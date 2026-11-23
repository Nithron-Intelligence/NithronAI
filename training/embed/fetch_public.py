"""
Download public training texts for Vane 1 (byte-exact, curl) and record them in a manifest.

Sources (URL, license, author, group) come from a JSON list (e.g. training/sources/vane1-pilot-public.json).
Only public domain, CC0, CC-BY and EU reuse texts are allowed (data rule, docs/lab/MODEL_AND_DATA_LICENSES.md):
the script refuses CC-BY-SA, NC and ND licenses and anything under evals/nai-bench. Files land in
``<out>/<group>/<file>``; the manifest records URL, license, author, retrieval date, size and SHA-256.

    python training/embed/fetch_public.py --sources training/sources/vane1-pilot-public.json \
        --out training/data/vane1-pilot/public --manifest training/manifests/vane1-pilot-public.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

from common import refuse_bench_path

USER_AGENT = "nithron-vane-data/1.0 (training corpus builder; curl)"
FORBIDDEN_LICENSE = re.compile(r"by-?sa|share-?alike|\bnc\b|non-?commercial|\bnd\b|no-?deriv", re.I)


def check_license(license_text: str) -> None:
    if FORBIDDEN_LICENSE.search(license_text):
        raise ValueError(
            f"license {license_text!r} is not allowed for Vane 1 training data (no CC-BY-SA/NC/ND)"
        )


def download(url: str, headers: dict[str, str], target: Path) -> None:
    cmd = ["curl", "-fsSL", "--retry", "3", "--max-time", "180", "-A", USER_AGENT, "-o", str(target)]
    for name, value in headers.items():
        cmd += ["-H", f"{name}: {value}"]
    subprocess.run([*cmd, url], check=True)


def fetch(sources: list[dict[str, Any]], out: Path) -> list[dict[str, Any]]:
    refuse_bench_path(out)
    entries = []
    for source in sources:
        check_license(source["license"])
        target = out / source["group"] / source["file"]
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            download(source["url"], source.get("headers", {}), target)
            time.sleep(1.0)
        data = target.read_bytes()
        entries.append(
            {
                "file": f"{source['group']}/{source['file']}",
                "group": source["group"],
                "language": source["language"],
                "license": source["license"],
                "author": source["author"],
                "source": source["source"],
                "source_url": source["url"],
                "retrieved": date.today().isoformat(),
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "use": "training",
            }
        )
        print(f"{len(data):>9} B  {source['group']}/{source['file']}")
    return entries


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    entries = fetch(json.loads(args.sources.read_text(encoding="utf-8")), args.out)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(entries, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(entries)} files, {sum(e['bytes'] for e in entries)} bytes; manifest {args.manifest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
