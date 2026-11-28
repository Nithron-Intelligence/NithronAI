"""Reranker auto policy: hardware profiles, cgroup-aware detection, setting normalization."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app import hardware
from app.config import Settings
from app.hardware import HardwareInfo, reranker_auto_decision

# Simulated NAS from evals/results/simulated-nas-2026-11-23.md: docker --cpus=2 --memory=4g on a 16-core host.
SIMULATED_NAS = HardwareInfo(
    cpu_count=2, memory_gb=4.0, physical_cores=16, memory_available_gb=3.0, arch="x86_64", avx2=True
)
N100_NAS = HardwareInfo(
    cpu_count=4, memory_gb=16.0, physical_cores=4, memory_available_gb=12.0, arch="x86_64", avx2=True
)
V1500B_NAS = HardwareInfo(
    cpu_count=8, memory_gb=8.0, physical_cores=4, memory_available_gb=5.0, arch="x86_64", avx2=True
)
DESKTOP = HardwareInfo(
    cpu_count=32, memory_gb=32.0, physical_cores=16, memory_available_gb=20.0, arch="x86_64", avx2=True
)
ARM_8_CORE = HardwareInfo(
    cpu_count=8, memory_gb=16.0, physical_cores=8, memory_available_gb=10.0, arch="aarch64"
)


@pytest.mark.parametrize(
    ("profile", "expected", "reason_part"),
    [
        (SIMULATED_NAS, False, "2 cores"),
        (N100_NAS, False, "needs 8+ cores"),
        (V1500B_NAS, False, "4 cores"),  # 8 threads but 4 physical cores (SMT)
        (DESKTOP, True, "16 cores"),
        (ARM_8_CORE, True, "8 cores"),
    ],
)
def test_auto_decision_by_hardware(profile: HardwareInfo, expected: bool, reason_part: str) -> None:
    on, reason = reranker_auto_decision(profile)
    assert on is expected
    assert reason_part in reason


def test_auto_needs_avx2_ram_and_free_memory() -> None:
    no_avx2 = HardwareInfo(cpu_count=16, memory_gb=32, physical_cores=16, arch="x86_64", avx2=False)
    small_ram = HardwareInfo(cpu_count=16, memory_gb=6, physical_cores=16, arch="x86_64", avx2=True)
    busy = HardwareInfo(
        cpu_count=16, memory_gb=32, physical_cores=16, memory_available_gb=1.0, arch="x86_64", avx2=True
    )
    assert reranker_auto_decision(no_avx2) == (
        False,
        "16 cores, 32 GB RAM, no AVX2 (int8 inference would be too slow)",
    )
    assert "8+ GB RAM" in reranker_auto_decision(small_ram)[1]
    assert "only 1 GB free" in reranker_auto_decision(busy)[1]


def test_cgroup_limits_are_what_the_container_sees(monkeypatch: pytest.MonkeyPatch) -> None:
    files = {
        "/sys/fs/cgroup/cpu.max": "200000 100000",
        "/sys/fs/cgroup/memory.max": str(4 * 1024**3),
        "/sys/fs/cgroup/memory.current": str(1 * 1024**3),
    }
    monkeypatch.setattr(hardware, "_read", files.get)
    assert hardware._cgroup_cpu_limit() == 2.0
    assert hardware._cgroup_memory_gb() == (4.0, 3.0)

    files["/sys/fs/cgroup/cpu.max"] = "max 100000"
    files["/sys/fs/cgroup/memory.max"] = "max"
    assert hardware._cgroup_cpu_limit() is None
    assert hardware._cgroup_memory_gb() == (None, None)


def test_cpuinfo_counts_physical_cores_and_avx2(monkeypatch: pytest.MonkeyPatch) -> None:
    cpuinfo = "\n".join(
        f"processor\t: {n}\nphysical id\t: 0\ncore id\t\t: {n % 4}\nflags\t\t: fpu sse2 avx2\n"
        for n in range(8)
    )
    monkeypatch.setattr(hardware, "_read", lambda path: cpuinfo if path == "/proc/cpuinfo" else None)
    assert hardware._cpuinfo() == (4, True)


@pytest.mark.parametrize(
    ("raw", "mode"), [("true", "on"), ("1", "on"), ("FALSE", "off"), ("no", "off"), (" Auto ", "auto")]
)
def test_reranker_setting_accepts_old_and_new_values(raw: str, mode: str) -> None:
    assert Settings(reranker=raw).reranker == mode


def test_reranker_setting_rejects_unknown_values() -> None:
    with pytest.raises(ValidationError):
        Settings(reranker="sometimes")


def test_defaults_are_auto_bge_int8_top10() -> None:
    fields = Settings.model_fields
    assert fields["reranker"].default == "auto"
    assert fields["reranker_model"].default == "BAAI/bge-reranker-v2-m3-int8"
    assert fields["reranker_candidates"].default == 10


def test_system_reports_effective_state_and_reason(make_client, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_detect() -> HardwareInfo:
        return SIMULATED_NAS

    fake_detect.cache_clear = lambda: None  # type: ignore[attr-defined]  # like the real lru_cache
    monkeypatch.setattr(hardware, "detect_hardware", fake_detect)
    client = make_client(NAI_RERANKER="auto")
    reranker = client.get("/system").json()["features"]["reranker"]
    assert reranker["mode"] == "auto" and reranker["active"] is False
    assert reranker["reason"].startswith("auto, off: 2 cores")
    assert reranker["top_k"] == 10


def test_auto_stays_off_for_a_reranker_with_non_commercial_training_data() -> None:
    # bge-reranker-v2-m3 lists MS MARCO in its training data (lineage audit, decision 2026-11-26): auto
    # leaves it off even on fast hardware; NAI_RERANKER=on still uses it.
    on, reason = reranker_auto_decision(DESKTOP, "BAAI/bge-reranker-v2-m3-int8")
    assert on is False
    assert "not cleared" in reason and "NAI_RERANKER=on" in reason
    # weak hardware keeps its own, more useful reason
    assert reranker_auto_decision(SIMULATED_NAS, "BAAI/bge-reranker-v2-m3-int8")[1].startswith("2 cores")


def test_auto_turns_on_a_cleared_reranker_on_fast_hardware(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hardware, "LINEAGE_CLEARED_RERANKERS", frozenset({"clean/reranker"}))
    assert reranker_auto_decision(DESKTOP, "clean/reranker")[0] is True
    assert reranker_auto_decision(N100_NAS, "clean/reranker")[0] is False


def test_system_reports_auto_off_for_the_default_reranker_on_fast_hardware(
    make_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_detect() -> HardwareInfo:
        return DESKTOP

    fake_detect.cache_clear = lambda: None  # type: ignore[attr-defined]
    monkeypatch.setattr(hardware, "detect_hardware", fake_detect)
    client = make_client(NAI_RERANKER="auto")
    body = client.get("/system").json()
    reranker = body["features"]["reranker"]
    assert reranker["active"] is False and "not cleared" in reranker["reason"]
    assert any("NAI_RERANKER=on" in tip for tip in body["recommendations"])
