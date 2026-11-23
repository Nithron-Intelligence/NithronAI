"""
nAI Core Hardware Detection

Detects CPU, memory and GPU so nAI can pick sensible defaults (semantic search and
reranker on/off, which local LLM to use) and tell the admin what the box can handle.
"""

import json
import math
import os
import platform
import shutil
import subprocess
import time
import urllib.request
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from typing import Any

from .utils.logging import get_logger

logger = get_logger(__name__)

GB = 1024**3


@dataclass
class GPUInfo:
    vendor: str
    name: str
    memory_gb: float | None = None


@dataclass
class HardwareInfo:
    cpu_count: int  # CPUs this process may use (cgroup quota and affinity applied)
    memory_gb: float  # RAM this process may use (cgroup limit applied)
    gpus: list[GPUInfo] = field(default_factory=list)
    physical_cores: int | None = None  # None: unknown (then cpu_count is used)
    memory_available_gb: float | None = None
    arch: str = ""
    avx2: bool | None = None  # x86 only; None: unknown or not x86

    @property
    def effective_cores(self) -> int:
        """Cores that do real work: physical cores (no SMT siblings), capped by the CPU quota."""
        if self.physical_cores:
            return max(1, min(self.physical_cores, self.cpu_count))
        return self.cpu_count

    @property
    def gpu_memory_gb(self) -> float | None:
        known = [g.memory_gb for g in self.gpus if g.memory_gb]
        return max(known) if known else None

    @property
    def tier(self) -> str:
        """low: small NAS CPU · standard: desktop-class CPU · gpu: dedicated GPU with known VRAM."""
        if (self.gpu_memory_gb or 0) >= 6:
            return "gpu"
        if self.cpu_count >= 8 and self.memory_gb >= 16:
            return "standard"
        return "low"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["tier"] = self.tier
        data["gpu_memory_gb"] = self.gpu_memory_gb
        return data


def _memory_gb() -> float:
    try:
        return round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / GB, 1)
    except (ValueError, OSError, AttributeError):
        return 0.0


def _read(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read().strip()
    except OSError:
        return None


def _cgroup_cpu_limit() -> float | None:
    """CPU quota of this container (docker --cpus), from cgroup v2 or v1; None if unlimited."""
    v2 = _read("/sys/fs/cgroup/cpu.max")
    if v2:
        quota, _, period = v2.partition(" ")
        if quota != "max" and period:
            return int(quota) / int(period)
        return None
    quota_v1, period_v1 = (
        _read("/sys/fs/cgroup/cpu/cpu.cfs_quota_us"),
        _read("/sys/fs/cgroup/cpu/cpu.cfs_period_us"),
    )
    if quota_v1 and period_v1 and int(quota_v1) > 0:
        return int(quota_v1) / int(period_v1)
    return None


def _cgroup_memory_gb() -> tuple[float | None, float | None]:
    """(limit, available) from the cgroup (docker --memory); (None, None) if unlimited."""
    limit = _read("/sys/fs/cgroup/memory.max") or _read("/sys/fs/cgroup/memory/memory.limit_in_bytes")
    used = _read("/sys/fs/cgroup/memory.current") or _read("/sys/fs/cgroup/memory/memory.usage_in_bytes")
    if not limit or limit == "max" or int(limit) >= 1 << 60:  # v1 reports a huge number when unlimited
        return None, None
    limit_gb = int(limit) / GB
    available = limit_gb - int(used) / GB if used else None
    return round(limit_gb, 1), (round(available, 1) if available is not None else None)


def _mem_available_gb() -> float | None:
    for line in (_read("/proc/meminfo") or "").splitlines():
        if line.startswith("MemAvailable:"):
            return round(int(line.split()[1]) * 1024 / GB, 1)
    return None


def _cpuinfo() -> tuple[int | None, bool | None]:
    """(physical cores, AVX2 available) from /proc/cpuinfo; None where unknown."""
    text = _read("/proc/cpuinfo") or ""
    cores: set[tuple[str, str]] = set()
    physical_id = core_id = ""
    avx2: bool | None = None
    for line in text.splitlines():
        key, _, value = line.partition(":")
        key, value = key.strip(), value.strip()
        if key == "physical id":
            physical_id = value
        elif key == "core id":
            core_id = value
            cores.add((physical_id, core_id))
        elif key == "flags" and avx2 is None:
            avx2 = "avx2" in value.split()
    return (len(cores) or None), avx2


def _usable_cpus() -> int:
    """Logical CPUs this process may run on: affinity, then the cgroup quota (rounded up)."""
    try:
        count = len(os.sched_getaffinity(0))
    except (AttributeError, OSError):
        count = os.cpu_count() or 1
    limit = _cgroup_cpu_limit()
    return max(1, min(count, math.ceil(limit))) if limit else count


def _nvidia_gpus() -> list[GPUInfo]:
    if shutil.which("nvidia-smi") is None:
        return []
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=3,
            check=True,
        ).stdout
    except (subprocess.SubprocessError, OSError):
        return []
    gpus = []
    for line in out.strip().splitlines():
        name, _, mem = line.rpartition(",")
        try:
            gpus.append(GPUInfo("nvidia", name.strip(), round(float(mem) / 1024, 1)))
        except ValueError:
            gpus.append(GPUInfo("nvidia", line.strip()))
    return gpus


