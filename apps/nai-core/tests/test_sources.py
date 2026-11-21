"""
Sources: NAS folders indexed in place, incremental sync, safety rules and per-group access
"""

import os
import time

import pytest


def _write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _add_source(client, name: str, path: str, **extra) -> dict:
    r = client.post("/sources", json={"name": name, "path": path, **extra})
    assert r.status_code == 201, r.text
    return r.json()


def _scan(client, source_id: int) -> dict:
    r = client.post(f"/sources/{source_id}/scan", params={"wait": "true"})
    assert r.status_code == 200, r.text
    return r.json()


def _search_files(client, query: str, **body) -> list[str]:
    r = client.post("/search", json={"query": query, **body})
    assert r.status_code == 200, r.text
    return [res["doc_path"] for res in r.json()["results"]]


@pytest.fixture
def docs(share, make_client):
    root, env = share
    folder = os.path.join(root, "Documents")
    _write(os.path.join(folder, "insurance.txt"), "The car insurance renews every March. Policy number 4711.")
    _write(
        os.path.join(folder, "Recipes", "pasta.md"), "# Pasta\n\nBoil water, add salt and cook the spaghetti."
    )
    client = make_client(**env)
    return client, folder


# ---------------------------------------------------------------------------
# Incremental sync
# ---------------------------------------------------------------------------


def test_scan_indexes_files_in_place(docs, tmp_path):
    client, folder = docs
    source = _add_source(client, "Documents", folder)  # adding a source starts a scan right away
    result = _scan(client, source["id"])
    assert result["indexed"] + result["unchanged"] == 2 and result["errors"] == 0

    assert _search_files(client, "spaghetti") == ["Recipes/pasta.md"]
    # Nothing was copied into nAI's upload folder
    assert os.listdir(tmp_path / "data" / "docs") == []

    listed = client.get("/sources").json()
    assert listed[0]["document_count"] == 2 and listed[0]["last_scan_status"] == "ok"


def test_rescan_only_reindexes_changes(docs):
    client, folder = docs
    source = _add_source(client, "Documents", folder)
    _scan(client, source["id"])

    second = _scan(client, source["id"])
    assert second["indexed"] == 0 and second["unchanged"] == 2

    path = os.path.join(folder, "insurance.txt")
    _write(path, "The car insurance now renews every September.")
    os.utime(path, (time.time() + 5, time.time() + 5))
    third = _scan(client, source["id"])
    assert third["indexed"] == 1 and third["unchanged"] == 1
    assert _search_files(client, "september") == ["insurance.txt"]
    assert _search_files(client, "march") == []


def test_touched_but_identical_file_is_not_reindexed(docs):
    client, folder = docs
    source = _add_source(client, "Documents", folder)
    _scan(client, source["id"])
    path = os.path.join(folder, "insurance.txt")
    os.utime(path, (time.time() + 10, time.time() + 10))
    result = _scan(client, source["id"])
    assert result["indexed"] == 0 and result["unchanged"] == 2


def test_deleted_and_renamed_files_follow_the_disk(docs):
    client, folder = docs
    source = _add_source(client, "Documents", folder)
    _scan(client, source["id"])

    os.remove(os.path.join(folder, "Recipes", "pasta.md"))
    os.rename(os.path.join(folder, "insurance.txt"), os.path.join(folder, "car-insurance.txt"))
    result = _scan(client, source["id"])
    assert result["removed"] == 2 and result["indexed"] == 1
    assert _search_files(client, "spaghetti") == []
    assert _search_files(client, "insurance") == ["car-insurance.txt"]


def test_doc_id_is_stable_across_edits(docs):
    client, folder = docs
    source = _add_source(client, "Documents", folder)
    _scan(client, source["id"])
    before = client.post("/search", json={"query": "insurance"}).json()["results"][0]["doc_id"]

    path = os.path.join(folder, "insurance.txt")
    _write(path, "The car insurance changed provider.")
    os.utime(path, (time.time() + 5, time.time() + 5))
    _scan(client, source["id"])
    after = client.post("/search", json={"query": "insurance"}).json()["results"][0]["doc_id"]
    assert before == after


def test_watcher_events_apply_changes(docs):
    from app.services import get_source_service

    client, folder = docs
    source = _add_source(client, "Documents", folder)
    _scan(client, source["id"])
    service = get_source_service()

    new_file = os.path.join(folder, "wifi.txt")
    _write(new_file, "The wifi password is on the back of the router.")
    service.apply_changes(source["id"], {new_file})
    assert _search_files(client, "router") == ["wifi.txt"]

    os.remove(new_file)
    service.apply_changes(source["id"], {new_file})
    assert _search_files(client, "router") == []

    # A deleted folder removes everything below it
    recipes = os.path.join(folder, "Recipes")
    os.remove(os.path.join(recipes, "pasta.md"))
    os.rmdir(recipes)
    service.apply_changes(source["id"], {recipes})
    assert _search_files(client, "spaghetti") == []


