"""
nAI TrueNAS Adapter (step 1: read-only discovery)
Talks to TrueNAS's versioned JSON-RPC 2.0 over WebSocket API (wss://<host>/api/current; the REST API
is deprecated since 25.04). Only read-only methods are called; no permission sync, no writes.
The API key is password-equivalent: wss:// with TLS verification only, never logged.
"""

from __future__ import annotations

import json
import os
import ssl
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from ..utils.logging import get_logger
from .base import Capabilities, ShareCandidate, discover_mounted_shares

logger = get_logger(__name__)

# Read-only methods this adapter may call (anything else is refused before it is sent).
READ_ONLY_METHODS = frozenset({"system.info", "sharing.smb.query", "sharing.nfs.query", "pool.dataset.query"})


class TrueNASError(RuntimeError):
    """Connection, TLS, authentication or API error (never contains the API key)."""


class _Connection(Protocol):
    def send(self, message: str) -> None: ...
    def recv(self, timeout: float | None = None) -> str | bytes: ...
    def close(self) -> None: ...


def _default_connect(url: str, ssl_context: ssl.SSLContext, timeout: float) -> _Connection:
    from websockets.sync.client import connect

    conn: _Connection = connect(url, ssl=ssl_context, open_timeout=timeout, close_timeout=timeout)
    return conn


@dataclass
class TrueNASClient:
    """Minimal JSON-RPC 2.0 client for the TrueNAS WebSocket API."""

    url: str
    api_key: str
    ca_file: str | None = None
    timeout: float = 15.0
    connect: Callable[[str, ssl.SSLContext, float], _Connection] = _default_connect
    _conn: _Connection | None = field(default=None, init=False, repr=False)
    _next_id: int = field(default=0, init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.url.startswith("wss://"):
            raise TrueNASError(
                "the TrueNAS API URL must start with wss:// (the API key is never sent unencrypted)"
            )
        if not self.api_key:
            raise TrueNASError("no TrueNAS API key configured (NAI_TRUENAS_API_KEY)")
        if self.ca_file and not os.path.isfile(self.ca_file):
            raise TrueNASError(f"CA file not found: {self.ca_file}")

    def __repr__(self) -> str:  # never show the key
        return f"TrueNASClient(url={self.url!r}, ca_file={self.ca_file!r})"

    def _ssl_context(self) -> ssl.SSLContext:
        # Verification is always on; a self-signed TrueNAS certificate needs its CA in ca_file.
        context = (
            ssl.create_default_context(cafile=self.ca_file) if self.ca_file else ssl.create_default_context()
        )
        context.check_hostname = True
        context.verify_mode = ssl.CERT_REQUIRED
        return context

    def _redact(self, text: str) -> str:
        return text.replace(self.api_key, "***") if self.api_key else text

    def _request(self, method: str, params: list[Any]) -> Any:
        assert self._conn is not None
        self._next_id += 1
        request_id = self._next_id
        self._conn.send(json.dumps({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}))
        while True:
            raw = self._conn.recv(timeout=self.timeout)
            message = json.loads(raw)
            if message.get("id") != request_id:  # notifications or other replies
                continue
            if "error" in message:
                error = message["error"]
                raise TrueNASError(f"{method} failed: {self._redact(str(error.get('message', error)))}")
            return message.get("result")

    def __enter__(self) -> TrueNASClient:
        try:
            self._conn = self.connect(self.url, self._ssl_context(), self.timeout)
            if self._request("auth.login_with_api_key", [self.api_key]) is not True:
                raise TrueNASError("TrueNAS rejected the API key")
        except TrueNASError:
            self.close()
            raise
        except Exception as e:  # TLS, DNS, refused, timeout: report without the key
            self.close()
            raise TrueNASError(
                f"cannot reach the TrueNAS API at {self.url}: {self._redact(str(e))}"
            ) from None
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            finally:
                self._conn = None

    def call(self, method: str, *params: Any) -> Any:
        if method not in READ_ONLY_METHODS:
            raise TrueNASError(f"{method} is not on the read-only allow-list")
        return self._request(method, list(params))


def share_paths(smb: list[dict[str, Any]], nfs: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """(name, host path) of enabled SMB and NFS shares; NFS uses 'path' (25.04+) or 'paths' (older)."""
    found: dict[str, str] = {}
    for share in smb:
        if share.get("enabled", True) and share.get("path"):
            found.setdefault(share["path"], share.get("name") or os.path.basename(share["path"]))
    for share in nfs:
        if not share.get("enabled", True):
            continue
        for path in [share["path"]] if share.get("path") else share.get("paths", []):
            found.setdefault(path, os.path.basename(path.rstrip("/")))
    return sorted(((name, path) for path, name in found.items()), key=lambda item: item[1])


@dataclass(frozen=True)
class TrueNASAdapter:
    """TrueNAS: mounted folders plus the shares the TrueNAS API reports (read-only)."""

    url: str = ""
    api_key: str = field(default="", repr=False)
    ca_file: str | None = None
    timeout: float = 15.0
    name: str = "truenas"
    display_name: str = "TrueNAS"
    capabilities: Capabilities = field(default_factory=Capabilities)

    def client(self) -> TrueNASClient:
        return TrueNASClient(self.url, self.api_key, self.ca_file, self.timeout)

    def discover_shares(self, roots: list[str], existing: list[str]) -> list[ShareCandidate]:
        mounted = discover_mounted_shares(roots, existing)
        if not self.url:
            return mounted
        try:
            with self.client() as api:
                shares = share_paths(api.call("sharing.smb.query"), api.call("sharing.nfs.query"))
        except TrueNASError as e:
            logger.warning(f"TrueNAS share discovery failed: {e}")
            return mounted
        by_name = {c.name: c for c in mounted}
        result = list(mounted)
        for name, host_path in shares:
            if os.path.basename(host_path.rstrip("/")) in by_name:
                continue  # already visible as a mounted folder
            result.append(ShareCandidate(name=name, path=host_path, source="nas-api", mounted=False))
        return result

    def platform_status(self) -> dict[str, Any]:
        """TrueNAS version and connection state for /sources/discover (no secrets)."""
        if not self.url:
            return {"connected": False, "detail": "NAI_TRUENAS_URL not set: showing mounted folders only"}
        try:
            with self.client() as api:
                info = api.call("system.info") or {}
            return {"connected": True, "version": info.get("version"), "hostname": info.get("hostname")}
        except TrueNASError as e:
            return {"connected": False, "detail": str(e)}
