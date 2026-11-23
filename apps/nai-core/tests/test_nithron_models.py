"""Nithron model catalog: IDs, display names, parsing and hardware choice."""

from __future__ import annotations

import pytest

from app.hardware import GPUInfo, HardwareInfo, nithron_answering_model
from app.nithron_models import FAMILIES, answering_family, model_ref, parse_model_id


def test_every_family_name_is_one_syllable_and_branded() -> None:
    # One syllable each (checked by hand); a new family must be added here deliberately.
    assert {f.name for f in FAMILIES.values()} == {"Vane", "Loupe", "Tern", "Nox"}
    assert model_ref("nox", "1").display_name == "Nithron Nox 1"
    assert model_ref("tern", "1", "mini").display_name == "Nithron Tern 1 mini"


def test_ids_round_trip() -> None:
    ref = model_ref("vane", "1.5")
    assert ref.hf_id == "nithron/vane-1.5"
    assert parse_model_id("nithron/vane-1.5") == ref
    assert parse_model_id("tern-1-mini") == model_ref("tern", "1", "mini")
    assert parse_model_id("ollama/nithron/nox-2:q4_K_M") == model_ref("nox", "2")
    assert parse_model_id("vane-1-rc2") == model_ref("vane", "1")
    assert parse_model_id("tern-1-mini-rc1") == model_ref("tern", "1", "mini")


@pytest.mark.parametrize(
    "model_id",
    [
        "qwen2.5:1.5b",
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        "other/vane-1",
        "tern-1-huge",
        "",
    ],
)
def test_non_nithron_ids_are_not_parsed(model_id: str) -> None:
    assert parse_model_id(model_id) is None


def test_invalid_refs_are_rejected() -> None:
    with pytest.raises(ValueError):
        model_ref("glint", "1")
    with pytest.raises(ValueError):
        model_ref("tern", "1", "huge")


def test_hardware_picks_tern_or_nox() -> None:
    assert answering_family(None, 8, 4) == "tern"
    assert answering_family(None, 64, 16) == "nox"
    assert answering_family(24, 16, 8) == "nox"
    small_nas = HardwareInfo(cpu_count=4, memory_gb=4)
    assert nithron_answering_model(small_nas)["display_name"] == "Nithron Tern 1 mini"
    gpu_pc = HardwareInfo(cpu_count=16, memory_gb=32, gpus=[GPUInfo("amd", "RX 7900 XTX", 24)])
    assert nithron_answering_model(gpu_pc)["model_id"] == "nithron/nox-1"
