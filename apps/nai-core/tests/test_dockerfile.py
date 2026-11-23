"""The image must work when started as another user (TrueNAS Apps run it as uid 568, HOME=/)."""

from __future__ import annotations

import re
from pathlib import Path

DOCKERFILE = Path(__file__).resolve().parents[1] / "Dockerfile"


def _env() -> dict[str, str]:
    text = DOCKERFILE.read_text(encoding="utf-8")
    return dict(re.findall(r"^\s*([A-Z_]+)=(\S+?)\s*\\?$", text, re.M))


def test_model_caches_live_in_the_data_volume() -> None:
    env = _env()
    assert env["NAI_DATA_DIR"] == "/app/data"
    assert env["HF_HOME"].startswith("/app/data/")  # writable for whichever uid owns the data volume


def test_bundled_data_is_not_in_a_private_home() -> None:
    env = _env()
    assert not env["NLTK_DATA"].startswith("/home/")
    assert "/home/nai/nltk_data" not in DOCKERFILE.read_text(encoding="utf-8")
