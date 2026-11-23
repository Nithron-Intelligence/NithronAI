"""TrueNAS adapter step 1: read-only discovery against a fake JSON-RPC WebSocket server."""

from __future__ import annotations

import json
import logging
import os
import ssl
from typing import Any

import pytest

from app.config import Settings
from app.nas import get_nas_adapter
from app.nas.truenas import TrueNASAdapter, TrueNASClient, TrueNASError, share_paths

KEY = "1-SECRETKEYdoNotLeak"


class RpcError(dict[str, Any]):
    """A JSON-RPC error object the fake server answers with instead of a result."""


# Recorded shapes of TrueNAS 25.10.8 responses (VM test 2026-11-23; trimmed to the fields nAI reads).
RESPONSES: dict[str, Any] = {
    "auth.login_with_api_key": True,
    "system.info": {"version": "25.10.8", "hostname": "truenas"},
    "sharing.smb.query": [
        {"id": 1, "name": "documents", "path": "/mnt/tank/documents", "enabled": True},
        {"id": 2, "name": "old", "path": "/mnt/tank/old", "enabled": False},
    ],
    "sharing.nfs.query": [{"id": 1, "path": "/mnt/tank/photos", "enabled": True}],
}

# What TrueNAS 25.10.8 answers when the read-only user calls a write method (trace trimmed).
EACCES = RpcError(
    code=-32001,
    message="Method call error",
    data={
        "error": 13,
        "errname": "EACCES",
        "reason": "[EACCES] Not authorized",
        "trace": {"class": "CallError"},
    },
)


class FakeConnection:
    """Answers JSON-RPC requests from RESPONSES and records what was sent."""

    def __init__(self, responses: dict[str, Any]) -> None:
        self.responses = responses
        self.sent: list[dict[str, Any]] = []
        self.queue: list[str] = []
        self.closed = False

    def send(self, message: str) -> None:
        request = json.loads(message)
        self.sent.append(request)
        method = request["method"]
        self.queue.append(
            json.dumps({"jsonrpc": "2.0", "method": "collection_update", "params": {}})
        )  # noise
        if isinstance(self.responses.get(method), RpcError):
            reply = {"jsonrpc": "2.0", "id": request["id"], "error": dict(self.responses[method])}
        elif method in self.responses and self.responses[method] is not Exception:
            reply = {"jsonrpc": "2.0", "id": request["id"], "result": self.responses[method]}
        else:
            reply = {
                "jsonrpc": "2.0",
                "id": request["id"],
                "error": {"code": -32601, "message": f"no {method}"},
            }
        self.queue.append(json.dumps(reply))

    def recv(self, timeout: float | None = None) -> str:
        return self.queue.pop(0)

    def close(self) -> None:
        self.closed = True


def _client(responses: dict[str, Any] | None = None) -> tuple[TrueNASClient, list[FakeConnection]]:
    made: list[FakeConnection] = []

    def connect(url: str, context: ssl.SSLContext, timeout: float) -> FakeConnection:
        assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
        made.append(FakeConnection(RESPONSES if responses is None else responses))
        return made[-1]

    return TrueNASClient("wss://truenas.local/api/current", KEY, connect=connect), made


def test_client_logs_in_and_calls_read_only_methods() -> None:
    client, made = _client()
    with client as api:
        assert api.call("system.info")["version"] == "25.10.8"
    assert [r["method"] for r in made[0].sent] == ["auth.login_with_api_key", "system.info"]
    assert made[0].closed


def test_client_refuses_insecure_urls_and_non_read_only_methods() -> None:
    with pytest.raises(TrueNASError, match="wss://"):
        TrueNASClient("ws://truenas.local/api/current", KEY)
    client, _ = _client()
    with client as api, pytest.raises(TrueNASError, match="read-only"):
        api.call("sharing.smb.create", {"path": "/mnt/tank/x"})


def test_api_errors_show_the_truenas_reason_not_the_generic_message() -> None:
    client, _ = _client({**RESPONSES, "system.info": EACCES})
    with client as api, pytest.raises(TrueNASError) as denied:
        api.call("system.info")
    assert str(denied.value) == "system.info failed: [EACCES] Not authorized"


def test_rejected_key_and_errors_never_contain_the_key(caplog: pytest.LogCaptureFixture) -> None:
    client, _ = _client({**RESPONSES, "auth.login_with_api_key": False})
    with pytest.raises(TrueNASError) as rejected:
        client.__enter__()
    assert KEY not in str(rejected.value)

    def boom(url: str, context: ssl.SSLContext, timeout: float) -> FakeConnection:
        raise OSError(f"TLS handshake failed while sending {KEY}")

    caplog.set_level(logging.DEBUG)
    adapter = TrueNASAdapter(url="wss://truenas.local/api/current", api_key=KEY)
    failing = TrueNASClient(adapter.url, KEY, connect=boom)
    with pytest.raises(TrueNASError) as unreachable:
        failing.__enter__()
    assert KEY not in str(unreachable.value) and "***" in str(unreachable.value)
    assert KEY not in repr(adapter) and KEY not in repr(failing)
    assert KEY not in caplog.text


def test_share_paths_reads_smb_and_both_nfs_shapes() -> None:
    older_nfs = [{"paths": ["/mnt/tank/music", "/mnt/tank/video"], "enabled": True}]
    assert share_paths(RESPONSES["sharing.smb.query"], RESPONSES["sharing.nfs.query"] + older_nfs) == [
        ("documents", "/mnt/tank/documents"),
        ("music", "/mnt/tank/music"),
        ("photos", "/mnt/tank/photos"),
        ("video", "/mnt/tank/video"),
    ]


def test_adapter_merges_mounted_folders_and_api_shares(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    os.mkdir(tmp_path / "documents")  # mounted into the container as /shares/documents
    client, _ = _client()
    monkeypatch.setattr(TrueNASAdapter, "client", lambda self: client)
    adapter = TrueNASAdapter(url="wss://truenas.local/api/current", api_key=KEY)
    shares = adapter.discover_shares([str(tmp_path)], [])
    assert [(s.name, s.source, s.mounted) for s in shares] == [
        ("documents", "mount", True),
        ("photos", "nas-api", False),
    ]
    status = adapter.platform_status()
    assert status["connected"] is True and status["version"] == "25.10.8"


def test_adapter_without_url_or_with_failing_api_still_lists_mounted_folders(tmp_path) -> None:
    os.mkdir(tmp_path / "documents")
    assert [s.name for s in TrueNASAdapter().discover_shares([str(tmp_path)], [])] == ["documents"]
    bad = TrueNASAdapter(url="ws://insecure/api/current", api_key=KEY)  # refused, falls back
    assert [s.name for s in bad.discover_shares([str(tmp_path)], [])] == ["documents"]
    assert bad.platform_status()["connected"] is False


def test_registry_builds_truenas_adapter_from_settings() -> None:
    settings = Settings(nas_platform="truenas", truenas_url="wss://nas/api/current", truenas_api_key=KEY)
    adapter = get_nas_adapter(settings)
    assert isinstance(adapter, TrueNASAdapter) and adapter.url == "wss://nas/api/current"
    assert KEY not in repr(settings)
