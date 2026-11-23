"""
Turn a folder of documents into training passages, exactly the way nAI chunks them.

Uses nai-core's own extractors and chunker (apps/nai-core/app/utils), so passages
look like what the embedding model sees in production: "<context header>\\n<chunk text>".
Every passage records the folder's license and source (lab principle 2).

    python training/embed/make_passages.py --input data/synthetic-corpus \\
        --license CC0-1.0 --source "synthetic NAS corpus v1" --author qwen2.5:7b \\
        --output data/passages.jsonl

Refuses anything inside evals/nai-bench (no-contamination rule).
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from common import NAI_CORE, check_author, detect_language, refuse_bench_path, write_jsonl

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
    args = parser.parse_args()

    check_author(args.author)
    refuse_bench_path(args.input)
    refuse_bench_path(args.output)
    root = args.input.resolve()
    rows = (row for path in iter_files(root) for row in passages_for(path, root, args))
    count = write_jsonl(args.output, rows)
    print(f"wrote {count} passages to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
