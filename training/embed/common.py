"""
Shared helpers for the Stage 1 embedding pipeline (training/embed/).

JSONL I/O, the teacher-model allow-list (lab principle 3) and the guard that keeps
nai-bench out of every training input (no-contamination rule).
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
NAI_CORE = REPO / "apps" / "nai-core"
NAI_BENCH = REPO / "evals" / "nai-bench"

# Teacher models allowed to write training data. Keep in sync with
# docs/lab/MODEL_AND_DATA_LICENSES.md ("approved" / "candidate" teachers). Matching is on the
# Ollama tag prefix or the Hugging Face id. Hosted frontier APIs (Claude, GPT, ...) are never allowed.
APPROVED_TEACHERS: dict[str, str] = {
    "qwen2.5:7b": "Apache-2.0",
    "qwen3:14b": "Apache-2.0",
    "qwen3:30b-a3b": "Apache-2.0",
    "mistral-small3.1": "Apache-2.0",
    "Qwen/Qwen2.5-7B-Instruct": "Apache-2.0",
    "Qwen/Qwen3-14B": "Apache-2.0",
    "Qwen/Qwen3-30B-A3B": "Apache-2.0",
    "mistralai/Mistral-Small-3.1-24B-Instruct-2503": "Apache-2.0",
}
# Authors whose output must never become training data (lab principle 3). Matched as substrings.
FORBIDDEN_AUTHORS = ("claude", "anthropic", "openai", "gpt-", "chatgpt", "gemini", "copilot")


def teacher_license(model: str) -> str:
    """License of an approved teacher model; raises if the model is not approved."""
    for name, license_id in APPROVED_TEACHERS.items():
        if model == name or model.startswith(name + "-") or model.startswith(name + ":"):
            return license_id
    raise ValueError(
        f"teacher model {model!r} is not approved for generating training data. Check its license, add it to "
        "docs/lab/MODEL_AND_DATA_LICENSES.md and APPROVED_TEACHERS first (lab principle 3)."
    )


def check_author(author: str) -> str:
    """Raise if training text was written by a service whose terms forbid training on it."""
    lowered = author.lower()
    if any(name in lowered for name in FORBIDDEN_AUTHORS):
        raise ValueError(f"author {author!r} is not allowed as a source of training data (lab principle 3)")
    return author


def refuse_bench_path(path: Path) -> None:
    """Raise if ``path`` is inside evals/nai-bench (nai-bench must never become training data)."""
    resolved = path.resolve()
    if resolved == NAI_BENCH or NAI_BENCH in resolved.parents:
        raise ValueError(f"{path} is part of nai-bench, which must never be used for training")


def detect_language(text: str) -> str | None:
    """nai-bench's small stopword detector (en/de/sv/fr/pt), None when unsure."""
    if str(REPO / "evals") not in sys.path:
        sys.path.insert(0, str(REPO / "evals"))
    from naibench import detect_language as detect

    result: str | None = detect(text)
    return result


def read_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1
    return count


def append_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            handle.flush()  # a crash loses at most the current row; --resume continues from here
            count += 1
    return count
