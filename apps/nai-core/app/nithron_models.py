"""
Nithron model catalog
The one place that defines Nithron model family names, IDs and display names
(docs/lab/MODEL_NAMING.md). Everything else (nAI's hardware detection, evals, training)
imports from here, so a family can be renamed in one edit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

BRAND = "Nithron"
HF_ORG = "nithron"
# Size variants (suffix after the version): smallest "mini", standard (no suffix), largest "max".
VARIANTS = ("mini", "max")


@dataclass(frozen=True)
class Family:
    key: str  # lower-case id used in model IDs ("vane")
    name: str  # display name, one syllable ("Vane")
    meaning: str
    role: str
    talks_to_users: bool
    target_size: str
    runs_on: str
    stage: str


FAMILIES: dict[str, Family] = {
    f.key: f
    for f in (
        Family(
            "vane",
            "Vane",
            "A weather vane points a direction; vectors are direction and magnitude.",
            "Embedding model: turns chunks and questions into vectors for semantic and cross-language search.",
            False,
            "~100–500M",
            "Any NAS CPU",
            "Stage 1",
        ),
        Family(
            "loupe",
            "Loupe",
            "A jeweller's lens for inspecting fine detail.",
            "Reranker: re-scores the top search hits so the best ones come first (multilingual).",
            False,
            "~100–600M",
            "Any NAS CPU",
            "Stage 1–2",
        ),
        Family(
            "tern",
            "Tern",
            "A seabird that travels the farthest on the least energy.",
            "Small answering model: grounded, cited answers; refuses when the files don't contain the answer.",
            True,
            "~1–4B",
            "CPU-only or low-RAM NAS",
            "Stage 2",
        ),
        Family(
            "nox",
            "Nox",
            "Latin for night: the flagship that guides you through the dark, like navigating by night.",
            "Flagship: stronger answers for hard questions and long documents, plus agent and tool use.",
            True,
            "~8B+",
            "NAS or PC with a GPU or lots of RAM",
            "Stage 2 (large tier) and Stage 3",
        ),
    )
}

# Pipeline order inside nAI: Vane -> Loupe -> Tern or Nox
PIPELINE = ("vane", "loupe", ("tern", "nox"))

# Planned first versions and their bases (docs/lab/stage1-embedding-finetune.md). Status changes to
# "released" only with a nai-bench result file backing the release (lab principle 4).
PLANNED: dict[str, dict[str, str]] = {
    "vane-1": {"base": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2", "status": "planned"},
    "loupe-1": {"base": "BAAI/bge-reranker-v2-m3", "status": "planned"},
    "tern-1": {"base": "to be chosen (Stage 2)", "status": "planned"},
    "nox-1": {"base": "to be chosen (Stage 2/3)", "status": "planned"},
}

_ID = re.compile(
    r"^(?:(?P<org>[\w.-]+)/)?(?P<family>[a-z]+)-(?P<version>\d+(?:\.\d+)?)"
    r"(?:-(?P<variant>[a-z]+?))?(?:-rc\d+)?$"  # "-rcN": release-candidate run labels (vane-1-rc1)
)


@dataclass(frozen=True)
class ModelRef:
    family: str
    version: str
    variant: str | None = None

    @property
    def slug(self) -> str:
        return f"{self.family}-{self.version}" + (f"-{self.variant}" if self.variant else "")

    @property
    def hf_id(self) -> str:
        return f"{HF_ORG}/{self.slug}"

    @property
    def display_name(self) -> str:
        """Public name, always with the brand: 'Nithron Tern 1 mini'."""
        name = f"{BRAND} {FAMILIES[self.family].name} {self.version}"
        return f"{name} {self.variant}" if self.variant else name


def model_ref(family: str, version: str, variant: str | None = None) -> ModelRef:
    if family not in FAMILIES:
        raise ValueError(f"unknown Nithron model family {family!r}")
    if variant is not None and variant not in VARIANTS:
        raise ValueError(f"unknown size variant {variant!r} (allowed: {', '.join(VARIANTS)})")
    if not re.fullmatch(r"\d+(\.\d+)?", version):
        raise ValueError(f"version must look like '1' or '1.5', got {version!r}")
    return ModelRef(family, version, variant)


def parse_model_id(model_id: str | None) -> ModelRef | None:
    """'nithron/tern-1-mini', 'tern-1' or 'ollama/nithron/nox-1.5' -> ModelRef; anything else -> None."""
    if not model_id:
        return None
    candidate = model_id.strip()
    if candidate.startswith("ollama/"):
        candidate = candidate[len("ollama/") :]
    candidate = candidate.split(":", 1)[0]  # Ollama tag
    match = _ID.match(candidate)
    if not match or match["family"] not in FAMILIES:
        return None
    if match["org"] not in (None, HF_ORG) or (match["variant"] and match["variant"] not in VARIANTS):
        return None
    return ModelRef(match["family"], match["version"], match["variant"])


def answering_family(gpu_memory_gb: float | None, memory_gb: float, cpu_count: int) -> str:
    """Which answering family fits a machine: Nox with a GPU (>= 10 GB VRAM) or lots of RAM, else Tern."""
    if (gpu_memory_gb or 0) >= 10 or (memory_gb >= 32 and cpu_count >= 8):
        return "nox"
    return "tern"


def answering_variant(family: str, memory_gb: float) -> str | None:
    """Size variant within the family: Tern mini for NAS boxes with less than 8 GB RAM."""
    if family == "tern" and memory_gb < 8:
        return "mini"
    return None