def _drm_gpus() -> list[GPUInfo]:
    """AMD/Intel GPUs via /sys (VRAM is reported for AMD dedicated cards)."""
    gpus = []
    vendors = {"0x1002": "amd", "0x8086": "intel"}
    base = "/sys/class/drm"
    if not os.path.isdir(base):
        return []
    for card in sorted(os.listdir(base)):
        if not card.startswith("card") or "-" in card:
            continue
        device = os.path.join(base, card, "device")
        try:
            with open(os.path.join(device, "vendor")) as f:
                vendor = vendors.get(f.read().strip())
        except OSError:
            continue
        if vendor is None:
            continue
        memory = None
        try:
            with open(os.path.join(device, "mem_info_vram_total")) as f:
                memory = round(int(f.read().strip()) / GB, 1)
        except (OSError, ValueError):
            pass
        gpus.append(GPUInfo(vendor, card, memory))
    return gpus


@lru_cache(maxsize=1)
def detect_hardware() -> HardwareInfo:
    """What this process can use. Inside a container the cgroup CPU quota and memory limit count,
    not the host's totals (docker --cpus=2 --memory=4g looks like a 2-CPU, 4 GB machine)."""
    physical, avx2 = _cpuinfo()
    limit_gb, cgroup_available = _cgroup_memory_gb()
    memory = min(_memory_gb(), limit_gb) if limit_gb else _memory_gb()
    available = [a for a in (_mem_available_gb(), cgroup_available) if a is not None]
    arch = platform.machine().lower()
    info = HardwareInfo(
        cpu_count=_usable_cpus(),
        memory_gb=memory,
        gpus=_nvidia_gpus() + _drm_gpus(),
        physical_cores=physical,
        memory_available_gb=min(available) if available else None,
        arch=arch,
        avx2=avx2 if arch in ("x86_64", "amd64") else None,
    )
    logger.info(
        f"Hardware: {info.cpu_count} usable CPUs ({info.effective_cores} effective cores), "
        f"{info.memory_gb} GB RAM, tier={info.tier}"
    )
    return info


# ---------------------------------------------------------------------------
# Reranker auto policy
# ---------------------------------------------------------------------------

# Budget: reranking the top 10 should add at most about 1 s per question (median). Measured (provisional,
# nai-bench v0, evals/results/rerankers-threads-2026-11-23.md): bge-reranker-v2-m3 int8, 10 passages on a
# Ryzen 9 7950X takes 2.1 s with 2 threads, 1.1 s with 4 and 0.7 s with 8. NAS cores are slower than Zen 4
# cores, so auto needs 8 effective cores; 2-4 core NAS boxes stay off. A GPU doesn't count: nAI runs the
# reranker with the CPU build of onnxruntime.
RERANKER_MIN_CORES = 8
RERANKER_MIN_MEMORY_GB = 8.0
RERANKER_MIN_AVAILABLE_GB = 2.0  # int8 model (0.57 GB download) needs ~1-1.5 GB while running


def reranker_auto_decision(hw: HardwareInfo) -> tuple[bool, str]:
    """Whether NAI_RERANKER=auto turns the reranker on for this machine, with a short reason."""
    cores = hw.effective_cores
    facts = f"{cores} cores, {hw.memory_gb:g} GB RAM"
    if hw.avx2 is False:
        return False, f"{facts}, no AVX2 (int8 inference would be too slow)"
    if cores < RERANKER_MIN_CORES:
        return False, f"{facts}: needs {RERANKER_MIN_CORES}+ cores (NAS-class CPU)"
    if hw.memory_gb < RERANKER_MIN_MEMORY_GB:
        return False, f"{facts}: needs {RERANKER_MIN_MEMORY_GB:g}+ GB RAM"
    if hw.memory_available_gb is not None and hw.memory_available_gb < RERANKER_MIN_AVAILABLE_GB:
        return False, f"{facts}: only {hw.memory_available_gb:g} GB free"
    return True, facts


# ---------------------------------------------------------------------------
# Embeddings auto policy (keyword-only mode)
# ---------------------------------------------------------------------------

# granite-embedding-97m-multilingual-r2 (fp32 ONNX) peaks at 1 759 MiB while indexing with the reranker off
# (2 CPU / 4 GB simulated NAS, evals/results/simulated-nas-granite97-rerank-off-2026-11-23.md). With ~40 %
# headroom for the OS share of a container, SQLite and spikes that is ~2.5 GB: NithronOS (3g) and TrueNAS (4g)
# templates stay on, a 2 GB box or a smaller limit runs keyword-only (BM25). There is deliberately no smaller
# fallback model (decision 2026-11-23).
EMBEDDINGS_MIN_MEMORY_GB = 2.5
EMBEDDINGS_RECOMMENDED_MEMORY_GB = 3.0


