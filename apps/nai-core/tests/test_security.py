"""
Authentication, authorization and rate limiting tests
"""

import io

import pytest
from starlette.requests import Request

PROTECTED = [
    ("post", "/ask", {"json": {"question": "hi"}}),
    ("post", "/search", {"json": {"query": "hi"}}),
    ("get", "/documents", {}),
    ("get", "/documents/stats/summary", {}),
    ("post", "/chat", {"json": {"messages": [{"role": "user", "content": "hi"}]}}),
    ("get", "/chat", {}),
    ("post", "/ingest", {"files": {"files": ("a.txt", io.BytesIO(b"hello world"), "text/plain")}}),
    ("post", "/ingest/url?url=https://example.com", {}),
    ("get", "/health/detailed", {}),
]

ADMIN = {"username": "admin", "email": "admin@example.com", "password": "correct-horse"}
ALICE = {"username": "alice", "email": "alice@example.com", "password": "alice-password"}


def _token(client, creds) -> dict:
    r = client.post("/auth/login", json={"username": creds["username"], "password": creds["password"]})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def auth_client(make_client):
    return make_client(NAI_AUTH_ENABLED="true")


@pytest.mark.parametrize(("method", "path", "kwargs"), PROTECTED)
def test_data_endpoints_require_auth(auth_client, method, path, kwargs):
    response = getattr(auth_client, method)(path, **kwargs)
    assert response.status_code == 401


def test_health_stays_public(auth_client):
    assert auth_client.get("/health").status_code == 200


def test_invalid_token_rejected(auth_client):
    r = auth_client.get("/documents", headers={"Authorization": "Bearer not-a-jwt"})
    assert r.status_code == 401


def test_first_user_becomes_admin_then_registration_closes(auth_client):
    assert auth_client.get("/auth/status").json()["setup_required"] is True

    r = auth_client.post("/auth/register", json=ADMIN)
    assert r.status_code == 200
    assert r.json()["is_admin"] is True

    status = auth_client.get("/auth/status").json()
    assert status["setup_required"] is False
    assert status["registration_open"] is False

    r = auth_client.post("/auth/register", json=ALICE)
    assert r.status_code == 403


def test_admin_can_create_users_and_users_are_not_admin(auth_client):
    auth_client.post("/auth/register", json=ADMIN)
    admin = _token(auth_client, ADMIN)

    r = auth_client.post("/auth/register", json=ALICE, headers=admin)
    assert r.status_code == 200
    assert r.json()["is_admin"] is False

    alice = _token(auth_client, ALICE)
    assert auth_client.get("/auth/me", headers=alice).json()["username"] == "alice"
    assert auth_client.get("/auth/users", headers=alice).status_code == 403
    assert auth_client.get("/health/detailed", headers=alice).status_code == 403
    assert auth_client.post("/system/embeddings/reindex", headers=alice).status_code == 403
    assert auth_client.get("/health/detailed", headers=admin).status_code == 200


def test_open_registration_setting(make_client):
    c = make_client(NAI_AUTH_ENABLED="true", NAI_AUTH_ALLOW_REGISTRATION="true")
    c.post("/auth/register", json=ADMIN)
    r = c.post("/auth/register", json=ALICE)
    assert r.status_code == 200
    assert r.json()["is_admin"] is False


def test_duplicate_username_rejected_case_insensitive(auth_client):
    auth_client.post("/auth/register", json=ADMIN)
    admin = _token(auth_client, ADMIN)
    dup = {**ALICE, "username": "ADMIN"}
    assert auth_client.post("/auth/register", json=dup, headers=admin).status_code == 400


def test_wrong_password_and_unknown_user(auth_client):
    auth_client.post("/auth/register", json=ADMIN)
    bad = auth_client.post("/auth/login", json={"username": "admin", "password": "nope-nope"})
    unknown = auth_client.post("/auth/login", json={"username": "ghost", "password": "nope-nope"})
    assert bad.status_code == unknown.status_code == 401


def test_password_over_72_bytes_rejected(auth_client):
    r = auth_client.post("/auth/register", json={**ADMIN, "password": "ä" * 40})
    assert r.status_code == 422


def test_only_admin_can_delete_documents(auth_client):
    auth_client.post("/auth/register", json=ADMIN)
    admin = _token(auth_client, ADMIN)
    auth_client.post("/auth/register", json=ALICE, headers=admin)
    alice = _token(auth_client, ALICE)

    files = {"files": ("doc.txt", io.BytesIO(b"Shared document content for everyone."), "text/plain")}
    doc_id = auth_client.post("/ingest", files=files, headers=alice).json()["added"][0]["doc_id"]

    assert auth_client.delete(f"/documents/{doc_id}", headers=alice).status_code == 403
    assert auth_client.delete(f"/documents/{doc_id}", headers=admin).status_code == 200


def test_secret_key_is_generated_and_persisted(make_client, tmp_path):
    c = make_client(NAI_AUTH_ENABLED="true")
    c.post("/auth/register", json=ADMIN)
    key_file = tmp_path / "data" / ".secret_key"
    assert key_file.exists()
    assert len(key_file.read_text()) >= 32


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


def test_rate_limit_ignores_spoofed_forwarded_for(make_client):
    c = make_client(NAI_RATE_LIMIT_ENABLED="true", NAI_RATE_LIMIT_REQUESTS="2")
    statuses = [
        c.get("/documents", headers={"X-Forwarded-For": f"203.0.113.{i}"}).status_code for i in range(3)
    ]
    assert statuses == [200, 200, 429]


def _request(peer: str, forwarded: str | None = None) -> Request:
    headers = [(b"x-forwarded-for", forwarded.encode())] if forwarded else []
    return Request({"type": "http", "client": (peer, 1234), "headers": headers, "path": "/"})


def test_rate_limit_trusts_forwarded_for_only_from_trusted_proxy(monkeypatch):
    from app.middleware import RateLimitMiddleware
    from app.services import reset_services

    monkeypatch.setenv("NAI_TRUSTED_PROXIES", '["10.0.0.0/8"]')
    reset_services()
    try:
        mw = RateLimitMiddleware(app=None)  # type: ignore[arg-type]
        # Trusted proxy: right-most untrusted hop is the client
        assert mw._get_client_key(_request("10.0.0.2", "198.51.100.7, 10.0.0.5")) == "198.51.100.7"
        # Untrusted peer: header ignored
        assert mw._get_client_key(_request("192.0.2.1", "198.51.100.7")) == "192.0.2.1"
    finally:
        monkeypatch.delenv("NAI_TRUSTED_PROXIES")
        reset_services()
