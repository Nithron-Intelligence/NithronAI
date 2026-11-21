"""
Storage, ingestion and migration tests (SQLite-backed index)
"""

import io
import json
import os

from app.utils.text import chunk_text_semantic


def _ingest(client, name: str, content: bytes) -> dict:
    r = client.post("/ingest", files={"files": (name, io.BytesIO(content), "text/plain")})
    assert r.status_code == 200, r.text
    return r.json()["added"][0]


def test_doc_id_from_ingest_can_be_fetched_and_deleted(make_client):
    """Regression: 0.2 returned a content hash but stored a path hash, so delete-by-id failed."""
    c = make_client()
    added = _ingest(c, "note.txt", b"Remember to renew the car insurance in March.")
    assert added["status"] == "success"

    assert c.get(f"/documents/{added['doc_id']}").status_code == 200
    assert c.get(f"/documents/{added['doc_id']}/chunks").json()["total"] >= 1
    r = c.delete(f"/documents/{added['doc_id']}")
    assert r.status_code == 200
    assert c.get(f"/documents/{added['doc_id']}").status_code == 404


def test_duplicate_upload_is_skipped_without_orphan_file(make_client, tmp_path):
    c = make_client()
    content = b"Exactly the same bytes uploaded twice."
    first = _ingest(c, "a.txt", content)
    second = _ingest(c, "b.txt", content)

    assert first["status"] == "success"
    assert second["status"] == "skipped"
    assert second["doc_id"] == first["doc_id"]
    assert len(os.listdir(tmp_path / "data" / "docs")) == 1


def test_delete_removes_stored_file(make_client, tmp_path):
    c = make_client()
    added = _ingest(c, "gone.txt", b"This file will be deleted again.")
    c.delete(f"/documents/{added['doc_id']}")
    assert os.listdir(tmp_path / "data" / "docs") == []


def test_rejected_and_empty_files_leave_nothing_behind(make_client, tmp_path):
    c = make_client()
    bad = c.post("/ingest", files={"files": ("x.exe", io.BytesIO(b"MZ"), "application/octet-stream")})
    assert bad.json()["added"][0]["status"] == "error"
    empty = _ingest(c, "empty.txt", b"   ")
    assert empty["status"] == "skipped"
    assert os.listdir(tmp_path / "data" / "docs") == []


def test_index_survives_restart(make_client):
    from fastapi.testclient import TestClient

    from app.main import create_app
    from app.services import reset_services

    c = make_client()
    _ingest(c, "persist.txt", b"Persistence means data survives a restart of the service.")

    reset_services()
    with TestClient(create_app()) as fresh:
        docs = fresh.get("/documents").json()
        assert docs["total"] == 1
        r = fresh.post("/search", json={"query": "persistence restart"})
        assert r.json()["total"] >= 1


def test_search_sees_new_and_deleted_documents(make_client):
    c = make_client()
    a = _ingest(c, "zebra.txt", b"Zebras are striped animals living in Africa.")
    assert c.post("/search", json={"query": "zebras"}).json()["total"] == 1
    c.delete(f"/documents/{a['doc_id']}")
    assert c.post("/search", json={"query": "zebras"}).json()["total"] == 0


def test_long_unpunctuated_text_is_chunked():
    """Regression: a sentence longer than max_chars crashed chunk_text with a TypeError."""
    text = " ".join(f"word{i}" for i in range(2000))  # ~15k chars, no sentence breaks
    chunks = chunk_text_semantic(text, max_chars=1000)
    assert len(chunks) > 1
    assert all(len(ch) <= 1000 for ch in chunks)


def test_legacy_jsonl_and_users_are_migrated(make_client, tmp_path):
    data = tmp_path / "data"
    (data / "index").mkdir(parents=True)
    (data / "docs").mkdir()
    records = [
        {
            "doc_id": "pathhash0000000",
            "doc_path": "20250101T000000_abc_old.txt",
            "chunk_id": i,
            "text": f"Legacy chunk {i} about migration of old indexes.",
            "metadata": {"doc_id": "contenthash00000", "original_filename": "old.txt"},
            "created_at": "2025-01-01T00:00:00Z",
        }
        for i in range(2)
    ]
    (data / "index" / "index.jsonl").write_text("\n".join(json.dumps(r) for r in records) + "\n")
    import bcrypt

    users = {
        "u1": {
            "id": "u1",
            "username": "legacy",
            "email": "legacy@example.com",
            "password_hash": bcrypt.hashpw(b"legacy-password", bcrypt.gensalt()).decode(),
            "is_active": True,
            "is_admin": True,
            "created_at": "2025-01-01T00:00:00Z",
        }
    }
    (data / "users.json").write_text(json.dumps(users))

    c = make_client(NAI_AUTH_ENABLED="true")
    login = c.post("/auth/login", json={"username": "legacy", "password": "legacy-password"})
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    docs = c.get("/documents", headers=headers).json()["documents"]
    assert [d["doc_id"] for d in docs] == ["contenthash00000"]
    assert docs[0]["chunk_count"] == 2
    assert (data / "index" / "index.jsonl.migrated").exists()
    assert (data / "users.json.migrated").exists()
