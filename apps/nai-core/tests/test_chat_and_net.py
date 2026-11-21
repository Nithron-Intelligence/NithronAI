"""
Persistent chat and URL-ingestion safety tests
"""

import asyncio
import io
import socket
import threading

import pytest
from aiohttp import web

from app.utils.net import UnsafeURLError, fetch_url, is_public_ip, validate_url

# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------


def _say(client, text: str, conversation_id: str | None = None, headers=None) -> dict:
    body = {"messages": [{"role": "user", "content": text}], "use_context": False}
    if conversation_id:
        body["conversation_id"] = conversation_id
    r = client.post("/chat", json=body, headers=headers or {})
    assert r.status_code == 200, r.text
    return r.json()


def test_conversation_continues_and_persists(make_client):
    c = make_client()
    first = _say(c, "Hello there")
    conv = first["conversation_id"]
    second = _say(c, "Second message", conv)
    assert second["conversation_id"] == conv

    history = c.get(f"/chat/{conv}").json()["messages"]
    assert [m["role"] for m in history] == ["user", "assistant", "user", "assistant"]

    listing = c.get("/chat").json()
    assert listing[0]["conversation_id"] == conv
    assert listing[0]["title"] == "Hello there"
    assert listing[0]["message_count"] == 4


def test_conversation_id_query_param_still_supported(make_client):
    c = make_client()
    conv = _say(c, "Hi")["conversation_id"]
    r = c.post(
        f"/chat?conversation_id={conv}",
        json={"messages": [{"role": "user", "content": "Again"}], "use_context": False},
    )
    assert r.json()["conversation_id"] == conv


def test_unknown_conversation_is_404(make_client):
    c = make_client()
    r = c.post(
        "/chat",
        json={"messages": [{"role": "user", "content": "x"}], "conversation_id": "does-not-exist"},
    )
    assert r.status_code == 404


def test_delete_conversation(make_client):
    c = make_client()
    conv = _say(c, "Temporary")["conversation_id"]
    assert c.delete(f"/chat/{conv}").status_code == 200
    assert c.get(f"/chat/{conv}").status_code == 404


def test_conversations_are_private_per_user(make_client):
    c = make_client(NAI_AUTH_ENABLED="true", NAI_AUTH_ALLOW_REGISTRATION="true")
    tokens = {}
    for name in ("admin", "bob"):
        c.post("/auth/register", json={"username": name, "email": f"{name}@x.io", "password": "password123"})
        tok = c.post("/auth/login", json={"username": name, "password": "password123"}).json()
        tokens[name] = {"Authorization": f"Bearer {tok['access_token']}"}

    conv = _say(c, "Admin secret", headers=tokens["admin"])["conversation_id"]
    assert c.get(f"/chat/{conv}", headers=tokens["bob"]).status_code == 404
    assert c.get("/chat", headers=tokens["bob"]).json() == []
    assert c.delete(f"/chat/{conv}", headers=tokens["bob"]).status_code == 404


def test_chat_uses_document_context(make_client):
    c = make_client()
    c.post(
        "/ingest", files={"files": ("fr.txt", io.BytesIO(b"The capital of France is Paris."), "text/plain")}
    )
    r = c.post("/chat", json={"messages": [{"role": "user", "content": "capital of France?"}]})
    data = r.json()
    assert data["citations"]
    assert "Paris" in data["message"]["content"]


# ---------------------------------------------------------------------------
# URL safety
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("address", "public"),
    [
        ("8.8.8.8", True),
        ("2606:4700:4700::1111", True),
        ("127.0.0.1", False),
        ("10.1.2.3", False),
        ("192.168.1.10", False),
        ("172.16.0.1", False),
        ("169.254.169.254", False),
        ("100.64.0.1", False),
        ("0.0.0.0", False),
        ("::1", False),
        ("fe80::1", False),
        ("fd00::1", False),
        ("::ffff:127.0.0.1", False),
        ("224.0.0.1", False),
        ("not-an-ip", False),
    ],
)
def test_is_public_ip(address, public):
    assert is_public_ip(address) is public


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com/x",
        "http://127.0.0.1:8000/health",
        "http://[::1]/",
        "http://169.254.169.254/latest/meta-data/",
        "http://user:pass@example.com/",
        "http:///nohost",
    ],
)
def test_validate_url_rejects(url):
    with pytest.raises(UnsafeURLError):
        validate_url(url)


@pytest.fixture
def local_server():
    """A tiny HTTP server on 127.0.0.1 (a 'private' address)."""

    async def page(request):
        return web.Response(text="Internal wiki page about the homelab backup schedule.")

    async def redirect(request):
        raise web.HTTPFound("/page")

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    loop = asyncio.new_event_loop()
    started = threading.Event()
    runner_box = {}

    def run():
        asyncio.set_event_loop(loop)
        app = web.Application()
        app.router.add_get("/page", page)
        app.router.add_get("/redirect", redirect)
        runner = web.AppRunner(app)
        loop.run_until_complete(runner.setup())
        loop.run_until_complete(web.TCPSite(runner, "127.0.0.1", port).start())
        runner_box["runner"] = runner
        started.set()
        loop.run_forever()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    started.wait(5)
    yield f"http://127.0.0.1:{port}", port
    asyncio.run_coroutine_threadsafe(runner_box["runner"].cleanup(), loop).result(5)
    loop.call_soon_threadsafe(loop.stop)
    thread.join(5)


def test_fetch_refuses_private_addresses(local_server):
    base, port = local_server
    with pytest.raises(UnsafeURLError):
        asyncio.run(fetch_url(f"{base}/page", max_bytes=10_000))
    # Hostname resolving to loopback is caught at DNS resolution
    with pytest.raises(UnsafeURLError):
        asyncio.run(fetch_url(f"http://localhost:{port}/page", max_bytes=10_000))


def test_fetch_allows_private_when_configured_and_follows_redirects(local_server):
    base, _ = local_server
    result = asyncio.run(fetch_url(f"{base}/redirect", max_bytes=10_000, allow_private=True))
    assert b"backup schedule" in result.content
    assert result.final_url.endswith("/page")


def test_fetch_enforces_size_limit(local_server):
    from app.utils.net import FetchError

    base, _ = local_server
    with pytest.raises(FetchError):
        asyncio.run(fetch_url(f"{base}/page", max_bytes=10, allow_private=True))


def test_ingest_url_endpoint_blocks_and_allows(make_client, local_server):
    base, _ = local_server
    c = make_client()
    assert c.post(f"/ingest/url?url={base}/page").status_code == 400

    c = make_client(NAI_INGEST_URL_ALLOW_PRIVATE="true")
    r = c.post(f"/ingest/url?url={base}/page")
    assert r.status_code == 200, r.text
    assert r.json()["added"][0]["status"] == "success"
