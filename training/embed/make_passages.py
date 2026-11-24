"""
Turn a folder of documents into training passages, exactly the way nAI chunks them.

Uses nai-core's own extractors and chunker (apps/nai-core/app/utils), so passages
look like what the embedding model sees in production: "<context header>\\n<chunk text>".
Every passage records the folder's license and source (lab principle 2).

    python training/embed/make_passages.py --input data/synthetic-corpus \\
        --license CC0-1.0 --source "synthetic NAS corpus v1" --author qwen2.5:7b \\
        --output data/passages.jsonl

Refuses anything inside evals/nai-bench (no-contamination rule).

``--holdout-output FILE --holdout-share 0.05`` sets whole documents aside (chosen by a hash of the relative path,
so the choice is stable across runs and never splits a file; all language versions of one document, e.g.
``CELEX_…_DE.html`` and ``CELEX_…_FR.html``, go the same way) for the held-out evaluation slice of real
documents (docs/lab/vane1-data-plan.md); their passages go to FILE instead of ``--output``.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from common import (
    NAI_CORE,
    check_author,
    detect_language,
    is_holdout,
    refuse_bench_path,
    write_jsonl,
)

sys.path.insert(0, str(NAI_CORE))

from app.utils.extractors import extract
from app.utils.text import chunk_sections

MIN_PASSAGE_CHARS = 80
SKIP_DIRS = {".git", ".snapshots", "@eaDir", "#recycle", "node_modules"}


def iter_files(root: Path) -> Iterator[Path]:
    for path in sorted(root.rglob("*")):
        parts = path.relative_to(root).parts  # only below the root: the root itself may sit in a dot-folder
        if path.is_file() and not any(part in SKIP_DIRS or part.startswith(".") for part in parts):
            yield path


def passages_for(path: Path, root: Path, args: argparse.Namespace) -> Iterator[dict[str, Any]]:
    rel = path.relative_to(root).as_posix()
    extracted = extract(str(path), ocr=args.ocr, ocr_languages=args.ocr_languages)
    title = extracted.metadata.get("title")
    for index, chunk in enumerate(
        chunk_sections(extracted.sections, rel, title=title, max_chars=args.max_chars)
    ):
        if len(chunk.text) < MIN_PASSAGE_CHARS:
            continue
        text = (
            f"{chunk.context}\n{chunk.text}" if chunk.context else chunk.text
        )  # = EmbeddingService.chunk_input
        yield {
            # source + path + index: unique across several input folders with the same relative paths
            "id": hashlib.sha256(f"{args.source}:{rel}:{index}".encode()).hexdigest()[:16],
            "file": rel,
            "page": chunk.page,
            "heading": chunk.heading,
            "text": text,
            "language": args.language or detect_language(chunk.text),
            "license": args.license,
            "source": args.source,
            "author": args.author,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract and chunk documents into training passages")
    parser.add_argument("--input", type=Path, required=True, help="folder of documents")
    parser.add_argument("--output", type=Path, required=True, help="passages.jsonl")
    parser.add_argument("--license", required=True, help="SPDX id or description of the folder's license")
    parser.add_argument("--source", required=True, help="where the documents come from (provenance)")
    parser.add_argument(
        "--author",
        required=True,
        help="who wrote the documents: a teacher model (e.g. qwen2.5:7b), 'public-domain', or a person/org",
    )
    parser.add_argument(
        "--language", default=None, help="language of the whole folder (default: detect per passage)"
    )
    parser.add_argument("--max-chars", type=int, default=1000, help="chunk size (nAI default: 1000)")
    parser.add_argument("--ocr", action="store_true", help="OCR scans and images (needs tesseract)")
    parser.add_argument("--ocr-languages", default="eng+deu")
    parser.add_argument("--holdout-output", type=Path, help="passages of held-out documents (eval only)")
    parser.add_argument("--holdout-share", type=float, default=0.0, help="share of documents to hold out")
    args = parser.parse_args()
    if args.holdout_share and not args.holdout_output:
        parser.error("--holdout-share needs --holdout-output")

    check_author(args.author)
    refuse_bench_path(args.input)
    refuse_bench_path(args.output)
    root = args.input.resolve()
    files = list(iter_files(root))
    held = [f for f in files if is_holdout(f.relative_to(root).as_posix(), args.holdout_share)]
    kept = [f for f in files if f not in held]
    count = write_jsonl(args.output, (row for path in kept for row in passages_for(path, root, args)))
    print(f"wrote {count} passages from {len(kept)} files to {args.output}")
    if args.holdout_output:
        refuse_bench_path(args.holdout_output)
        rows = ({**row, "use": "eval-only"} for path in held for row in passages_for(path, root, args))
        held_count = write_jsonl(args.holdout_output, rows)
        print(f"held out {held_count} passages from {len(held)} files to {args.holdout_output} (eval-only)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
