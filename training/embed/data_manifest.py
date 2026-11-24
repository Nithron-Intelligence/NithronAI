"""
Write a manifest (path, bytes, SHA-256, JSONL row count) of a training-data folder that stays outside git.

The data itself lives in git-ignored ``training/data/``; the manifest goes into ``training/manifests/`` so a
commit pins exactly which files a run used, and anyone with the same inputs can check them.

    python training/embed/data_manifest.py --data training/data/vane1 --out training/manifests/vane1-data.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

from common import refuse_bench_path

CHUNK = 1 << 20


def file_entry(path: Path, root: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    rows = 0
    with path.open("rb") as handle:
        while block := handle.read(CHUNK):
            digest.update(block)
            rows += block.count(b"\n")
    return {
        "path": path.relative_to(root).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": digest.hexdigest(),
        "rows": rows if path.suffix == ".jsonl" else None,
    }


def build(root: Path) -> dict[str, Any]:
    refuse_bench_path(root)
    files = [
        file_entry(p, root) for p in sorted(root.rglob("*")) if p.is_file() and not p.name.startswith(".")
    ]
    return {
        "folder": root.as_posix(),
        "created": date.today().isoformat(),
        "files": files,
        "total_bytes": sum(f["bytes"] for f in files),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    manifest = build(args.data)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(manifest, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(manifest['files'])} files, {manifest['total_bytes']} bytes -> {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
