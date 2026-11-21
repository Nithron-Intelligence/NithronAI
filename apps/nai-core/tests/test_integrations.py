"""
Integrations for other programs: API keys, OpenAI-compatible API, MCP server
(plus source renames keeping the index consistent)
"""

import json
import os

import pytest


def _write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _login(client, username: str) -> dict:
    r = client.post("/auth/login", json={"username": username, "password": "password123"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _register(client, username: str, headers: dict | None = None) -> dict:
    r = client.post(
        "/auth/register",
        json={"username": username, "email": f"{username}@example.com", "password": "password123"},
        headers=headers or {},
    )
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture
def nas(share, make_client):
    """Auth on. 'Family' share open to all, 'Finance' only to group 'parents'. Users: admin, kid."""
    root, env = share
    family, finance = os.path.join(root, "Family"), os.path.join(root, "Finance")
    _write(os.path.join(family, "holiday.txt"), "Holiday plan: Lisbon in July. Budget 2000 EUR for the trip.")
    _write(
        os.path.join(family, "Recipes", "pasta.md"), "# Pasta\n\nBoil water, add salt, cook the spaghetti."
    )
    _write(os.path.join(finance, "salary.txt"), "Salary statement 2025: net salary and the yearly budget.")

    client = make_client(NAI_AUTH_ENABLED="true", **env)
    _register(client, "admin")
    admin = _login(client, "admin")
    _register(client, "kid", admin)
    for name, path, groups in [("Family", family, []), ("Finance", finance, ["parents"])]:
        r = client.post(
            "/sources", json={"name": name, "path": path, "allowed_groups": groups}, headers=admin
        )
        assert r.status_code == 201, r.text
    return client, admin, _login(client, "kid")


def _key(client, headers: dict, name: str = "test") -> dict:
    r = client.post("/auth/keys", json={"name": name}, headers=headers)
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['key']}"}


# ---------------------------------------------------------------------------
# API keys
# ---------------------------------------------------------------------------


def test_api_key_lifecycle(nas):
    client, admin, _ = nas
    created = client.post("/auth/keys", json={"name": "Open WebUI"}, headers=admin).json()
    assert created["key"].startswith("nai_") and created["prefix"] == created["key"][:12]
    key_auth = {"Authorization": f"Bearer {created['key']}"}

    assert client.get("/auth/me", headers=key_auth).json()["username"] == "admin"
    listed = client.get("/auth/keys", headers=admin).json()
    assert [k["name"] for k in listed] == ["Open WebUI"]
    assert "key" not in listed[0]  # the secret is shown only once
    assert listed[0]["last_used_at"] is not None

    assert client.delete(f"/auth/keys/{created['id']}", headers=admin).status_code == 200
    assert client.get("/auth/me", headers=key_auth).status_code == 401


def test_api_keys_are_private_and_bogus_keys_fail(nas):
    client, admin, kid = nas
    admin_key = client.post("/auth/keys", json={"name": "a"}, headers=admin).json()
    assert client.get("/auth/keys", headers=kid).json() == []
    assert client.delete(f"/auth/keys/{admin_key['id']}", headers=kid).status_code == 404
    assert client.get("/auth/me", headers={"Authorization": "Bearer nai_not-a-real-key"}).status_code == 401


def test_api_key_dies_with_its_user(nas):
    client, admin, kid = nas
    kid_key = _key(client, kid)
    kid_id = client.get("/auth/me", headers=kid).json()["id"]
    assert client.delete(f"/auth/users/{kid_id}", headers=admin).status_code == 200
    assert client.get("/auth/me", headers=kid_key).status_code == 401


def test_api_key_endpoints_need_auth_enabled(make_client):
    c = make_client()
    assert c.post("/auth/keys", json={"name": "x"}).status_code == 400


# ---------------------------------------------------------------------------
# OpenAI-compatible API
# ---------------------------------------------------------------------------


def test_models_list_sources_the_user_can_see(nas):
    client, admin, kid = nas
    ids = lambda h: [m["id"] for m in client.get("/v1/models", headers=h).json()["data"]]  # noqa: E731
    assert ids(admin) == ["nai", "nai/family", "nai/finance"]
    assert ids(_key(client, kid)) == ["nai", "nai/family"]
    assert client.get("/v1/models").status_code == 401


def test_chat_completion_answers_from_files(nas):
    client, admin, _ = nas
    r = client.post(
        "/v1/chat/completions",
        json={"model": "nai", "messages": [{"role": "user", "content": "how do I cook spaghetti?"}]},
        headers=_key(client, admin),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["object"] == "chat.completion"
    content = body["choices"][0]["message"]["content"]
    assert "spaghetti" in content and "Family/Recipes/pasta.md" in content
    assert body["choices"][0]["finish_reason"] == "stop"
    assert body["citations"][0]["source_name"] == "Family"


def test_chat_completion_accepts_content_parts_and_system_messages(nas):
    client, admin, _ = nas
    r = client.post(
        "/v1/chat/completions",
        json={
            "model": "nai",
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": "You are helpful."},
                {"role": "user", "content": [{"type": "text", "text": "Lisbon holiday budget"}]},
            ],
        },
        headers=admin,
    )
    assert r.status_code == 200
    assert "holiday.txt" in r.json()["choices"][0]["message"]["content"]


def test_per_source_model_and_access(nas):
    client, admin, kid = nas
    ask = lambda model, h: client.post(  # noqa: E731
        "/v1/chat/completions",
        json={"model": model, "messages": [{"role": "user", "content": "budget"}]},
        headers=h,
    )
    finance_only = ask("nai/finance", admin).json()["citations"]
    assert {c["source_name"] for c in finance_only} == {"Finance"}
    # A restricted user can neither pick the model nor reach the files through "nai"
    assert ask("nai/finance", _key(client, kid)).status_code == 404
    kid_sources = {c["source_name"] for c in ask("nai", _key(client, kid)).json()["citations"]}
    assert kid_sources == {"Family"}
    assert ask("gpt-4o", admin).status_code == 404


def test_chat_completion_streaming_format(nas, monkeypatch):
    from .test_streaming_and_system import _fake_llm

    client, admin, _ = nas
    monkeypatch.setenv("NAI_LLM_ENABLED", "true")
    from app.services import get_llm_service

    get_llm_service().settings.llm_enabled = True
    _fake_llm(monkeypatch, ["Boil ", "the water."])
    r = client.post(
        "/v1/chat/completions",
        json={"model": "nai", "stream": True, "messages": [{"role": "user", "content": "spaghetti"}]},
        headers=admin,
    )
    assert r.headers["content-type"].startswith("text/event-stream")
    lines = [line[6:] for line in r.text.splitlines() if line.startswith("data: ")]
    assert lines[-1] == "[DONE]"
    chunks = [json.loads(line) for line in lines[:-1]]
    assert all(c["object"] == "chat.completion.chunk" for c in chunks)
    assert chunks[0]["choices"][0]["delta"]["role"] == "assistant"
    text = "".join(c["choices"][0]["delta"].get("content", "") for c in chunks)
    assert text.startswith("Boil the water.") and "pasta.md" in text
    assert chunks[-1]["choices"][0]["finish_reason"] == "stop"


def test_chat_completion_needs_a_user_message(nas):
    client, admin, _ = nas
    r = client.post(
        "/v1/chat/completions", json={"messages": [{"role": "system", "content": "hi"}]}, headers=admin
    )
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# MCP
# ---------------------------------------------------------------------------


def _rpc(client, headers, method, params=None, msg_id: int | None = 1, **extra_headers: str):
    body = {"jsonrpc": "2.0", "method": method}
    if msg_id is not None:
        body["id"] = msg_id
    if params is not None:
        body["params"] = params
    return client.post("/mcp", json=body, headers={**headers, **extra_headers})


def _tool(client, headers, name, **arguments):
    r = _rpc(client, headers, "tools/call", {"name": name, "arguments": arguments})
    assert r.status_code == 200, r.text
    result = r.json()["result"]
    return result["content"][0]["text"], result["isError"]


def test_mcp_handshake_and_tool_list(nas):
    client, admin, _ = nas
    key = _key(client, admin)
    init = _rpc(
        client,
        key,
        "initialize",
        {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}},
    )
    result = init.json()["result"]
    assert result["protocolVersion"] == "2025-06-18"
    assert result["serverInfo"]["name"] == "nai" and "tools" in result["capabilities"]

    old = _rpc(client, key, "initialize", {"protocolVersion": "2024-11-05"}).json()["result"]
    assert old["protocolVersion"] == "2024-11-05"
    future = _rpc(client, key, "initialize", {"protocolVersion": "2099-01-01"}).json()["result"]
    assert future["protocolVersion"] == "2025-06-18"

    note = _rpc(client, key, "notifications/initialized", msg_id=None)
    assert note.status_code == 202 and note.content == b""

    tools = _rpc(client, key, "tools/list", **{"MCP-Protocol-Version": "2025-06-18"}).json()["result"][
        "tools"
    ]
    assert [t["name"] for t in tools] == ["search_files", "read_document", "list_sources"]
    assert all(t["annotations"]["readOnlyHint"] for t in tools)
    assert _rpc(client, key, "ping").json()["result"] == {}


