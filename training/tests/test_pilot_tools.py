"""Vane 1 pilot data tools: license gate, deterministic corpus specs, seeded passage selection."""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import pytest

EMBED = Path(__file__).resolve().parents[1] / "embed"
sys.path.insert(0, str(EMBED))

import fetch_public  # noqa: E402
import generate_corpus  # noqa: E402
import select_passages  # noqa: E402


@pytest.mark.parametrize(
    "license_text",
    ["CC-BY-SA-4.0", "CC BY-SA 3.0", "Creative Commons ShareAlike", "CC-BY-NC-4.0", "CC BY-ND"],
)
def test_public_fetcher_refuses_share_alike_nc_and_nd(license_text: str) -> None:
    with pytest.raises(ValueError, match="not allowed"):
        fetch_public.check_license(license_text)


@pytest.mark.parametrize(
    "license_text", ["CC0-1.0", "CC-BY-4.0", "public domain (17 U.S.C. § 105)", "EU reuse with attribution"]
)
def test_public_fetcher_accepts_allowed_licenses(license_text: str) -> None:
    fetch_public.check_license(license_text)


def test_public_fetcher_refuses_nai_bench_targets() -> None:
    with pytest.raises(ValueError, match="nai-bench"):
        fetch_public.fetch([], EMBED.parents[1] / "evals" / "nai-bench" / "x")


def test_corpus_specs_are_deterministic_and_cover_every_language() -> None:
    a, b = generate_corpus.specs(4, seed=13), generate_corpus.specs(4, seed=13)
    assert a == b and len(a) == 4 * len(generate_corpus.LANGUAGES)
    assert {s["language"] for s in a} == set(generate_corpus.LANGUAGES)


def test_selection_is_seeded_spread_over_languages_and_guarded(tmp_path: Path) -> None:
    rows = [
        {"id": f"{lang}{i}", "text": "t", "language": lang, "author": "qwen2.5:7b"}
        for lang in "ab"
        for i in range(10)
    ]
    chosen = select_passages.sample(rows, 6, random.Random(13))
    assert sorted(r["language"] for r in chosen) == ["a", "a", "a", "b", "b", "b"]
    assert chosen == select_passages.sample(rows, 6, random.Random(13))
    bad = tmp_path / "bad.jsonl"
    bad.write_text(json.dumps({"id": "x", "text": "t", "use": "eval-only"}) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="eval-only"):
        list(select_passages.read_training_rows(bad))
