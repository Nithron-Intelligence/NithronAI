"""The lab-principle guards in training/embed work (no PyTorch needed)."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest

EMBED = Path(__file__).resolve().parent.parent / "embed"
sys.path.insert(0, str(EMBED))

import check_overlap  # noqa: E402
import common  # noqa: E402
import generate_pairs  # noqa: E402
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


GOOD_PASSAGE = {"id": "p1", "text": "Some synthetic text.", "author": "qwen2.5:7b", "license": "CC0-1.0"}


@pytest.mark.parametrize(
    "bad",
    [
        {**GOOD_PASSAGE, "use": "eval-only"},
        {**GOOD_PASSAGE, "provenance": {"author": "qwen2.5:7b", "use": "eval-only"}},
        {**GOOD_PASSAGE, "author": "claude-opus-5-5"},
        {**GOOD_PASSAGE, "provenance": {"author": "qwen2.5:7b", "passage_author": "Claude (Anthropic)"}},
        {**GOOD_PASSAGE, "provenance": {"model": "claude-opus-5-5", "use": "training"}},
        {**GOOD_PASSAGE, "gold_answer": "x", "gold_sources": []},
    ],
    ids=[
        "eval-only",
        "provenance-eval-only",
        "claude-author",
        "claude-passage-author",
        "claude-model",
        "bench-item",
    ],
)
def test_training_rows_refuse_eval_only_claude_and_bench_items(tmp_path: Path, bad: dict[str, Any]) -> None:
    path = tmp_path / "passages.jsonl"
    path.write_text(json.dumps(GOOD_PASSAGE) + "\n" + json.dumps(bad) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="line 2"):
        list(common.read_training_rows(path))


def test_training_rows_accept_open_teacher_rows(tmp_path: Path) -> None:
    path = tmp_path / "passages.jsonl"
    path.write_text(json.dumps(GOOD_PASSAGE) + "\n", encoding="utf-8")
    assert list(common.read_training_rows(path)) == [GOOD_PASSAGE]


def test_real_nai_bench_questions_cannot_be_loaded_as_training_data(tmp_path: Path) -> None:
    bench = common.NAI_BENCH / "questions.jsonl"
    with pytest.raises(ValueError, match="nai-bench"):
        list(common.read_training_rows(bench))  # by path
    copy = tmp_path / "copied.jsonl"
    copy.write_text(bench.read_text(encoding="utf-8").splitlines()[0] + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match=r"eval-only|not allowed|nai-bench"):
        list(common.read_training_rows(copy))  # copied out of the repo folder: refused by its content


def test_generate_pairs_and_train_load_through_the_guard(tmp_path: Path) -> None:
    passages = tmp_path / "passages.jsonl"
    passages.write_text(
        json.dumps({**GOOD_PASSAGE, "provenance": {"use": "eval-only"}}) + "\n", encoding="utf-8"
    )
    args = argparse.Namespace(
        passages=passages, seed=1, limit=None, resume=False, output=tmp_path / "o.jsonl"
    )
    with pytest.raises(ValueError, match="eval-only"):
        generate_pairs.select_passages(args)
    pairs = tmp_path / "pairs.jsonl"
    pairs.write_text(json.dumps({**_pair("q", "a", "t"), "gold_facts": ["x"]}) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="nai-bench item"):
        train.load_pairs(pairs, None)


def test_overlap_check_covers_nai_bench_v1_files_and_questions() -> None:
    _, questions = check_overlap.bench_texts()
    index, _ = check_overlap.bench_index()
    v1 = check_overlap.V1
    # a v1 question from the dev and from the test file, and text from a downloaded v1 file
    rows = [
        json.loads(line)
        for name in ("questions-dev.jsonl", "questions-test.jsonl")
        for line in (v1 / name).read_text(encoding="utf-8").splitlines()[:1]
    ]
    assert all(r["question"] in questions for r in rows)
    eu = check_overlap._corpus_file_text(v1 / "corpus" / "Recht/EU/CELEX_32011L0083_EN_TXT.html")
    passage = " ".join(eu.split()[3000:3200])
    assert check_overlap.overlap(passage, index) > 0.9
    assert (
        check_overlap.overlap("Our cat sleeps on the warm windowsill every sunny afternoon in May.", index)
        < 0.2
    )
