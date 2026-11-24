"""
Mine hard negatives for Vane 1 pairs with the base model (Granite R2 97m), offline and once.

For every query, ranks all passages of the dataset and keeps ``--negatives`` passages that are hard (high rank)
but safely not positives:

- never the positive itself and never a passage from the same source document (``passage_file``): neighbours
  in one file are often relevant too (false negatives);
- ranks ``--range-min``..``--range-max`` only (the very top is skipped: often unlabeled positives);
- score below ``--margin`` × the positive's score (positive-aware filter, as in NV-Retriever's TopK-PercPos).

Writes the rows with a ``negatives`` list (passage texts) and ``negative_ids``. Needs PyTorch and
sentence-transformers: run it in the ROCm trainer container. Pure-Python selection logic lives in
``pick_negatives`` (tested without PyTorch).

    python3 training/embed/mine_negatives.py --input training/data/vane1/pairs-filtered.jsonl \\
        --output training/data/vane1/pairs-mined.jsonl
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from common import read_training_rows, refuse_bench_path, write_jsonl

DEFAULT_MODEL = "ibm-granite/granite-embedding-97m-multilingual-r2"
NEGATIVES = 3
RANGE_MIN, RANGE_MAX = 3, 50
MARGIN = 0.95


def pick_negatives(
    ranked: list[tuple[str, float]],
    positive_score: float,
    excluded: set[str],
    *,
    count: int = NEGATIVES,
    range_min: int = RANGE_MIN,
    range_max: int = RANGE_MAX,
    margin: float = MARGIN,
) -> list[str]:
    """Passage ids from a ranking ``[(id, score), ...]`` (best first) that are hard but safe negatives."""
    picked: list[str] = []
    for position, (passage_id, score) in enumerate(ranked):
        if position < range_min or passage_id in excluded:
            continue
        if position >= range_max or len(picked) == count:
            break
        if score >= margin * positive_score:
            continue
        picked.append(passage_id)
    return picked


def passage_file(row: dict[str, Any]) -> str:
    """The source document of a row's passage (falls back to the passage id)."""
    provenance = row.get("provenance") or {}
    return str(row.get("passage_file") or provenance.get("passage_file") or row["passage_id"])


def mine(rows: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    import numpy as np
    import torch
    from sentence_transformers import SentenceTransformer

    texts: dict[str, str] = {}
    files: dict[str, str] = {}
    for row in rows:
        texts.setdefault(row["passage_id"], row["passage"])
        files.setdefault(row["passage_id"], passage_file(row))
    ids = list(texts)
    by_file: dict[str, set[str]] = defaultdict(set)
    for passage_id in ids:
        by_file[files[passage_id]].add(passage_id)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = SentenceTransformer(args.model, device=device)  # never trust_remote_code
    model.max_seq_length = args.max_seq_length
    p = model.encode(
        [texts[i] for i in ids], batch_size=128, normalize_embeddings=True, convert_to_numpy=True
    )
    q = model.encode(
        [r["query"] for r in rows], batch_size=256, normalize_embeddings=True, convert_to_numpy=True
    )
    index = {passage_id: n for n, passage_id in enumerate(ids)}
    out: list[dict[str, Any]] = []
    for start in range(0, len(rows), 1024):
        block = q[start : start + 1024] @ p.T
        top = np.argsort(-block, axis=1)[:, : args.range_max + 1]
        for offset, row in enumerate(rows[start : start + 1024]):
            scores = block[offset]
            ranked = [(ids[j], float(scores[j])) for j in top[offset]]
            excluded = by_file[files[row["passage_id"]]] | {row["passage_id"]}
            negative_ids = pick_negatives(
                ranked,
                float(scores[index[row["passage_id"]]]),
                excluded,
                count=args.negatives,
                range_min=args.range_min,
                range_max=args.range_max,
                margin=args.margin,
            )
            out.append({**row, "negative_ids": negative_ids, "negatives": [texts[i] for i in negative_ids]})
    return out


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--negatives", type=int, default=NEGATIVES)
    parser.add_argument("--range-min", type=int, default=RANGE_MIN)
    parser.add_argument("--range-max", type=int, default=RANGE_MAX)
    parser.add_argument("--margin", type=float, default=MARGIN)
    parser.add_argument("--max-seq-length", type=int, default=256)
    args = parser.parse_args()
    for path in (args.input, args.output):
        refuse_bench_path(path)
    rows = list(read_training_rows(args.input))
    mined = mine(rows, args)
    count = write_jsonl(args.output, mined)
    short = sum(len(r["negatives"]) < args.negatives for r in mined)
    print(
        f"wrote {count} rows with negatives to {args.output} ({short} with fewer than {args.negatives})",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
