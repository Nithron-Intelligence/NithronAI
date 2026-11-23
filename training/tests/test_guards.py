"""The lab-principle guards in training/embed work (no PyTorch needed)."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

EMBED = Path(__file__).resolve().parent.parent / "embed"
sys.path.insert(0, str(EMBED))

import check_overlap  # noqa: E402
import common  # noqa: E402
import train  # noqa: E402

REGISTER = common.REPO / "docs" / "lab" / "MODEL_AND_DATA_LICENSES.md"


def test_every_approved_teacher_has_an_approved_or_candidate_register_row() -> None:
    rows = [line for line in REGISTER.read_text(encoding="utf-8").splitlines() if line.startswith("| `")]
    allowed = [r for r in rows if re.search(r"\|\s*(approved|candidate)\s*\|", r)]
    for model in common.APPROVED_TEACHERS:
        assert any(f"`{model}`" in row for row in allowed), f"{model} has no approved/candidate register row"


@pytest.mark.parametrize("author", ["claude-opus-5-5", "Anthropic Claude", "gpt-4o", "ChatGPT", "gemini-2.5"])
def test_forbidden_authors_are_refused(author: str) -> None:
    with pytest.raises(ValueError):
        common.check_author(author)


def test_open_teacher_is_accepted() -> None:
    assert common.check_author("qwen2.5:7b") == "qwen2.5:7b"
    assert common.teacher_license("qwen2.5:7b") == "Apache-2.0"
    with pytest.raises(ValueError):
        common.teacher_license("gpt-4o")


def test_nai_bench_paths_are_refused() -> None:
    with pytest.raises(ValueError):
        common.refuse_bench_path(common.NAI_BENCH / "corpus")
    common.refuse_bench_path(common.REPO / "training")


def test_overlap_catches_bench_text_and_paraphrased_questions() -> None:
    index, questions = check_overlap.bench_index()
    kaution = (
        "Die Mieter leisten eine Kaution in Höhe von 3.450,00 €. Sie darf in drei gleichen monatlichen "
        "Teilbeträgen gezahlt werden; der erste Teilbetrag ist zu Beginn des Mietverhältnisses fällig."
    )
    assert check_overlap.overlap(kaution, index) > 0.5
    assert check_overlap.closest_question("Wie hoch ist laut Mietvertrag die Kaution?", questions) >= 0.6
    assert check_overlap.closest_question("When do tomatoes go into the raised bed?", questions) < 0.6


def _pair(query: str, pid: str, text: str, **provenance: str) -> dict[str, object]:
    base = {"author": "qwen2.5:7b", "passage_author": "qwen2.5:7b", "use": "training"}
    return {"query": query, "passage_id": pid, "passage": text, "provenance": {**base, **provenance}}


def test_load_pairs_enforces_provenance_and_merges_duplicate_texts(tmp_path: Path) -> None:
    path = tmp_path / "pairs.jsonl"
    rows = [_pair("q1", "a", "same text"), _pair("q2", "b", "same text"), _pair("q3", "c", "other")]
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    pairs = train.load_pairs(path, None)
    assert {p["passage_id"] for p in pairs if p["passage"] == "same text"} == {"a"}

    path.write_text(json.dumps(_pair("q", "a", "t", passage_author="claude-opus-5-5")), encoding="utf-8")
    with pytest.raises(ValueError):
        train.load_pairs(path, None)
    path.write_text(json.dumps(_pair("q", "a", "t", use="eval-only")), encoding="utf-8")
    with pytest.raises(ValueError):
        train.load_pairs(path, None)


def test_split_holds_out_whole_passages() -> None:
    pairs = [_pair(f"q{i}", f"p{i % 10}", f"text {i % 10}") for i in range(40)]
    trained, held_out = train.split_by_passage(pairs, 0.2, seed=1)
    assert {p["passage_id"] for p in trained}.isdisjoint({p["passage_id"] for p in held_out})
    corpus = train.eval_corpus(trained, held_out, distractors=3, seed=1)
    assert len(corpus) == len({p["passage_id"] for p in held_out}) + 3
