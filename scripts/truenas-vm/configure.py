"""
Configure the TrueNAS test VM for nAI's adapter test over the JSON-RPC 2.0 WebSocket API (idempotent).

Creates: pool `tank` (mirror of the two data disks), datasets `tank/documents` (with sample text files
written here) and `tank/photos`, an SMB share for documents, an NFS share for photos, a read-only user
`nai-reader` (built-in read-only administrators group, no password, no shell, no SMB) and an API key for it.
Exports the TrueNAS web UI certificate as the CA file nAI verifies against, or, with --cert/--key/--ca from
make-cert.sh, imports an own certificate as the web UI certificate and writes its CA as that file.

Secrets: reads TRUENAS_ADMIN_USER / TRUENAS_ADMIN_PASSWORD from the secrets file and appends
TRUENAS_NAI_API_KEY to it; the file is kept at mode 600 and nothing secret is printed.

    python configure.py --secrets ~/vms/truenas-test/secrets.env --ca-out ~/vms/truenas-test/truenas-ca.pem
"""

from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import time
import uuid
from pathlib import Path
from typing import Any
from urllib import request as urlrequest

from websockets.sync.client import connect

READONLY_GROUP = "truenas_readonly_administrators"
NAI_USER = "nai-reader"
API_KEY_NAME = "nai-reader"
OWN_CERT_NAME = "nai_test_ui"

# Sample files for tank/documents, written for this test (no third-party content).
SAMPLE_FILES = {
    "README.txt": "Sample files for the nAI TrueNAS adapter test. Written for this test; no real data.\n",
    "heating-maintenance.md": (
        "# Heating maintenance\n\nThe boiler in the basement was serviced on 2026-10-14 by the local "
        "installer. Next service is due in October 2027. The pressure should stay between 1.2 and 1.8 bar.\n"
    ),
    "wifi-notes.txt": (
        "Guest Wi-Fi network name: garden-guest. The access point is in the hallway cupboard. "
        "Restart it by unplugging it for ten seconds.\n"
    ),
    "recipes/lentil-soup.md": (
        "# Lentil soup\n\n250 g red lentils, one onion, two carrots, one litre of vegetable stock, cumin. "
        "Simmer for 25 minutes and blend.\n"
    ),
}


