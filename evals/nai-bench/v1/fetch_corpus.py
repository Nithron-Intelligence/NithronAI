"""
nai-bench v1 corpus fetcher
===========================

Downloads the third-party corpus files listed in ``sources.json`` with curl, stores them under
``corpus/`` and records each one in ``corpus-manifest.json``: source URL, license, author, retrieval date,
SHA-256 (and, for Project Gutenberg books, the SHA-256 of the download before the one documented
transform). Files are stored byte-exact as downloaded, except:

- ``gutenberg-strip``: Project Gutenberg's header and licence (everything up to and including the
  ``*** START OF ...`` line, and from the ``*** END OF ...`` line on) are removed, as V1_PLAN.md requires;
  the body is kept byte-exact.

Only openly reusable sources belong in ``sources.json`` (official texts, US federal works, public-domain
books); fictional documents are written by ``build_corpus.py`` and keep their own manifest entries.

    python evals/nai-bench/v1/fetch_corpus.py            # fetch what is missing, update the manifest
    python evals/nai-bench/v1/fetch_corpus.py --check    # verify every corpus file against the manifest
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import time
from datetime import date
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
SOURCES = HERE / "sources.json"
MANIFEST = HERE / "corpus-manifest.json"
CORPUS = HERE / "corpus"
USER_AGENT = "nai-bench-corpus/1.0 (benchmark corpus builder; curl)"
FORMATS = {".html": "html", ".htm": "html", ".txt": "text", ".md": "text", ".pdf": "pdf", ".xml": "text"}
PAUSE_SECONDS = 1.0  # between downloads, to be polite to the source servers


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def download(url: str, headers: dict[str, str]) -> bytes:
    """Fetch with curl (follows redirects, fails on HTTP errors)."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "download"
        cmd = ["curl", "-fsSL", "--retry", "3", "--max-time", "180", "-A", USER_AGENT, "-o", str(out), url]
        for name, value in headers.items():
            cmd[1:1] = ["-H", f"{name}: {value}"]
        subprocess.run(cmd, check=True)
        return out.read_bytes()


def gutenberg_strip(data: bytes) -> bytes:
    """The book body between Project Gutenberg's START and END marker lines (both removed)."""
    lines = data.splitlines(keepends=True)
    start = next((i for i, line in enumerate(lines) if line.startswith(b"*** START OF")), None)
    end = next((i for i, line in enumerate(lines) if line.startswith(b"*** END OF")), None)
    if start is None or end is None or end <= start:
        raise ValueError("Project Gutenberg START/END markers not found")
    body = b"".join(lines[start + 1 : end]).strip(b"\r\n") + b"\n"
    if b"Project Gutenberg" in body[:2000] or b"Project Gutenberg" in body[-2000:]:
        raise ValueError("Project Gutenberg text left at the start or end of the body")
    return body


TRANSFORMS = {"gutenberg-strip": gutenberg_strip}


def pdf_pages(data: bytes) -> int | None:
    try:
        from io import BytesIO

        from pypdf import PdfReader
    except ImportError:
        return None
    return len(PdfReader(BytesIO(data)).pages)


def manifest_entry(source: dict[str, Any], raw: bytes, stored: bytes, retrieved: str) -> dict[str, Any]:
    suffix = Path(source["file"]).suffix.lower()
    entry = {
        "file": source["file"],
        "format": FORMATS.get(suffix, suffix.lstrip(".")),
        "language": source["language"],
        "kind": source["kind"],
        "pages": pdf_pages(stored) if suffix == ".pdf" else None,
        "license": source["license"],
        "source": source["source"],
        "source_url": source["url"],
        "author": source["author"],
        "retrieved": retrieved,
        "provenance": source["provenance"],
        "use": "eval-only",
        "sha256": sha256(stored),
    }
    if source.get("transform"):
        entry["transform"] = source["transform"]
        entry["download_sha256"] = sha256(raw)
    return entry


def load_manifest() -> list[dict[str, Any]]:
    data: list[dict[str, Any]] = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else []
    return data


def save_manifest(entries: list[dict[str, Any]]) -> None:
    entries = sorted(entries, key=lambda e: e["file"])
    MANIFEST.write_text(json.dumps(entries, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def fetch(only: str | None, refresh: bool) -> int:
    sources: list[dict[str, Any]] = json.loads(SOURCES.read_text(encoding="utf-8"))
    entries = {e["file"]: e for e in load_manifest()}
    fetched = 0
    for source in sources:
        if only and not source["file"].startswith(only):
            continue
        target = CORPUS / source["file"]
        if target.exists() and source["file"] in entries and not refresh:
            continue
        raw = download(source["url"], source.get("headers", {}))
        stored = TRANSFORMS[source["transform"]](raw) if source.get("transform") else raw
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(stored)
        entries[source["file"]] = manifest_entry(source, raw, stored, date.today().isoformat())
        save_manifest(list(entries.values()))  # after every file, so an interrupted run keeps its work
        fetched += 1
        print(f"{len(stored):>9} B  {source['file']}")
        time.sleep(PAUSE_SECONDS)
    print(f"fetched {fetched} file(s); manifest has {len(entries)} entries")
    return 0


def check() -> list[str]:
    """Problems: files missing, changed, or not in the manifest (empty list = all good)."""
    entries = load_manifest()
    problems = []
    known = set()
    for entry in entries:
        known.add(entry["file"])
        path = CORPUS / entry["file"]
        if not path.is_file():
            problems.append(f"missing: {entry['file']}")
        elif sha256(path.read_bytes()) != entry["sha256"]:
            problems.append(f"changed: {entry['file']}")
        for field in ("license", "source", "author", "language", "kind", "sha256"):
            if not entry.get(field):
                problems.append(f"{entry['file']}: no {field}")
    if CORPUS.exists():
        for path in sorted(p for p in CORPUS.rglob("*") if p.is_file()):
            rel = path.relative_to(CORPUS).as_posix()
            if rel not in known:
                problems.append(f"not in the manifest: {rel}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--check", action="store_true", help="verify the corpus against the manifest (no network)"
    )
    parser.add_argument("--only", help="only sources whose corpus path starts with this prefix")
    parser.add_argument("--refresh", action="store_true", help="download again even if the file exists")
    args = parser.parse_args(argv)
    if args.check:
        problems = check()
        print("\n".join(problems) if problems else f"ok: {len(load_manifest())} files match the manifest")
        return 1 if problems else 0
    return fetch(args.only, args.refresh)


if __name__ == "__main__":
    sys.exit(main())