def embeddings_auto_decision(hw: HardwareInfo) -> tuple[bool, str]:
    """Whether NAI_EMBEDDINGS=auto turns semantic search on for this machine, with a short reason.

    Uses the effective memory (cgroup limit capped by the host's RAM), not what is free right now: a
    temporarily busy box should not flip between modes from one start to the next."""
    facts = f"{hw.memory_gb:g} GB RAM"
    if hw.memory_gb < EMBEDDINGS_MIN_MEMORY_GB:
        return False, (
            f"{facts}: semantic search needs {EMBEDDINGS_MIN_MEMORY_GB:g}+ GB "
            f"({EMBEDDINGS_RECOMMENDED_MEMORY_GB:g}+ recommended), keyword search only"
        )
    return True, facts


# ---------------------------------------------------------------------------
# Ollama model selection
# ---------------------------------------------------------------------------

_OLLAMA_CACHE: dict[str, tuple[float, Any]] = {}
_OLLAMA_TTL = 300


def ollama_models(base_url: str) -> list[dict[str, Any]]:
    """Installed Ollama models (cached for a few minutes). Empty list if unreachable."""
    cached = _OLLAMA_CACHE.get(base_url)
    if cached and time.monotonic() - cached[0] < _OLLAMA_TTL:
        return cached[1]
    try:
        with urllib.request.urlopen(base_url.rstrip("/") + "/api/tags", timeout=3) as response:
            models = json.load(response).get("models", [])
    except (OSError, ValueError):
        models = []
    _OLLAMA_CACHE[base_url] = (time.monotonic(), models)
    return models


def memory_budget_gb(hw: HardwareInfo) -> float:
    """Memory a local model may use: most of the VRAM, or half the system RAM on CPU."""
    if hw.gpu_memory_gb:
        return hw.gpu_memory_gb * 0.9
    return hw.memory_gb * 0.5


def choose_ollama_model(models: list[dict[str, Any]], hw: HardwareInfo) -> str | None:
    """Largest installed chat model whose weights fit the memory budget."""
    budget = memory_budget_gb(hw) * GB
    chat_models = [m for m in models if "embed" not in m.get("name", "").lower()]
    fitting = [m for m in chat_models if m.get("size", 0) <= budget]
    if fitting:
        return max(fitting, key=lambda m: m.get("size", 0))["name"]
    if chat_models:  # nothing fits: the smallest one is the best bet
        return min(chat_models, key=lambda m: m.get("size", 0))["name"]
    return None


def recommendations(hw: HardwareInfo) -> list[str]:
    """Plain-language advice for the admin (model names are examples; check Ollama's library)."""
    tips: list[str] = []
    vram = hw.gpu_memory_gb
    if vram and vram >= 20:
        tips.append(f"GPU with {vram:g} GB: a ~27-32B model (Q4) runs comfortably.")
    elif vram and vram >= 10:
        tips.append(f"GPU with {vram:g} GB: a 12-14B model (Q4) is a good fit.")
    elif vram and vram >= 6:
        tips.append(f"GPU with {vram:g} GB: use a 7-8B model (Q4).")
    elif hw.memory_gb >= 16:
        tips.append(
            "No usable GPU detected: a 3-4B model runs on CPU but slowly (a few tokens/s). "
            "Consider pointing NAI_LLM_BASE_URL at Ollama on a PC with a GPU."
        )
    else:
        tips.append(
            "Limited hardware: search and extractive answers work well; use a remote Ollama "
            "(NAI_LLM_BASE_URL) for generated answers."
        )
    rerank_on, reason = reranker_auto_decision(hw)
    if rerank_on:
        tips.append(f"Reranking runs automatically here ({reason}); NAI_RERANKER=off turns it off.")
    else:
        tips.append(
            f"Reranking stays off on this machine ({reason}); NAI_RERANKER=false keeps it off, "
            "NAI_RERANKER=on forces it (about 2 s or more per question on small CPUs)."
        )
    return tips


def nithron_answering_model(hw: HardwareInfo) -> dict[str, Any]:
    """Which Nithron answering model (Tern or Nox) fits this machine, for the model picker."""
    from .nithron_models import FAMILIES, PLANNED, answering_family, answering_variant, model_ref

    family = answering_family(hw.gpu_memory_gb, hw.memory_gb, hw.cpu_count)
    ref = model_ref(family, "1", answering_variant(family, hw.memory_gb))
    return {
        "family": FAMILIES[family].name,
        "model_id": ref.hf_id,
        "display_name": ref.display_name,
        "status": PLANNED.get(f"{family}-1", {}).get("status", "planned"),
    }
