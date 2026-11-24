"""
Quality filter and deduplication for Vane 1 training pairs (round 9 data pipeline).

Runs after generate_pairs.py and before mine_negatives.py / check_overlap.py. Every row first goes through the
training guard (``read_training_rows``: no nai-bench, no eval-only, no forbidden authors) and must carry
``provenance.use == "training"``. Then, in order:

1. query shape: length bounds, not a substring of its passage, not mostly copied from it (word overlap);
2. language: the query's detected language must match its label when the detector is sure;
3. exact duplicates: the same normalized query (keeps the first), the same (query, passage) pair;
4. near-duplicate passages: word 5-gram Jaccard >= ``--passage-jaccard`` with an earlier kept passage of the
   same language counts as the same passage (its pairs are re-pointed to the kept passage id);
5. caps: at most ``--max-per-passage`` queries per passage.

Writes kept rows to ``--output`` and a JSON report of what was dropped and why (``<output>.report.json``).

    python training/embed/filter_pairs.py --input training/data/vane1/pairs-raw.jsonl \\
        --output training/data/vane1/pairs-filtered.jsonl
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from common import detect_language, read_training_rows, refuse_bench_path, write_jsonl

MIN_QUERY_CHARS, MAX_QUERY_CHARS = 8, 200
MAX_COPIED_WORDS = 0.8  # share of a query's words (4+ letters) that may appear verbatim in the passage
PASSAGE_SHINGLE = 5
PASSAGE_JACCARD = 0.8
MAX_PER_PASSAGE = 6
MIN_PASSAGE_CHARS = 120


def normalize(text: str) -> str:
    return " ".join(re.findall(r"\w+", text.lower()))


def content_words(text: str) -> list[str]:
    return [w for w in re.findall(r"\w+", text.lower()) if len(w) >= 4]


def copied_share(query: str, passage: str) -> float:
    """Share of the query's content words that occur in the passage (1.0 = fully copied)."""
    words = content_words(query)
    if not words:
        return 0.0
    vocabulary = set(content_words(passage))
    return sum(w in vocabulary for w in words) / len(words)


def shingles(text: str, size: int = PASSAGE_SHINGLE) -> frozenset[tuple[str, ...]]:
    tokens = re.findall(r"\w+", text.lower())
    if len(tokens) < size:
        return frozenset({tuple(tokens)}) if tokens else frozenset()
    return frozenset(tuple(tokens[i : i + size]) for i in range(len(tokens) - size + 1))


def jaccard(a: frozenset[Any], b: frozenset[Any]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def query_problem(row: dict[str, Any], max_copied: float = MAX_COPIED_WORDS) -> str | None:
    """Why a single row is unusable on its own, or None."""
    raw = row.get("provenance")
    provenance: dict[str, Any] = raw if isinstance(raw, dict) else {}
    if provenance.get("use") != "training":
        return "not_marked_training"
    query, passage = str(row.get("query") or "").strip(), str(row.get("passage") or "")
    if not MIN_QUERY_CHARS <= len(query) <= MAX_QUERY_CHARS:
        return "query_length"
    if len(passage) < MIN_PASSAGE_CHARS:
        return "passage_too_short"
    if normalize(query) and normalize(query) in normalize(passage):
        return "query_in_passage"
    if copied_share(query, passage) > max_copied and len(content_words(query)) >= 3:
        return "query_copied"
    label, detected = row.get("query_language"), detect_language(query)
    if label and detected and label != detected:
        return "language_mismatch"
    return None


@dataclass
class PassageDeduper:
    """Maps near-duplicate passages (same language) to the first kept passage id."""

    threshold: float = PASSAGE_JACCARD
    kept: dict[str, list[tuple[str, frozenset[tuple[str, ...]]]]] = field(default_factory=dict)
    alias: dict[str, str] = field(default_factory=dict)
    exact: dict[str, str] = field(default_factory=dict)

    def canonical(self, passage_id: str, text: str, language: str | None) -> str:
        if passage_id in self.alias:
            return self.alias[passage_id]
        key = normalize(text)
        if key in self.exact:
            self.alias[passage_id] = self.exact[key]
            return self.exact[key]
        own = shingles(text)
        bucket = self.kept.setdefault(language or "?", [])
        for other_id, other in bucket:
            if jaccard(own, other) >= self.threshold:
                self.alias[passage_id] = other_id
                return other_id
        bucket.append((passage_id, own))
        self.exact[key] = passage_id
        self.alias[passage_id] = passage_id
        return passage_id


def filter_rows(
    rows: Iterable[dict[str, Any]],
    stats: Counter[str],
    *,
    max_per_passage: int = MAX_PER_PASSAGE,
    passage_jaccard: float = PASSAGE_JACCARD,
    max_copied: float = MAX_COPIED_WORDS,
) -> Iterator[dict[str, Any]]:
    seen_queries: set[str] = set()
    per_passage: Counter[str] = Counter()
    deduper = PassageDeduper(passage_jaccard)
    for row in rows:
        stats["read"] += 1
        problem = query_problem(row, max_copied)
        if problem:
            stats[problem] += 1
            continue
        key = normalize(row["query"])
        if key in seen_queries:
            stats["duplicate_query"] += 1
            continue
        passage_id = deduper.canonical(str(row["passage_id"]), row["passage"], row.get("passage_language"))
        if passage_id != row["passage_id"]:
            stats["near_duplicate_passage_merged"] += 1
        if per_passage[passage_id] >= max_per_passage:
            stats["passage_cap"] += 1
            continue
        seen_queries.add(key)
        per_passage[passage_id] += 1
        stats["kept"] += 1
        yield {**row, "passage_id": passage_id} if passage_id != row["passage_id"] else row


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-per-passage", type=int, default=MAX_PER_PASSAGE)
    parser.add_argument("--passage-jaccard", type=float, default=PASSAGE_JACCARD)
    parser.add_argument("--max-copied", type=float, default=MAX_COPIED_WORDS)
    args = parser.parse_args()
    for path in (args.input, args.output):
        refuse_bench_path(path)
    stats: Counter[str] = Counter()
    rows = filter_rows(
        read_training_rows(args.input),
        stats,
        max_per_passage=args.max_per_passage,
        passage_jaccard=args.passage_jaccard,
        max_copied=args.max_copied,
    )
    count = write_jsonl(args.output, rows)
    report = args.output.with_suffix(".report.json")
    report.write_text(json.dumps(dict(stats.most_common()), indent=1) + "\n", encoding="utf-8")
    print(f"kept {count} of {stats['read']} pairs -> {args.output}; report {report}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