def test_mcp_search_and_read(nas):
    client, admin, _ = nas
    key = _key(client, admin)
    text, is_error = _tool(client, key, "search_files", query="cook spaghetti")
    assert not is_error and "Family/Recipes/pasta.md" in text and "section 'Pasta'" in text
    doc_id = text.split("doc_id: ")[1].split()[0]

    doc, is_error = _tool(client, key, "read_document", doc_id=doc_id)
    assert not is_error and "Boil water" in doc

    only_finance, _ = _tool(client, key, "search_files", query="budget", source="finance")
    assert "salary.txt" in only_finance and "holiday" not in only_finance

    sources, _ = _tool(client, key, "list_sources")
    assert "Family" in sources and "Finance" in sources


def test_mcp_respects_access(nas):
    client, admin, kid = nas
    admin_key, kid_key = _key(client, admin), _key(client, kid)
    salary_text, _ = _tool(client, admin_key, "search_files", query="salary statement")
    salary_id = salary_text.split("doc_id: ")[1].split()[0]

    kid_search, _ = _tool(client, kid_key, "search_files", query="salary statement")
    assert "salary.txt" not in kid_search
    denied, is_error = _tool(client, kid_key, "read_document", doc_id=salary_id)
    assert is_error and "No accessible document" in denied
    unknown, is_error = _tool(client, kid_key, "search_files", query="x", source="Finance")
    assert is_error and "Unknown source" in unknown
    assert "Finance" not in _tool(client, kid_key, "list_sources")[0]

    assert _rpc(client, {}, "tools/list").status_code == 401


