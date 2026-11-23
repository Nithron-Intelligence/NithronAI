"""NAS adapters: platform selection and share discovery (GET /sources/discover)."""

from __future__ import annotations

import os

from app.config import Settings
from app.nas import ADAPTERS, get_nas_adapter
from app.nas.base import discover_mounted_shares


def test_adapter_comes_from_setting_and_falls_back_to_generic() -> None:
    assert get_nas_adapter(Settings(nas_platform="nithronos")).name == "nithronos"
    assert get_nas_adapter(Settings(nas_platform="NithronOS ")).name == "nithronos"
    assert get_nas_adapter(Settings(nas_platform="beos")).name == "generic"
    assert set(ADAPTERS) == {"generic", "nithronos"}


def test_discovery_lists_first_level_folders_and_skips_nas_internals(tmp_path) -> None:
    for name in ("Familie", "Arbeit", "@eaDir", "#recycle", ".snapshots"):
        (tmp_path / name).mkdir()
    (tmp_path / "notes.txt").write_text("not a share")
    os.symlink(tmp_path / "Arbeit", tmp_path / "link-to-arbeit")

    shares = discover_mounted_shares([str(tmp_path), str(tmp_path / "missing")], [str(tmp_path / "Arbeit")])

    assert [(s.name, s.already_added) for s in shares] == [("Arbeit", True), ("Familie", False)]

    # A folder that contains an existing source overlaps it too, so it can't be added either.
    nested = discover_mounted_shares([str(tmp_path)], [str(tmp_path / "Familie" / "Fotos")])
    assert {s.name: s.already_added for s in nested}["Familie"] is True


def test_discover_endpoint_is_admin_only_and_marks_added_sources(share, make_client) -> None:
    root, env = share
    os.mkdir(os.path.join(root, "Photos"))
    client = make_client(NAI_NAS_PLATFORM="nithronos", **env)
    assert (
        client.post("/sources", json={"name": "docs", "path": os.path.join(root, "Documents")}).status_code
        == 201
    )

    data = client.get("/sources/discover").json()

    assert data["platform"] == "nithronos"
    assert data["capabilities"]["share_discovery"] is True
    assert {s["name"]: s["already_added"] for s in data["shares"]} == {"Documents": True, "Photos": False}

    secured = make_client(NAI_AUTH_ENABLED="true", **env)
    assert secured.get("/sources/discover").status_code == 401
