"""
Install nAI as a TrueNAS custom app in the test VM, following packaging/truenas/README.md (idempotent).

Steps a user does in the UI, done here over the JSON-RPC API: Apps pool, an Apps-preset dataset for nAI's
data, read access for the `apps` group on the searched datasets, the CA file in nAI's data dataset, and
"Install via YAML" with packaging/truenas/compose.yaml (paths and settings filled in). Test plumbing that a
user doesn't need: an SSH key for truenas_admin with passwordless `sudo docker` (to `docker load` a locally
built image) and SSH TCP forwarding (to reach the app's port from the host), see README.md here.

The API key goes into the app's configuration on TrueNAS only; it is read from the secrets file and never
printed.

    python install_app.py --secrets ~/vms/truenas-test/secrets.env --ca ~/vms/truenas-test/pki/ca.pem \
        --ssh-pubkey ~/vms/truenas-test/ssh/id_ed25519.pub --image nai-core:lab-stage-0
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

import configure

REPO = Path(__file__).resolve().parents[2]
COMPOSE = REPO / "packaging" / "truenas" / "compose.yaml"
APP_NAME = "nai"
APPS_GROUP = "apps"


def ensure_ssh_access(api: configure.Api, pubkey: str) -> None:
    """Test plumbing: key login for truenas_admin and passwordless `sudo docker` (for `docker load`)."""
    user = api.call("user.query", [["username", "=", "truenas_admin"]], {"get": True})
    changes: dict[str, Any] = {}
    if (user.get("sshpubkey") or "").strip() != pubkey.strip():
        changes["sshpubkey"] = pubkey.strip()
    if "/usr/bin/docker" not in (user.get("sudo_commands_nopasswd") or []):
        changes["sudo_commands_nopasswd"] = [*(user.get("sudo_commands_nopasswd") or []), "/usr/bin/docker"]
    if changes:
        api.call("user.update", user["id"], changes)
    if not api.call("ssh.config").get("tcpfwd"):
        api.call("ssh.update", {"tcpfwd": True})  # for the tunnel to the app's port (test_app.py)
    api.call("service.update", "ssh", {"enable": True})
    api.job("service.control", "RESTART", "ssh", {"silent": False})
    print("ssh: key login for truenas_admin, passwordless sudo for /usr/bin/docker, TCP forwarding on")


def ensure_apps_pool(api: configure.Api) -> None:
    if api.call("docker.config").get("pool") == "tank":
        print("apps pool: tank (already)")
        return
    api.job("docker.update", {"pool": "tank"}, timeout=900)
    print("apps pool: tank")


def ensure_app_datasets(api: configure.Api) -> None:
    configure.ensure_dataset(api, "tank/apps", "GENERIC")
    configure.ensure_dataset(api, "tank/apps/nai", "APPS")


def ensure_group_read(api: configure.Api, path: str) -> None:
    """Guide step 1.2: the apps group can read the dataset (an NFSv4 ACL entry, or POSIX 'other' read)."""
    acl = api.call("filesystem.getacl", path, False)
    if acl["acltype"] != "NFS4":
        stat = api.call("filesystem.stat", path)
        print(
            f"{path}: POSIX ACL, mode {oct(stat['mode'] & 0o777)} (others can read: {bool(stat['mode'] & 0o004)})"
        )
        return
    gid = api.call("group.query", [["group", "=", APPS_GROUP]], {"get": True})["gid"]
    entries: list[dict[str, Any]] = []
    for ace in acl["acl"]:  # getacl names groups by gid ("who" is empty); drop exact duplicates
        if ace not in entries:
            entries.append(ace)
    has_apps = any(
        a.get("tag") == "GROUP" and (a.get("id") == gid or a.get("who") == APPS_GROUP) for a in entries
    )
    if has_apps and len(entries) == len(acl["acl"]):
        print(f"{path}: apps group already in the ACL")
        return
    if not has_apps:
        entries.append(
            {
                "tag": "GROUP",
                "id": gid,
                "type": "ALLOW",
                "perms": {"BASIC": "READ"},
                "flags": {"BASIC": "INHERIT"},
            }
        )
    api.job(
        "filesystem.setacl",
        {"path": path, "dacl": entries, "acltype": "NFS4", "options": {"recursive": True}},
    )
    print(
        f"{path}: {'added a Read entry for' if not has_apps else 'removed a duplicate entry of'} group apps"
    )


def put_ca_file(api: configure.Api, base_url: str, context: Any, ca_pem: bytes) -> None:
    token = api.call("auth.generate_token", 600)
    configure.upload_file(base_url, token, context, "/mnt/tank/apps/nai/truenas-ca.pem", ca_pem)
    time.sleep(2)
    print("CA file: /mnt/tank/apps/nai/truenas-ca.pem (= /app/data/truenas-ca.pem in the app)")


def compose_text(image: str, url: str, api_key: str) -> str:
    """packaging/truenas/compose.yaml with the values a user fills in."""
    text = COMPOSE.read_text(encoding="utf-8")
    replacements = {
        "image: ghcr.io/nithron/nithronai/nai-core:0.7.0": f"image: {image}",
        "- NAI_TRUENAS_URL=\n": f"- NAI_TRUENAS_URL={url}\n",
        "- NAI_TRUENAS_API_KEY=\n": f"- NAI_TRUENAS_API_KEY={api_key}\n",
        "# - NAI_TRUENAS_CA_FILE=/app/data/truenas-ca.pem": "- NAI_TRUENAS_CA_FILE=/app/data/truenas-ca.pem",
    }
    for old, new in replacements.items():
        if old not in text:
            raise RuntimeError(f"compose.yaml no longer contains {old.strip()!r}; update install_app.py")
        text = text.replace(old, new, 1)
    return text


def ensure_app(api: configure.Api, compose: str) -> None:
    if api.call("app.query", [["name", "=", APP_NAME]]):
        api.job("app.update", APP_NAME, {"custom_compose_config_string": compose}, timeout=900)
        print(f"app {APP_NAME}: updated")
    else:
        api.job(
            "app.create",
            {"app_name": APP_NAME, "custom_app": True, "custom_compose_config_string": compose},
            timeout=900,
        )
        print(f"app {APP_NAME}: created")
    app: dict[str, Any] = {"state": "UNKNOWN"}
    for _ in range(90):
        app = api.call("app.query", [["name", "=", APP_NAME]], {"get": True})
        if app["state"] in ("RUNNING", "CRASHED", "STOPPED"):
            break
        time.sleep(5)
    print(f"app {APP_NAME}: state {app['state']}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=8443)
    parser.add_argument("--secrets", type=Path, required=True)
    parser.add_argument("--ca", type=Path, required=True, help="CA that signed the TrueNAS UI certificate")
    parser.add_argument("--ssh-pubkey", type=Path, help="enable key SSH + sudo docker for truenas_admin")
    parser.add_argument("--image", default="nai-core:lab-stage-0")
    parser.add_argument(
        "--truenas-url", default="wss://10.0.2.15/api/current", help="the URL nAI uses from inside the app"
    )
    parser.add_argument(
        "--skip-app", action="store_true", help="prepare everything but don't install the app"
    )
    args = parser.parse_args()

    secrets = configure.read_secrets(args.secrets)
    context = configure.bootstrap_context(configure.fetch_server_cert(args.host, args.port))
    api = configure.Api(f"wss://{args.host}:{args.port}/api/current", context)
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
        if args.ssh_pubkey:
            ensure_ssh_access(api, args.ssh_pubkey.read_text(encoding="utf-8"))
        ensure_apps_pool(api)
        ensure_app_datasets(api)
        for path in ("/mnt/tank/documents", "/mnt/tank/photos"):
            ensure_group_read(api, path)
        put_ca_file(api, f"https://{args.host}:{args.port}", context, args.ca.read_bytes())
        if not args.skip_app:
            ensure_app(api, compose_text(args.image, args.truenas_url, secrets["TRUENAS_NAI_API_KEY"]))
    finally:
        api.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
