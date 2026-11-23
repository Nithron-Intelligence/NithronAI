"""Keyword-only mode: NAI_EMBEDDINGS=auto turns semantic search off where memory can't fit the embedding model."""

from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache

import pytest
from pydantic import ValidationError

from app import hardware
from app.config import Settings
from app.hardware import EMBEDDINGS_MIN_MEMORY_GB, HardwareInfo, embeddings_auto_decision

from .conftest import FakeEmbeddingProvider
from .test_retrieval import _embed_all, _upload

# A 2 GB NAS (no container limit), and docker --memory limits of 2g, 3g (NithronOS template) and 4g (TrueNAS).
BOX_2GB = HardwareInfo(cpu_count=2, memory_gb=1.9, physical_cores=2, memory_available_gb=1.1)
LIMIT_2G = HardwareInfo(cpu_count=2, memory_gb=2.0, physical_cores=16, memory_available_gb=1.9)
LIMIT_3G = HardwareInfo(cpu_count=2, memory_gb=3.0, physical_cores=16, memory_available_gb=2.9)
LIMIT_4G = HardwareInfo(cpu_count=2, memory_gb=4.0, physical_cores=16, memory_available_gb=3.0)

OLD_DEFAULT = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
NEW_DEFAULT = Settings.model_fields["embeddings_model"].default


@pytest.mark.parametrize(
    ("profile", "expected"),
    [(BOX_2GB, False), (LIMIT_2G, False), (LIMIT_3G, True), (LIMIT_4G, True)],
)
def test_auto_decision_by_memory(profile: HardwareInfo, expected: bool) -> None:
    on, reason = embeddings_auto_decision(profile)
    assert on is expected
    assert f"{profile.memory_gb:g} GB RAM" in reason
    if not expected:
        assert "2.5+ GB" in reason and "keyword search only" in reason


def test_threshold_is_inclusive_and_ignores_free_memory() -> None:
    assert EMBEDDINGS_MIN_MEMORY_GB == 2.5
    at_threshold = HardwareInfo(cpu_count=2, memory_gb=2.5, memory_available_gb=0.5)
    assert embeddings_auto_decision(at_threshold)[0] is True
    assert embeddings_auto_decision(HardwareInfo(cpu_count=2, memory_gb=2.4))[0] is False


@pytest.mark.parametrize(
    ("raw", "mode"),
    [("auto", "auto"), ("on", "on"), ("TRUE", "on"), ("1", "on"), ("off", "off"), ("no", "off")],
)
def test_embeddings_setting_is_normalized(raw: str, mode: str) -> None:
    assert Settings(embeddings=raw).embeddings == mode


def test_embeddings_setting_rejects_unknown_values() -> None:
    with pytest.raises(ValidationError, match="NAI_EMBEDDINGS must be auto, on or off"):
        Settings(embeddings="sometimes")


def test_default_is_auto() -> None:
    assert Settings.model_fields["embeddings"].default == "auto"


# ---------------------------------------------------------------------------
# The running app
# ---------------------------------------------------------------------------


def _pretend_hardware(monkeypatch: pytest.MonkeyPatch, profile: HardwareInfo) -> None:
    # lru_cache wrapper: reset_services() calls detect_hardware.cache_clear()
    monkeypatch.setattr(hardware, "detect_hardware", lru_cache(maxsize=1)(lambda: profile))


class CountingProvider(FakeEmbeddingProvider):
    """Records every construction: loading the model is what keyword-only mode must avoid."""

    loads = 0

    def __init__(self, settings=None):
        type(self).loads += 1


def _auto_env(fake_embeddings: dict[str, str], **extra: str) -> dict[str, str]:
    return {**fake_embeddings, "NAI_EMBEDDINGS": "auto", **extra}


def test_small_box_runs_keyword_only_without_loading_the_model(make_client, fake_embeddings, monkeypatch):
    from app.services import get_embedding_service
    from app.services.embeddings import register_provider

    _pretend_hardware(monkeypatch, LIMIT_2G)
    CountingProvider.loads = 0
    register_provider("fake", CountingProvider)
    c = make_client(**_auto_env(fake_embeddings))
    _upload(c, "car.txt", "Car insurance renewal letter.")

    r = c.post("/search", json={"query": "insurance"}).json()
    assert r["method"] == "bm25" and len(r["results"]) == 1
    rejected = c.post("/search", json={"query": "insurance", "method": "embedding"})
    assert rejected.status_code == 400 and "keyword search only" in rejected.text

    stats = c.get("/system").json()["features"]["embeddings"]
    assert stats["mode"] == "auto-off" and stats["enabled"] is False and stats["state"] == "disabled"
    assert "2 GB RAM" in stats["reason"] and "2.5+ GB" in stats["reason"]
    health = c.get("/health").json()
    assert health["status"] == "ok" and "embeddings" not in health["components"]

    service = get_embedding_service()
    assert service.embed_pending() == 0 and not service.is_available()
    assert CountingProvider.loads == 0


