"""
nAI retrieval evaluation on nai-bench
=====================================

Runs every answerable nai-bench question through ``POST /search`` and scores the
ranked files against the gold sources (document level: several chunks of the same
file count once). Unanswerable questions have no gold sources and are skipped here;
``answers/eval_answers.py`` scores them.

Metrics per retrieval method, overall and per category / language:
  Recall@K, Precision@K, Hit@K (at least one gold file in the top K), MRR, NDCG@K,
  and page Hit@K (a returned chunk from a gold file *and* gold page, for gold
  sources that have a page).

Usage (nAI running with auth off, or pass --api-key):
    python evals/retrieval/eval_retrieval.py --index-corpus /path/seen/by/server \\
        --methods bm25,embedding,hybrid --output results.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from naibench import (
    QUESTIONS_FILE,
    BenchItem,
    NaiClient,
    hit_at_k,
    is_cross_lingual,
    load_items,
    load_manifest,
    matches_gold,
    mean,
    ndcg_at_k,
    precision_at_k,
    ranked_files,
    recall_at_k,
    reciprocal_rank,
)

DEFAULT_K = (1, 3, 5, 10)


def page_hit_at_k(results: list[dict[str, Any]], item: BenchItem, k: int) -> float | None:
    """1.0 if a top-k chunk comes from a gold file *and* its gold page (None: no paged gold)."""
    paged = [s for s in item.gold_sources if s.page is not None]
    if not paged:
        return None
    files_seen: list[str] = []
    for r in results:
        if r["doc_path"] not in files_seen:
            files_seen.append(r["doc_path"])
        if len(files_seen) > k:
            break
        if any(matches_gold(r["doc_path"], s.file) and r.get("page") == s.page for s in paged):
            return 1.0
    return 0.0


def score_item(item: BenchItem, results: list[dict[str, Any]], k_values: tuple[int, ...]) -> dict[str, Any]:
    ranked = ranked_files([r["doc_path"] for r in results])
    gold = item.gold_files
    row: dict[str, Any] = {
        "id": item.id,
        "category": item.category,
        "language": item.language,
        "retrieved": ranked[:5],
        "gold": list(gold),
        "mrr": reciprocal_rank(ranked, gold),
    }
    for k in k_values:
        row[f"recall@{k}"] = recall_at_k(ranked, gold, k)
        row[f"precision@{k}"] = precision_at_k(ranked, gold, k)
        row[f"hit@{k}"] = hit_at_k(ranked, gold, k)
        row[f"ndcg@{k}"] = ndcg_at_k(ranked, gold, k)
        row[f"page_hit@{k}"] = page_hit_at_k(results, item, k)
    return row


def aggregate(rows: list[dict[str, Any]], k_values: tuple[int, ...]) -> dict[str, Any]:
    keys = ["mrr"] + [
        f"{m}@{k}" for k in k_values for m in ("recall", "precision", "hit", "ndcg", "page_hit")
    ]
    out: dict[str, Any] = {"n": len(rows)}
    for key in keys:
        values = [r[key] for r in rows if r.get(key) is not None]
        out[key] = round(mean(values), 4) if values else None
    return out


def breakdown(rows: list[dict[str, Any]], field: str, k_values: tuple[int, ...]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[row[field]].append(row)
    return {name: aggregate(group, k_values) for name, group in sorted(groups.items())}


def evaluate(
    client: NaiClient, items: list[BenchItem], methods: list[str], k_values: tuple[int, ...] = DEFAULT_K
) -> dict[str, Any]:
    answerable = [i for i in items if i.answerable]
    top_k = max(k_values) * 3  # chunks; several chunks of one file collapse into one ranked file
    manifest = load_manifest()
    report: dict[str, Any] = {
        "questions": len(answerable),
        "skipped_unanswerable": len(items) - len(answerable),
    }
    for method in methods:
        rows, errors, used = [], [], set()
        for item in answerable:
            try:
                data = client.search(item.question, top_k=top_k, method=method)
            except Exception as e:  # report and keep going; one bad query must not hide the rest
                errors.append({"id": item.id, "error": str(e)})
                continue
            used.add(data.get("method"))
            row = score_item(item, data.get("results", []), k_values)
            row["cross_lingual"] = "yes" if is_cross_lingual(item, manifest) else "no"
            rows.append(row)
        report[method] = {
            "method_used": sorted(m for m in used if m),
            "overall": aggregate(rows, k_values),
            "by_category": breakdown(rows, "category", k_values),
            "by_language": breakdown(rows, "language", k_values),
            # question language differs from all gold sources' languages (wider than the category)
            "by_cross_lingual": breakdown(rows, "cross_lingual", k_values),
            "errors": errors,
            "per_question": rows,
        }
    return report


def print_summary(report: dict[str, Any], methods: list[str]) -> None:
    print(f"\nnai-bench retrieval: {report['questions']} answerable questions")
    print(f"{'method':<12}{'MRR':>7}{'Hit@1':>8}{'Hit@5':>8}{'R@5':>7}{'P@5':>7}{'nDCG@5':>8}{'pHit@5':>8}")
    for method in methods:
        o = report[method]["overall"]
        print(
            f"{method:<12}{o['mrr']:>7.3f}{o['hit@1']:>8.3f}{o['hit@5']:>8.3f}{o['recall@5']:>7.3f}"
            f"{o['precision@5']:>7.3f}{o['ndcg@5']:>8.3f}{(o['page_hit@5'] or 0):>8.3f}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate nAI retrieval on nai-bench")
    parser.add_argument("--bench", type=Path, default=QUESTIONS_FILE, help="questions.jsonl")
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument(
        "--reviewed-only", action="store_true", help="only human-reviewed items (published numbers)"
    )
    parser.add_argument("--api-key", default=None, help="nAI API key (when auth is on)")
    parser.add_argument("--methods", default="bm25,embedding,hybrid", help="comma-separated /search methods")
    parser.add_argument("--k-values", default=",".join(map(str, DEFAULT_K)))
    parser.add_argument(
        "--index-corpus",
        metavar="SERVER_PATH",
        help="create a 'nai-bench' source for this path (as the server sees it) and wait until indexed",
    )
    parser.add_argument("--output", type=Path, help="write the full report as JSON")
    args = parser.parse_args()

    items = load_items(args.bench, reviewed_only=args.reviewed_only)
    methods = [m.strip() for m in args.methods.split(",") if m.strip()]
    k_values = tuple(int(k) for k in args.k_values.split(","))
    client = NaiClient(args.api_url, args.api_key)
    client.wait_until_up()
    if args.index_corpus:
        source_id = client.ensure_source(args.index_corpus)
        client.wait_until_indexed(source_id)

    report = evaluate(client, items, methods, k_values)
    print_summary(report, methods)
    if args.output:
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"\nwrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
