"""nai-bench v1 corpus: files match the manifest, licenses are open, provenance is complete."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

EVALS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EVALS))

import naibench as nb  # noqa: E402

FORBIDDEN_LICENSE_WORDS = ("sharealike", "share-alike", "-sa", "noncommercial", "non-commercial", "-nc")


def _fetcher() -> ModuleType:
    spec = importlib.util.spec_from_file_location("v1_fetch_corpus", nb.V1_DIR / "fetch_corpus.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def manifest() -> list[dict[str, object]]:
    if not nb.V1_MANIFEST_FILE.exists():
        pytest.skip("no v1 corpus yet")
    data: list[dict[str, object]] = json.loads(nb.V1_MANIFEST_FILE.read_text(encoding="utf-8"))
    return data


def test_v1_corpus_matches_its_manifest(manifest: list[dict[str, object]]) -> None:
    assert _fetcher().check() == []


def test_v1_files_have_open_licenses_and_full_provenance(manifest: list[dict[str, object]]) -> None:
    for entry in manifest:
        license_text = str(entry["license"]).lower().replace(" ", "")
        assert not any(word in license_text for word in FORBIDDEN_LICENSE_WORDS), entry["file"]
        assert entry["language"] in nb.LANGUAGES, entry["file"]
        assert entry.get("use") == "eval-only", entry["file"]
        if entry.get("source_url"):  # downloaded third-party file
            assert entry.get("retrieved") and entry.get("author"), entry["file"]


def test_every_download_source_is_in_the_manifest(manifest: list[dict[str, object]]) -> None:
    sources = json.loads((nb.V1_DIR / "sources.json").read_text(encoding="utf-8"))
    files = {str(e["file"]) for e in manifest}
    assert [s["file"] for s in sources if s["file"] not in files] == []


def test_gutenberg_strip_removes_header_and_licence() -> None:
    raw = (
        b"The Project Gutenberg eBook of X\r\n*** START OF THE PROJECT GUTENBERG EBOOK X ***\r\n\r\n"
        b"Chapter 1\r\nIt was a dark night.\r\n\r\n*** END OF THE PROJECT GUTENBERG EBOOK X ***\r\nlicence\r\n"
    )
    assert _fetcher().gutenberg_strip(raw) == b"Chapter 1\r\nIt was a dark night.\n"
    with pytest.raises(ValueError):
        _fetcher().gutenberg_strip(b"no markers here")


def test_gutenberg_strip_also_drops_the_old_end_of_ebook_line() -> None:
    raw = b"*** START OF X ***\r\nBody line\r\n\r\nEnd of Project Gutenberg's X, by Y\r\n\r\n*** END OF X ***\r\n"
    assert _fetcher().gutenberg_strip(raw) == b"Body line\n"


def test_fictional_v1_files_say_they_are_claude_written_and_eval_only(
    manifest: list[dict[str, object]],
) -> None:
    fictional = [e for e in manifest if e.get("source_text")]
    assert fictional, "no fictional files yet"
    for entry in fictional:
        assert "claude" in str(entry.get("author", "")).lower(), entry["file"]
        assert entry["provenance"] == "claude-authored" and entry["use"] == "eval-only", entry["file"]
        assert entry["license"] == "CC-BY-4.0" and (nb.V1_DIR / str(entry["source_text"])).is_file(), entry[
            "file"
        ]