def test_exclude_patterns_and_non_recursive(docs):
    client, folder = docs
    source = _add_source(client, "Documents", folder, exclude_patterns=["insurance.*"], recursive=False)
    result = _scan(client, source["id"])
    assert result["indexed"] == 0  # top-level file excluded, subfolder not walked

    client.patch(f"/sources/{source['id']}", json={"exclude_patterns": [], "recursive": True})
    assert _scan(client, source["id"])["indexed"] == 2


def test_snapshots_hidden_folders_and_unsupported_files_are_skipped(docs):
    client, folder = docs
    _write(os.path.join(folder, ".snapshots", "1", "snapshot", "insurance.txt"), "car insurance copy")
    _write(os.path.join(folder, ".hidden", "secret.txt"), "car insurance hidden")
    _write(os.path.join(folder, "@eaDir", "thumb.txt"), "car insurance thumbnail")
    with open(os.path.join(folder, "program.exe"), "wb") as f:
        f.write(b"MZ\x00\x00")
    source = _add_source(client, "Documents", folder)
    _scan(client, source["id"])
    assert _search_files(client, "insurance") == ["insurance.txt"]


def test_symlinks_leaving_the_source_are_ignored(docs, tmp_path):
    client, folder = docs
    outside = tmp_path / "outside.txt"
    outside.write_text("top secret car insurance details")
    os.symlink(outside, os.path.join(folder, "link.txt"))
    os.symlink(os.path.join(folder, "insurance.txt"), os.path.join(folder, "inside-link.txt"))
    source = _add_source(client, "Documents", folder)
    _scan(client, source["id"])
    assert sorted(_search_files(client, "insurance")) == ["inside-link.txt", "insurance.txt"]
    assert _search_files(client, "secret") == []


def test_unreadable_file_does_not_stop_the_scan(docs):
    client, folder = docs
    _write(os.path.join(folder, "empty.txt"), "   ")
    source = _add_source(client, "Documents", folder, enabled=False)  # disabled: no automatic scan
    result = _scan(client, source["id"])
    assert result["indexed"] == 2 and result["skipped"] == 1 and result["errors"] == 0
    # The skipped file is remembered, so the next scan doesn't retry it
    assert _scan(client, source["id"])["unchanged"] == 3
    docs_listed = client.get("/documents").json()["documents"]
    assert sorted(d["filename"] for d in docs_listed) == ["insurance.txt", "pasta.md"]


# ---------------------------------------------------------------------------
# Validation and lifecycle
# ---------------------------------------------------------------------------


def test_source_path_must_be_inside_allowed_roots(docs, tmp_path):
    client, folder = docs
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    for bad in [str(elsewhere), "/etc", "relative/path", folder + "/../../elsewhere"]:
        r = client.post("/sources", json={"name": "x", "path": bad})
        assert r.status_code == 400, bad
    assert client.post("/sources", json={"name": "x", "path": folder + "/missing"}).status_code == 400


def test_overlapping_and_duplicate_sources_are_rejected(docs):
    client, folder = docs
    _add_source(client, "Documents", folder)
    assert client.post("/sources", json={"name": "Docs2", "path": folder + "/Recipes"}).status_code == 400
    assert (
        client.post("/sources", json={"name": "Parent", "path": os.path.dirname(folder)}).status_code == 400
    )
    assert client.post("/sources", json={"name": "documents", "path": folder}).status_code == 400


def test_deleting_a_source_drops_its_index_but_not_the_files(docs):
    client, folder = docs
    source = _add_source(client, "Documents", folder)
    _scan(client, source["id"])
    assert client.delete(f"/sources/{source['id']}").status_code == 200
    assert _search_files(client, "spaghetti") == []
    assert os.path.exists(os.path.join(folder, "Recipes", "pasta.md"))


def test_source_documents_cannot_be_deleted_individually(docs):
    client, folder = docs
    source = _add_source(client, "Documents", folder)
    _scan(client, source["id"])
    doc_id = client.post("/search", json={"query": "spaghetti"}).json()["results"][0]["doc_id"]
    assert client.delete(f"/documents/{doc_id}").status_code == 409
    assert os.path.exists(os.path.join(folder, "Recipes", "pasta.md"))


def test_citations_carry_source_and_open_the_original_file(docs):
    client, folder = docs
    source = _add_source(client, "Documents", folder)
    _scan(client, source["id"])
    citation = client.post("/ask", json={"question": "how do I cook spaghetti?"}).json()["citations"][0]
    assert citation["source_name"] == "Documents"
    assert citation["doc_path"] == "Recipes/pasta.md"
    assert citation["heading"] == "Pasta"

    r = client.get(f"/documents/{citation['doc_id']}/file")
    assert r.status_code == 200
    assert b"spaghetti" in r.content


