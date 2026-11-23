"""
Check nAI running as a TrueNAS custom app (installed by install_app.py), through its HTTP API.

Reach the app through an SSH tunnel (the VM only forwards the TrueNAS ports), e.g.
    ssh -i ~/vms/truenas-test/ssh/id_ed25519 -p 2222 -fN -L 18000:127.0.0.1:8000 truenas_admin@localhost
then
    python test_app.py --url http://127.0.0.1:18000 --secrets ~/vms/truenas-test/secrets.env

Creates the first nAI account (the admin; its password is generated into the secrets file, mode 600, and
never printed), then checks: /health (embeddings on), /sources/discover (platform truenas, connected
through the API with the read-only key and the CA file, SMB documents mounted, NFS photos not mounted), adds
and indexes /shares/documents, and asks two questions about the sample files (extractive, no LLM).
Prints one PASS/FAIL line per check.
"""

from __future__ import annotations

import argparse
import os
import secrets as pysecrets
import sys
import time
from pathlib import Path
from typing import Any

import httpx

ADMIN_USER = "nai-admin"
QUESTIONS = (  # (question, a string the extractive answer or its top citation must contain, expected file)
    ("Where is the guest Wi-Fi access point?", "hallway cupboard", "wifi-notes.txt"),
    ("When is the next boiler service due?", "October 2027", "heating-maintenance.md"),
)


def admin_password(path: Path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("NAI_ADMIN_PASSWORD="):
            return line.partition("=")[2].strip()
    password = pysecrets.token_urlsafe(18)
    os.chmod(path, 0o600)
    with path.open("a", encoding="utf-8") as f:
        f.write(f"NAI_ADMIN_PASSWORD={password}\n")
    return password


class Results:
    def __init__(self) -> None:
        self.failed = 0

    def check(self, name: str, ok: bool, detail: str = "") -> None:
        self.failed += 0 if ok else 1
        print(f"{'PASS' if ok else 'FAIL'}  {name}{': ' + detail if detail else ''}")


def login(client: httpx.Client, password: str) -> None:
    if client.get("/auth/status").json().get("setup_required"):  # no users yet: the first one is the admin
        client.post(
            "/auth/register",
            json={"username": ADMIN_USER, "email": "admin@nai.example", "password": password},
        ).raise_for_status()
    token = client.post("/auth/login", json={"username": ADMIN_USER, "password": password})
    token.raise_for_status()
    client.headers["Authorization"] = f"Bearer {token.json()['access_token']}"


def index_documents(client: httpx.Client) -> dict[str, Any]:
    sources = {s["path"]: s for s in client.get("/sources").json()}
    source = sources.get("/shares/documents")
    if source is None:
        created = client.post("/sources", json={"name": "documents", "path": "/shares/documents"})
        created.raise_for_status()
        source = created.json()
    client.post(f"/sources/{source['id']}/scan")
    for _ in range(120):
        source = next(s for s in client.get("/sources").json() if s["id"] == source["id"])
        if not source["scanning"] and source["last_scan_status"] not in ("never", "running", "queued"):
            break
        time.sleep(2)
    return source


def run(url: str, secrets_file: Path) -> int:
    results = Results()
    with httpx.Client(base_url=url, timeout=120) as client:
        health = client.get("/health")
        login(client, admin_password(secrets_file))
        info = client.get("/health/detailed").json()
        embeddings = info.get("embeddings") or {}
        results.check(
            "nAI is up as the TrueNAS app, with semantic search",
            health.status_code == 200 and bool(embeddings.get("model")),
            f"version {info.get('version')}, embeddings {embeddings.get('provider')}/{embeddings.get('model')}",
        )

        discovery = client.get("/sources/discover").json()
        status = discovery.get("status") or {}
        shares = {s["name"]: s for s in discovery.get("shares", [])}
        results.check(
            "discovery: platform truenas, connected with the read-only key and the CA file",
            discovery.get("platform") == "truenas" and status.get("connected") is True,
            f"version={status.get('version')} hostname={status.get('hostname')} detail={status.get('detail')}",
        )
        docs, photos = shares.get("documents"), shares.get("photos")
        results.check(
            "discovery: documents and photos (both mounted read-only in the app)",
            bool(docs and docs.get("mounted") and photos and photos.get("mounted")),
            ", ".join(
                f"{n}:{s.get('source')}:{'mounted' if s.get('mounted') else 'not mounted'}"
                for n, s in shares.items()
            ),
        )

        source = index_documents(client)
        results.check(
            "indexing /shares/documents",
            source["last_scan_status"] in ("success", "ok", "completed") and source["document_count"] >= 4,
            f"status={source['last_scan_status']} documents={source['document_count']} error={source.get('last_error')}",
        )
        for question, needle, expected_file in QUESTIONS:
            reply = client.post("/ask", json={"question": question, "use_llm": False, "top_k": 3}).json()
            cited = [c.get("doc_path") or c.get("filename") or "" for c in reply.get("citations", [])]
            text = reply.get("answer", "")
            results.check(
                f"answer: {question}",
                needle.lower() in text.lower() and any(expected_file in str(c) for c in cited[:1]),
                f"top citation {Path(str(cited[0])).name if cited else None}; method {reply.get('method')}",
            )
    print("ALL PASSED" if not results.failed else f"{results.failed} FAILED")
    return 1 if results.failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--url", default="http://127.0.0.1:18000")
    parser.add_argument("--secrets", type=Path, required=True)
    args = parser.parse_args()
    return run(args.url, args.secrets)


if __name__ == "__main__":
    sys.exit(main())
