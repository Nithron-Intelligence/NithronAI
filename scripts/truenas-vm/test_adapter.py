"""
Manual test of nAI's TrueNAS adapter against a real TrueNAS (the VM from start-vm.sh + configure.py).

Uses only the read-only API key (TRUENAS_NAI_API_KEY from the secrets file) and nAI's own adapter code.
Prints one PASS/FAIL line per check and never prints the key. Run with nai-core's venv:

    apps/nai-core/.venv/bin/python scripts/truenas-vm/test_adapter.py \
        --secrets ~/vms/truenas-test/secrets.env --ca-file ~/vms/truenas-test/truenas-ca.pem

Checks: discovery with the CA file (version, SMB + NFS shares, mounted vs "nas-api"); the allow-list refuses
a non-read-only method before sending it; TrueNAS itself refuses a write for this user; without the CA file
the TLS handshake fails (no insecure fallback); ws:// is refused; a wrong key is rejected; the key appears in
no log record and no output.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import logging
import ssl
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps" / "nai-core"))

from app.nas.truenas import TrueNASAdapter, TrueNASClient, TrueNASError


def read_key(path: Path) -> str:
    for line in path.read_text().splitlines():
        if line.startswith("TRUENAS_NAI_API_KEY="):
            return line.partition("=")[2].strip()
    raise SystemExit(f"TRUENAS_NAI_API_KEY not found in {path} (run configure.py first)")


class Results:
    def __init__(self) -> None:
        self.failed = 0

    def check(self, name: str, ok: bool, detail: str = "") -> None:
        self.failed += 0 if ok else 1
        print(f"{'PASS' if ok else 'FAIL'}  {name}{': ' + detail if detail else ''}")


def run_checks(url: str, key: str, ca_file: str, results: Results) -> None:
    with tempfile.TemporaryDirectory() as shares_root:
        Path(shares_root, "documents").mkdir()  # only documents is "mounted" into the app
        adapter = TrueNASAdapter(url=url, api_key=key, ca_file=ca_file)

        status = adapter.platform_status()
        results.check(
            "discovery: connected with CA file",
            status.get("connected") is True and bool(status.get("version")),
            f"version={status.get('version')} hostname={status.get('hostname')}",
        )
        found = {c.name: c for c in adapter.discover_shares([shares_root], [])}
        docs, photos = found.get("documents"), found.get("photos")
        results.check(
            "discovery: SMB documents (mounted) and NFS photos (nas-api, not mounted)",
            bool(docs and docs.mounted and photos and photos.source == "nas-api" and not photos.mounted),
            ", ".join(
                f"{c.name}:{c.source}:{'mounted' if c.mounted else 'not mounted'}" for c in found.values()
            ),
        )

    sent: list[str] = []

    def recording_connect(u: str, context: ssl.SSLContext, timeout: float) -> Any:
        from websockets.sync.client import connect

        conn = connect(u, ssl=context, open_timeout=timeout, close_timeout=timeout).__enter__()
        original_send = conn.send

        def send(message: str) -> None:
            sent.append(message)
            original_send(message)

        conn.send = send  # type: ignore[method-assign,assignment]
        return conn

    try:
        with TrueNASClient(url, key, ca_file, connect=recording_connect) as api:
            before = len(sent)
            try:
                api.call("user.query")
                refused = False
            except TrueNASError as e:
                refused = "allow-list" in str(e)
            results.check("allow-list refuses user.query before sending it", refused and len(sent) == before)

            try:  # bypass the allow-list on purpose: TrueNAS must refuse writes for the read-only user
                api._request("pool.dataset.create", [{"name": "tank/nai-write-probe"}])
                server_refused, detail = False, "dataset was created!"
            except TrueNASError as e:
                server_refused, detail = True, str(e)[:120]
            results.check("TrueNAS refuses a write for the read-only user", server_refused, detail)
    except TrueNASError as e:
        results.check("allow-list and server-side write checks", False, f"no connection: {str(e)[-110:]}")

    no_ca = TrueNASAdapter(url=url, api_key=key).platform_status()
    detail = str(no_ca.get("detail", ""))
    results.check(
        "without CA file: TLS verification fails (no insecure fallback)",
        no_ca.get("connected") is False and "CERTIFICATE_VERIFY_FAILED" in detail,
        detail[-110:],
    )

    try:
        TrueNASClient(url.replace("wss://", "ws://", 1), key, ca_file)
        insecure_refused = False
    except TrueNASError:
        insecure_refused = True
    results.check("ws:// URL refused", insecure_refused)

    wrong = TrueNASAdapter(url=url, api_key="1-" + "x" * 64, ca_file=ca_file).platform_status()
    results.check(
        "wrong key rejected",
        wrong.get("connected") is False and "rejected" in str(wrong.get("detail", "")),
        str(wrong.get("detail", ""))[:110],
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--url", default="wss://localhost:8443/api/current")
    parser.add_argument("--secrets", type=Path, required=True)
    parser.add_argument("--ca-file", required=True)
    args = parser.parse_args()
    key = read_key(args.secrets)

    log_buffer = io.StringIO()
    handler = logging.StreamHandler(log_buffer)
    handler.setFormatter(logging.Formatter("%(name)s %(levelname)s %(message)s"))
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)  # websockets logs every frame at DEBUG: the key must not show up there

    results = Results()
    output = io.StringIO()
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
        run_checks(args.url, key, args.ca_file, results)
    text = output.getvalue()
    print(text, end="")

    secret_part = key.partition("-")[2] or key
    logs = log_buffer.getvalue()
    needles = (key, secret_part, secret_part[:12])  # the prefix catches truncated frame logs
    leaked = any(n in logs or n in text for n in needles)
    results.check(
        "key absent from all log records (DEBUG) and output",
        not leaked,
        f"{len(logs.splitlines())} log lines checked",
    )
    print(f"{'ALL PASSED' if not results.failed else f'{results.failed} FAILED'}")
    return 1 if results.failed else 0


if __name__ == "__main__":
    sys.exit(main())
