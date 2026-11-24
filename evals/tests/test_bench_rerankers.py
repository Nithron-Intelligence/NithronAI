"""Reranker bench: re-scoring only nAI's top-N candidates and refusing a test split."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

EVALS = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(EVALS), str(EVALS / "rerankers")]

import bench_rerankers  # noqa: E402

RESULTS = [{"doc_path": f"f{i}.md", "text": f"t{i}"} for i in range(5)]


def test_split_head_keeps_the_tail_in_hybrid_order() -> None:
    head, tail = bench_rerankers.split_head(RESULTS, 2)
    assert [r["doc_path"] for r in head] == ["f0.md", "f1.md"]
    assert [r["doc_path"] for r in tail] == ["f2.md", "f3.md", "f4.md"]


def test_split_head_none_rescores_everything() -> None:
    head, tail = bench_rerankers.split_head(RESULTS, None)
    assert head == RESULTS and tail == []


def test_score_ranking_refuses_the_v1_test_split() -> None:
    with pytest.raises(Exception, match="test"):
        bench_rerankers.score_ranking([], EVALS / "nai-bench" / "v1" / "questions-test.jsonl")


def test_v1_dev_ranking_scores_every_answerable_item() -> None:
    bench = EVALS / "nai-bench" / "v1" / "questions-dev.jsonl"
    items = [i for i in bench_rerankers.load_items(bench) if i.answerable]
    per_question = [{"id": i.id, "results": []} for i in items]
    report = bench_rerankers.score_ranking(per_question, bench)
    assert report["overall"]["mrr"] == 0.0
    assert set(report["by_cross_lingual"]) <= {"yes", "no"}
    assert report["by_language"]