def read_secrets(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    return values


def append_secret(path: Path, key: str, value: str) -> None:
    os.chmod(path, 0o600)
    with path.open("a") as f:
        f.write(f"{key}={value}\n")


def fetch_server_cert(host: str, port: int) -> str:
    """The server's certificate (trust on first use for the bootstrap admin session only)."""
    return ssl.get_server_certificate((host, port))


class Api:
    """Small JSON-RPC client for the admin bootstrap (password login)."""

    def __init__(self, url: str, ssl_context: ssl.SSLContext) -> None:
        self.ws = connect(url, ssl=ssl_context, open_timeout=30, max_size=2**24).__enter__()
        self.next_id = 0

    def call(self, method: str, *params: Any, timeout: float = 120) -> Any:
        self.next_id += 1
        rid = self.next_id
        self.ws.send(json.dumps({"jsonrpc": "2.0", "id": rid, "method": method, "params": list(params)}))
        while True:
            msg = json.loads(self.ws.recv(timeout=timeout))
            if msg.get("id") != rid:
                continue
            if "error" in msg:
                err = msg["error"]
                data = err.get("data") or {}
                raise RuntimeError(f"{method}: {data.get('reason') or err.get('message')}")
            return msg.get("result")

    def job(self, method: str, *params: Any, timeout: float = 600) -> Any:
        """Call a job method and wait for its result (core.job_wait is itself a job, so poll)."""
        job_id = self.call(method, *params)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            job = self.call("core.get_jobs", [["id", "=", job_id]], {"get": True})
            if job["state"] == "SUCCESS":
                return job["result"]
            if job["state"] in ("FAILED", "ABORTED"):
                raise RuntimeError(f"{method}: {job.get('error') or job['state']}")
            time.sleep(1)
        raise TimeoutError(f"{method}: job {job_id} still running after {timeout:.0f} s")

    def close(self) -> None:
        self.ws.close()


def bootstrap_context(cert_pem: str) -> ssl.SSLContext:
    # Pin the exact certificate the VM presented (no hostname check: the default cert names the VM, not
    # localhost). nAI itself never does this; it always verifies the host name.
    context = ssl.create_default_context(cadata=cert_pem)
    context.check_hostname = False
    context.verify_flags |= ssl.VERIFY_X509_PARTIAL_CHAIN  # accept the pinned leaf even if a CA signed it
    return context


def ensure_pool(api: Api) -> None:
    if api.call("pool.query", [["name", "=", "tank"]]):
        print("pool tank: exists")
        return
    disks = sorted(d["name"] for d in api.call("disk.details")["unused"])
    if len(disks) < 2:
        raise RuntimeError(f"need two unused data disks, found {disks}")
    topology = {"data": [{"type": "MIRROR", "disks": disks[:2]}]}
    api.job("pool.create", {"name": "tank", "topology": topology, "allow_duplicate_serials": False})
    print(f"pool tank: created (mirror of {', '.join(disks[:2])})")


def ensure_dataset(api: Api, name: str, share_type: str) -> None:
    if api.call("pool.dataset.query", [["id", "=", name]]):
        print(f"dataset {name}: exists")
        return
    api.call("pool.dataset.create", {"name": name, "share_type": share_type})
    print(f"dataset {name}: created")


def upload_file(base_url: str, token: str, ssl_context: ssl.SSLContext, path: str, content: bytes) -> None:
    """filesystem.put through the /_upload endpoint (multipart: JSON 'data' + 'file')."""
    boundary = uuid.uuid4().hex
    data = json.dumps({"method": "filesystem.put", "params": [path, {"mode": 0o644}]}).encode()
    body = b"".join(
        [
            f'--{boundary}\r\nContent-Disposition: form-data; name="data"\r\n\r\n'.encode(),
            data,
            f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="f"\r\n'
            "Content-Type: application/octet-stream\r\n\r\n".encode(),
            content,
            f"\r\n--{boundary}--\r\n".encode(),
        ]
    )
    req = urlrequest.Request(
        f"{base_url}/_upload",
        data=body,
        headers={
            "Authorization": f"Token {token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
    )
    with urlrequest.urlopen(req, context=ssl_context, timeout=60) as resp:
        resp.read()


def ensure_sample_files(api: Api, base_url: str, ssl_context: ssl.SSLContext) -> None:
    token = api.call("auth.generate_token", 600)
    for rel, text in SAMPLE_FILES.items():
        path = f"/mnt/tank/documents/{rel}"
        parent = os.path.dirname(path)
        if parent != "/mnt/tank/documents" and not api.call(
            "filesystem.listdir", "/mnt/tank/documents", [["name", "=", os.path.basename(parent)]]
        ):
            api.call("filesystem.mkdir", {"path": parent, "options": {"raise_chmod_error": False}})
        upload_file(base_url, token, ssl_context, path, text.encode())
    time.sleep(2)  # filesystem.put runs as a job
    names = sorted(e["name"] for e in api.call("filesystem.listdir", "/mnt/tank/documents"))
    print(f"tank/documents files: {', '.join(names)}")


def ensure_shares(api: Api) -> None:
    if not api.call("sharing.smb.query", [["name", "=", "documents"]]):
        api.call("sharing.smb.create", {"path": "/mnt/tank/documents", "name": "documents"})
    if not api.call("sharing.nfs.query", [["path", "=", "/mnt/tank/photos"]]):
        api.call("sharing.nfs.create", {"path": "/mnt/tank/photos"})
    for service in ("cifs", "nfs"):
        api.call("service.update", service, {"enable": True})
        api.job("service.control", "START", service, {"silent": False})
    print("shares: SMB documents, NFS /mnt/tank/photos; services cifs and nfs enabled")


def ensure_reader(api: Api) -> None:
    if api.call("user.query", [["username", "=", NAI_USER]]):
        print(f"user {NAI_USER}: exists")
        return
    groups = api.call("group.query", [["group", "=", READONLY_GROUP]])
    if not groups:
        raise RuntimeError(f"built-in group {READONLY_GROUP} not found")
    api.call(
        "user.create",
        {
            "username": NAI_USER,
            "full_name": "nAI read-only discovery",
            "password_disabled": True,
            "group_create": True,
            "groups": [groups[0]["id"]],
            "shell": "/usr/sbin/nologin",
            "smb": False,
        },
    )
    print(f"user {NAI_USER}: created in {READONLY_GROUP}")


def ensure_api_key(api: Api, secrets_path: Path, secrets: dict[str, str]) -> None:
    existing = api.call("api_key.query", [["name", "=", API_KEY_NAME]])
    if existing and secrets.get("TRUENAS_NAI_API_KEY"):
        print(f"API key {API_KEY_NAME}: exists (stored in the secrets file)")
        return
    for key in existing:  # exists on TrueNAS but we lost the secret: replace it
        api.call("api_key.delete", key["id"])
    created = api.call("api_key.create", {"name": API_KEY_NAME, "username": NAI_USER})
    append_secret(secrets_path, "TRUENAS_NAI_API_KEY", created["key"])
    print(f"API key {API_KEY_NAME}: created for {NAI_USER} (written to the secrets file, not shown)")


def import_ui_cert(api: Api, cert_pem: str, key_pem: str) -> None:
    """Import our own certificate (make-cert.sh) and make it the web UI certificate."""
    existing = api.call("certificate.query", [["name", "=", OWN_CERT_NAME]])
    if existing and existing[0]["certificate"].strip() == cert_pem.strip():
        cert_id = existing[0]["id"]
    else:
        if existing:  # stale copy: switch the UI back to the default before replacing it
            default = api.call("certificate.query", [["name", "=", "truenas_default"]], {"get": True})
            api.call("system.general.update", {"ui_certificate": default["id"]})
            api.job("certificate.delete", existing[0]["id"])
        created = api.job(
            "certificate.create",
            {
                "name": OWN_CERT_NAME,
                "create_type": "CERTIFICATE_CREATE_IMPORTED",
                "certificate": cert_pem,
                "privatekey": key_pem,
            },
        )
        cert_id = created["id"]
    if api.call("system.general.config")["ui_certificate"]["id"] != cert_id:
        api.call("system.general.update", {"ui_certificate": cert_id})
        api.call("system.general.ui_restart", 3)
        print(f"web UI certificate: {OWN_CERT_NAME} (imported); web UI restarting")
    else:
        print(f"web UI certificate: {OWN_CERT_NAME} (already active)")


def export_ui_cert(api: Api, ca_out: Path) -> None:
    cert_id = api.call("system.general.config")["ui_certificate"]["id"]
    cert = api.call("certificate.query", [["id", "=", cert_id]], {"get": True})
    ca_out.write_text(cert["certificate"])
    sans = cert.get("san") or []
    print(f"UI certificate {cert['name']!r} (SAN {sans}) exported to {ca_out}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=8443)
    parser.add_argument("--secrets", type=Path, required=True)
    parser.add_argument("--ca-out", type=Path, required=True, help="where to write the CA file for nAI")
    parser.add_argument("--cert", type=Path, help="own web UI certificate (make-cert.sh server.pem)")
    parser.add_argument("--key", type=Path, help="its private key (make-cert.sh server.key)")
    parser.add_argument("--ca", type=Path, help="the CA that signed --cert (make-cert.sh ca.pem)")
    args = parser.parse_args()
    own_cert = (args.cert, args.key, args.ca)
    if any(own_cert) and not all(own_cert):
        parser.error("--cert, --key and --ca go together")

    secrets = read_secrets(args.secrets)
    context = bootstrap_context(fetch_server_cert(args.host, args.port))
    base_url = f"https://{args.host}:{args.port}"
    api = Api(f"wss://{args.host}:{args.port}/api/current", context)
    try:
        login = api.call(
            "auth.login_ex",
            {
                "mechanism": "PASSWORD_PLAIN",
                "username": secrets["TRUENAS_ADMIN_USER"],
                "password": secrets["TRUENAS_ADMIN_PASSWORD"],
            },
        )
        if login.get("response_type") != "SUCCESS":
            raise RuntimeError(f"admin login failed: {login.get('response_type')}")
        print(f"TrueNAS {api.call('system.version')}")
        ensure_pool(api)
        ensure_dataset(api, "tank/documents", "SMB")
        ensure_dataset(api, "tank/photos", "GENERIC")
        ensure_sample_files(api, base_url, context)
        ensure_shares(api)
        ensure_reader(api)
        ensure_api_key(api, args.secrets, secrets)
        if args.cert and args.key and args.ca:
            import_ui_cert(api, args.cert.read_text(), args.key.read_text())
            args.ca_out.write_text(args.ca.read_text())
            print(f"CA file for nAI: {args.ca_out} (copy of {args.ca})")
        else:
            export_ui_cert(api, args.ca_out)
    finally:
        api.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
