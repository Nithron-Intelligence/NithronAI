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

from common import NAI_BENCH, refuse_bench_path

USER_AGENT = "nithron-vane-data/1.0 (training corpus builder; curl)"
FORBIDDEN_LICENSE = re.compile(r"by-?sa|share-?alike|\bnc\b|non-?commercial|\bnd\b|no-?deriv", re.I)


def check_license(license_text: str) -> None:
    if FORBIDDEN_LICENSE.search(license_text):
        raise ValueError(
            f"license {license_text!r} is not allowed for Vane 1 training data (no CC-BY-SA/NC/ND)"
        )


def bench_source_urls() -> set[str]:
    """Normalized URLs of every document nai-bench uses (v0 and v1 manifests, v1 sources list)."""
    urls: set[str] = set()
    for path in (
        NAI_BENCH / "corpus-manifest.json",
        NAI_BENCH / "v1" / "corpus-manifest.json",
        NAI_BENCH / "v1" / "sources.json",
    ):
        if path.exists():
            for entry in json.loads(path.read_text(encoding="utf-8")):
                url = entry.get("source_url") or entry.get("url")
                if url:
                    urls.add(normalize_url(url))
    return urls


def normalize_url(url: str) -> str:
    """Scheme, ``www.`` and trailing slashes don't make a different document."""
    return re.sub(r"^https?://(www\.)?", "", url.strip()).rstrip("/").lower()


def refuse_bench_source(url: str, bench_urls: set[str]) -> None:
    """Raise if ``url`` is a document nai-bench uses: training must use other statutes and books."""
    own = normalize_url(url)
    if own in bench_urls or any(own.startswith(b + "/") for b in bench_urls):  # bench "bgb/" = whole BGB
        raise ValueError(f"{url} is a nai-bench document; pick another source (no-contamination rule)")


def download(url: str, headers: dict[str, str], target: Path) -> None:
    cmd = ["curl", "-fsSL", "--retry", "3", "--max-time", "180", "-A", USER_AGENT, "-o", str(target)]
    for name, value in headers.items():
        cmd += ["-H", f"{name}: {value}"]
    subprocess.run([*cmd, url], check=True)


def fetch(sources: list[dict[str, Any]], out: Path) -> list[dict[str, Any]]:
    refuse_bench_path(out)
    bench_urls = bench_source_urls()
    entries = []
    for source in sources:
        check_license(source["license"])
        refuse_bench_source(source["url"], bench_urls)
        target = out / source["group"] / source["file"]
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            try:
                download(source["url"], source.get("headers", {}), target)
            except subprocess.CalledProcessError as e:
                target.unlink(missing_ok=True)  # never keep a partial file
                print(f"  FAILED ({e.returncode}) {source['url']}: skipped", file=sys.stderr)
                continue
            finally:
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
