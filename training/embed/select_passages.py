"""
Combine passage files into one training input, taking a seeded random sample from each (reproducible).

    python training/embed/select_passages.py --out passages-pilot.jsonl --seed 13 \
        synthetic.jsonl:all public-eu.jsonl:110 public-de.jsonl:50

``FILE:N`` takes N passages from FILE (``all`` takes every passage); for files with a ``language`` field the
sample is spread evenly over languages. Every row goes through ``common.check_training_row``.
"""

from __future__ import annotations

import argparse
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from common import read_training_rows, write_jsonl


def sample(rows: list[dict[str, Any]], n: int, rng: random.Random) -> list[dict[str, Any]]:
    by_lang: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_lang[str(row.get("language"))].append(row)
    langs = sorted(by_lang)
    out: list[dict[str, Any]] = []
    for i, lang in enumerate(langs):
        share = n // len(langs) + (1 if i < n % len(langs) else 0)
        pool = by_lang[lang]
        out += rng.sample(pool, min(share, len(pool)))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=13)
    parser.add_argument("inputs", nargs="+", help="FILE:N or FILE:all")
    args = parser.parse_args()
    rng = random.Random(args.seed)
    selected: list[dict[str, Any]] = []
    for spec in args.inputs:
        name, _, count = spec.rpartition(":")
        rows = list(read_training_rows(Path(name)))
        chosen = rows if count == "all" else sample(rows, int(count), rng)
        print(f"{len(chosen):>5} of {len(rows):>5} from {name}")
        selected += chosen
    print(f"wrote {write_jsonl(args.out, selected)} passages to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
