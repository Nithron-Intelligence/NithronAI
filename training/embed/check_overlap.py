"""
Contamination check: training data must not overlap with nai-bench.

Compares word 8-gram shingles of every training passage and query with the
nai-bench corpus source texts and questions, and each (short) query's word set
with every nai-bench question (Jaccard >= 0.6 counts as a copy). Exits 1 if any
row overlaps. With --write-clean, writes the rows that pass to a new file and
exits 0 (the flagged rows are reported but dropped).

Note: the public-domain statute excerpts in nai-bench (BGB §§ 535/551/573c,
Jordabalken 12:4) are in the index, so training on those same paragraphs is
flagged by design; use other statutes or sections.

    python training/embed/check_overlap.py data/pairs.jsonl
    python training/embed/check_overlap.py data/pairs.jsonl --write-clean data/pairs.clean.jsonl
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from common import NAI_BENCH, read_jsonl, write_jsonl

SHINGLE = 8
QUERY_JACCARD = 0.6  # short queries: word-set similarity with a nai-bench question that counts as a copy


def words(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


def shingles(text: str, size: int = SHINGLE) -> set[tuple[str, ...]]:
    tokens = words(text)
    if len(tokens) < size:
        return {tuple(tokens)} if tokens else set()
    return {tuple(tokens[i : i + size]) for i in range(len(tokens) - size + 1)}


def bench_index() -> tuple[set[tuple[str, ...]], list[set[str]]]:
    """Shingles of every nai-bench source text and question, and each question's word set."""
    texts = [p.read_text(encoding="utf-8") for p in sorted((NAI_BENCH / "corpus-src").glob("*.src.md"))]
    questions = [row["question"] for row in read_jsonl(NAI_BENCH / "questions.jsonl")]
    index: set[tuple[str, ...]] = set()
    for text in [*texts, *questions]:
        index |= shingles(text)
    return index, [set(words(q)) for q in questions]


def closest_question(query: str, questions: list[set[str]]) -> float:
    """Highest word-set Jaccard similarity between a query and any nai-bench question.

    Queries are usually shorter than one 8-gram, so shingles can't catch paraphrased copies.
    """
    own = set(words(query))
    if not own:
        return 0.0
    return max((len(own & q) / len(own | q) for q in questions), default=0.0)


def overlap(text: str, index: set[tuple[str, ...]]) -> float:
    own = shingles(text)
    return len(own & index) / len(own) if own else 0.0


def main() -> int:
    parser = argparse.ArgumentParser(description="Check training data for overlap with nai-bench")
    parser.add_argument("data", type=Path, help="pairs.jsonl or passages.jsonl")
    parser.add_argument(
        "--max-overlap", type=float, default=0.1, help="max share of shingles found in nai-bench"
    )
    parser.add_argument("--write-clean", type=Path, help="write the rows that pass here")
    args = parser.parse_args()

    index, bench_questions = bench_index()
    rows = list(read_jsonl(args.data))
    clean, flagged = [], 0
    for row in rows:
        texts = [row.get("passage") or row.get("text") or "", row.get("query") or ""]
        worst = max(overlap(t, index) for t in texts if t) if any(texts) else 0.0
        repeated = closest_question(row.get("query") or "", bench_questions) >= QUERY_JACCARD
        if worst > args.max_overlap or repeated:
            flagged += 1
            if flagged <= 10:
                print(
                    f"overlap {worst:.2f}{' (query copies a nai-bench question)' if repeated else ''}: {texts[-1][:80]!r}"
                )
        else:
            clean.append(row)
    print(
        f"{len(rows)} rows, {flagged} overlap with nai-bench "
        f"(> {args.max_overlap:.0%} shared 8-grams, or a query close to a nai-bench question)"
    )
    if args.write_clean:
        write_jsonl(args.write_clean, clean)
        print(f"wrote {len(clean)} clean rows to {args.write_clean}")
        return 0
    return 1 if flagged else 0


if __name__ == "__main__":
    raise SystemExit(main())