def test_mcp_protocol_errors(nas):
    client, admin, _ = nas
    assert _rpc(client, admin, "resources/list").json()["error"]["code"] == -32601
    bad_tool = _rpc(client, admin, "tools/call", {"name": "rm_rf", "arguments": {}}).json()
    assert bad_tool["error"]["code"] == -32602
    bad_args, is_error = _tool(client, admin, "search_files", nonsense=1)
    assert is_error and "Invalid arguments" in bad_args

    parse = client.post("/mcp", content=b"{not json", headers={**admin, "Content-Type": "application/json"})
    assert parse.status_code == 400 and parse.json()["error"]["code"] == -32700
    assert _rpc(client, admin, "ping", **{"MCP-Protocol-Version": "1999-01-01"}).status_code == 400
    assert client.get("/mcp", headers=admin).status_code == 405

    batch = client.post(
        "/mcp",
        json=[
            {"jsonrpc": "2.0", "id": 1, "method": "ping"},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
        ],
        headers=admin,
    ).json()
    assert batch == [{"jsonrpc": "2.0", "id": 1, "result": {}}]


def test_mcp_rejects_foreign_browser_origins(nas):
    client, admin, _ = nas
    assert _rpc(client, admin, "ping", Origin="https://evil.example").status_code == 403
    assert (
        _rpc(client, admin, "ping", Origin="http://localhost:5173").status_code == 200
    )  # configured CORS origin
    assert _rpc(client, admin, "ping", Origin="http://testserver").status_code == 200  # same origin


# ---------------------------------------------------------------------------
# Renaming a source
# ---------------------------------------------------------------------------


def test_renaming_a_source_updates_index_and_reembeds(share, make_client, fake_embeddings):
    from app.db import get_db
    from app.services import get_embedding_service

    root, env = share
    _write(os.path.join(root, "Documents", "car.txt"), "Car insurance renewal letter.")
    client = make_client(**env, **fake_embeddings)
    source = client.post(
        "/sources", json={"name": "Documents", "path": os.path.join(root, "Documents")}
    ).json()
    service = get_embedding_service()
    service.embed_pending()

    client.patch(f"/sources/{source['id']}", json={"name": "Paperwork"})
    with get_db().connect() as conn:
        contexts = [r[0] for r in conn.execute("SELECT context FROM chunks")]
    assert contexts and all(c.startswith("Document: Paperwork/car.txt") for c in contexts)
    assert service.pending_count() == 1  # vector dropped, worker will re-embed with the new header
    service.embed_pending()

    assert client.post("/search", json={"query": "paperwork"}).json()["results"][0]["filename"] == "car.txt"
    assert client.post("/search", json={"query": "documents"}).json()["results"] == []