def test_search_can_be_limited_to_sources_or_uploads(docs):
    import io

    client, folder = docs
    source = _add_source(client, "Documents", folder)
    _scan(client, source["id"])
    client.post(
        "/ingest",
        files={"files": ("upload.txt", io.BytesIO(b"Upload about spaghetti carbonara"), "text/plain")},
    )

    assert len(_search_files(client, "spaghetti")) == 2
    assert _search_files(client, "spaghetti", source_ids=[source["id"]], include_uploads=False) == [
        "Recipes/pasta.md"
    ]
    only_uploads = client.post("/search", json={"query": "spaghetti", "source_ids": []}).json()["results"]
    assert [r["filename"] for r in only_uploads] == ["upload.txt"]


# ---------------------------------------------------------------------------
# Access control by group
# ---------------------------------------------------------------------------


def _login(client, username: str, password: str = "password123") -> dict:
    token = client.post("/auth/login", json={"username": username, "password": password}).json()[
        "access_token"
    ]
    return {"Authorization": f"Bearer {token}"}


def _register(client, username: str, headers: dict | None = None) -> dict:
    r = client.post(
        "/auth/register",
        json={"username": username, "email": f"{username}@example.com", "password": "password123"},
        headers=headers or {},
    )
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture
def secured(share, make_client):
    """Auth on; 'Family' share is open to everyone, 'Finance' only to group 'parents'."""
    root, env = share
    family = os.path.join(root, "Family")
    finance = os.path.join(root, "Finance")
    _write(
        os.path.join(family, "holiday.txt"), "Holiday plan: Lisbon in July, budget planning with the kids."
    )
    _write(os.path.join(finance, "salary.txt"), "Salary statement and budget planning for the year.")

    client = make_client(NAI_AUTH_ENABLED="true", **env)
    _register(client, "admin")
    admin = _login(client, "admin")
    user = _register(client, "kid", admin)
    _register(client, "mum", admin)
    mum_id = next(u["id"] for u in client.get("/auth/users", headers=admin).json() if u["username"] == "mum")
    r = client.put(f"/auth/users/{mum_id}/groups", json={"groups": ["Parents"]}, headers=admin)
    assert r.status_code == 200 and r.json()["groups"] == ["Parents"]

    for name, path, groups in [("Family", family, []), ("Finance", finance, ["parents"])]:
        r = client.post(
            "/sources", json={"name": name, "path": path, "allowed_groups": groups}, headers=admin
        )
        assert r.status_code == 201, r.text
        assert client.post(f"/sources/{r.json()['id']}/scan?wait=true", headers=admin).status_code == 200
    return client, admin, _login(client, "kid"), _login(client, "mum"), user


def test_restricted_sources_are_invisible_to_other_users(secured):
    client, admin, kid, mum, _ = secured

    def files(headers):
        r = client.post("/search", json={"query": "budget planning"}, headers=headers)
        return sorted(res["filename"] for res in r.json()["results"])

    assert files(admin) == ["holiday.txt", "salary.txt"]
    assert files(mum) == ["holiday.txt", "salary.txt"]
    assert files(kid) == ["holiday.txt"]

    # Asking for the restricted source explicitly doesn't help either
    finance_id = next(s["id"] for s in client.get("/sources", headers=admin).json() if s["name"] == "Finance")
    r = client.post("/search", json={"query": "salary", "source_ids": [finance_id]}, headers=kid)
    assert r.json()["results"] == []

    ask = client.post("/ask", json={"question": "salary statement"}, headers=kid).json()
    assert all(c["filename"] != "salary.txt" for c in ask["citations"])


def test_restricted_documents_cannot_be_listed_or_downloaded(secured):
    client, admin, kid, _, _ = secured
    salary = next(
        d
        for d in client.get("/documents", headers=admin).json()["documents"]
        if d["filename"] == "salary.txt"
    )
    assert [d["filename"] for d in client.get("/documents", headers=kid).json()["documents"]] == [
        "holiday.txt"
    ]
    assert client.get(f"/documents/{salary['doc_id']}", headers=kid).status_code == 404
    assert client.get(f"/documents/{salary['doc_id']}/file", headers=kid).status_code == 404
    assert client.get(f"/documents/{salary['doc_id']}/chunks", headers=kid).status_code == 404


def test_users_see_only_their_sources_without_paths(secured):
    client, admin, kid, mum, _ = secured
    kid_sources = client.get("/sources", headers=kid).json()
    assert [s["name"] for s in kid_sources] == ["Family"]
    assert kid_sources[0]["path"] is None
    assert sorted(s["name"] for s in client.get("/sources", headers=mum).json()) == ["Family", "Finance"]
    assert all(s["path"] for s in client.get("/sources", headers=admin).json())


def test_only_admins_manage_sources_and_groups(secured, share):
    client, _, kid, _, user = secured
    root, _ = share
    assert client.post("/sources", json={"name": "x", "path": root}, headers=kid).status_code == 403
    assert client.post("/sources/1/scan", headers=kid).status_code == 403
    assert client.delete("/sources/1", headers=kid).status_code == 403
    assert (
        client.put(f"/auth/users/{user['id']}/groups", json={"groups": ["parents"]}, headers=kid).status_code
        == 403
    )
    assert client.get("/system", headers=kid).status_code == 403
