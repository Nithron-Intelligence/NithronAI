"""Baseline report pieces for v1: the right manifest for the cross-lingual flag, per-language and empty-result tables."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

EVALS = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(EVALS), str(EVALS / "retrieval"), str(EVALS / "answers")]

import eval_retrieval  # noqa: E402
import naibench as nb  # noqa: E402
import run_baseline  # noqa: E402

MANIFEST = [
    {"file": "Docs/en_note.md", "language": "en", "pages": None},
    {"file": "Docs/de_brief.md", "language": "de", "pages": None},
]


def _item(item_id: str, language: str, gold: str, category: str = "lookup") -> nb.BenchItem:
    return nb.BenchItem(
        id=item_id,
        question="q?",
        language=language,
        gold_answer="a",
        gold_facts=("a",),
        gold_sources=(nb.GoldSource(gold),),
        category=category,
        difficulty="easy",
        provenance={"author": "claude", "use": "eval-only"},
    )


class FakeClient:
    """Returns the English note for every query, except none at all for German queries."""

    def search(self, question: str, top_k: int, method: str) -> dict[str, Any]:
        results = [] if question.startswith("de:") else [{"doc_path": "src/Docs/en_note.md", "page": None}]
        return {"method": method, "results": results}


def test_evaluate_uses_the_given_manifest_for_the_cross_lingual_flag() -> None:
    items = [_item("a", "en", "Docs/en_note.md"), _item("b", "de", "Docs/en_note.md", "cross-lingual")]
    items[1] = items[1].__class__(**{**items[1].__dict__, "question": "de: q?"})
    report = eval_retrieval.evaluate(FakeClient(), items, ["embedding"], manifest=MANIFEST)  # type: ignore[arg-type]
    rows = {r["id"]: r for r in report["embedding"]["per_question"]}
    assert rows["a"]["cross_lingual"] == "no" and rows["b"]["cross_lingual"] == "yes"
    assert set(report["embedding"]["by_language"]) == {"en", "de"}

    lines = run_baseline.empty_result_lines(report, ["embedding"])
    assert lines[-1] == "| embedding | 0 of 1 | 1 of 1 |"
    table = run_baseline.language_lines(report["embedding"])
    assert table[2].startswith("| de | 1 |") and table[3].startswith("| en | 1 |")