@pytest.mark.parametrize("profile", [LIMIT_3G, LIMIT_4G], ids=["3g", "4g"])
def test_nas_templates_keep_semantic_search(make_client, fake_embeddings, monkeypatch, profile):
    _pretend_hardware(monkeypatch, profile)
    c = make_client(**_auto_env(fake_embeddings))
    _upload(c, "car.txt", "Car insurance renewal letter.")
    assert _embed_all() == 1
    assert c.post("/search", json={"query": "automobile coverage"}).json()["method"] == "hybrid"
    stats = c.get("/system").json()["features"]["embeddings"]
    assert stats["mode"] == "auto-on" and stats["enabled"] is True


@pytest.mark.parametrize(
    ("env", "mode"),
    [
        ({"NAI_EMBEDDINGS": "on"}, "on"),  # an admin can force it on, even on a 2 GB box
        ({"NAI_EMBEDDINGS": "off"}, "off"),
        ({"NAI_EMBEDDINGS": "on", "NAI_EMBEDDINGS_ENABLED": "false"}, "off"),  # master switch wins
    ],
)
def test_explicit_settings_override_the_policy(make_client, fake_embeddings, monkeypatch, env, mode):
    from app.services import get_embedding_service

    _pretend_hardware(monkeypatch, BOX_2GB)
    make_client(**{**fake_embeddings, **env})
    assert get_embedding_service().decision()[0] == mode


def _index_with_old_default(make_client: Callable, fake_embeddings: dict[str, str]) -> None:
    """A 0.6.0 install: two files embedded with the old default model (MiniLM)."""
    from app.services.embeddings import register_provider

    class OldDefault(FakeEmbeddingProvider):
        name = "fastembed"
        model = OLD_DEFAULT

    register_provider("fastembed", OldDefault)
    c = make_client(
        **{**fake_embeddings, "NAI_EMBEDDINGS_PROVIDER": "fastembed", "NAI_EMBEDDINGS_MODEL": OLD_DEFAULT}
    )
    _upload(c, "car.txt", "Car insurance renewal letter.")
    _upload(c, "bill.txt", "Electricity bill for October.")
    assert _embed_all() == 2


class NewDefault(CountingProvider):
    name = "fastembed"
    model = NEW_DEFAULT


def test_upgrade_on_a_2gb_box_goes_keyword_only_without_a_reindex_prompt(
    make_client, fake_embeddings, monkeypatch
):
    """0.6.0 → 0.7.0 on a 2 GB box: keyword-only, no "re-index now" prompt, Granite never loaded, the old
    vectors stay in the database (nothing is deleted)."""
    from app.services import get_embedding_service
    from app.services.embeddings import register_provider

    _index_with_old_default(make_client, fake_embeddings)
    _pretend_hardware(monkeypatch, BOX_2GB)
    NewDefault.loads = 0
    register_provider("fastembed", NewDefault)
    c = make_client(**_auto_env(fake_embeddings, NAI_EMBEDDINGS_PROVIDER="fastembed"))

    stats = c.get("/system").json()["features"]["embeddings"]
    assert stats["mode"] == "auto-off"
    assert stats["reindex_required"] is False and stats["previous_models"] == {}
    assert stats["vectors"] == 2  # kept, in case the box gets more memory
    assert c.post("/search", json={"query": "insurance"}).json()["method"] == "bm25"
    assert c.post("/system/embeddings/reindex").json() == {
        "reindexing": False,
        "removed_vectors": 0,
        "pending": 0,
    }
    assert get_embedding_service().embed_pending() == 0
    assert NewDefault.loads == 0


def test_upgrade_with_enough_memory_asks_before_reindexing(make_client, fake_embeddings, monkeypatch):
    """Same data on a 3g container: semantic search on, so the existing ask-before-re-index flow applies."""
    from app.services import get_embedding_service
    from app.services.embeddings import register_provider

    _index_with_old_default(make_client, fake_embeddings)
    _pretend_hardware(monkeypatch, LIMIT_3G)
    register_provider("fastembed", NewDefault)
    c = make_client(**_auto_env(fake_embeddings, NAI_EMBEDDINGS_PROVIDER="fastembed"))
    service = get_embedding_service()
    assert service.is_available() and service.reindex_required
    assert service.embed_pending() == 0
    stats = c.get("/system").json()["features"]["embeddings"]
    assert stats["mode"] == "auto-on" and stats["reindex_required"] is True
    assert stats["previous_models"] == {f"fastembed:{OLD_DEFAULT}": 2}
