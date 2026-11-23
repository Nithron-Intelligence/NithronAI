"""
nAI Core Hardware Detection

Detects CPU, memory and GPU so nAI can pick sensible defaults (reranker on/off, which
local LLM to use) and tell the admin what the box can handle.
"""

import json
import os
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
    cpu_count: int
    memory_gb: float
    gpus: list[GPUInfo] = field(default_factory=list)

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
    info = HardwareInfo(
        cpu_count=os.cpu_count() or 1, memory_gb=_memory_gb(), gpus=_nvidia_gpus() + _drm_gpus()
    )
    logger.info(f"Hardware: {info.cpu_count} CPUs, {info.memory_gb} GB RAM, tier={info.tier}")
    return info


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
    if hw.tier == "low":
        tips.append("Reranking is best left off on this machine (NAI_RERANKER=false).")
    else:
        tips.append(
            "This machine can afford reranking, but the default reranker is English-only: enable it "
            "(NAI_RERANKER=true) only with a multilingual NAI_RERANKER_MODEL."
        )
    return tips
