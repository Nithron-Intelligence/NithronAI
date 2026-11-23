"""nai-bench dev/test split guard: hash split, test files refused without --final-run, ledger of final runs."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest

EVALS = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(EVALS), str(EVALS / "retrieval"), str(EVALS / "answers")]

import eval_answers  # noqa: E402
import eval_retrieval  # noqa: E402
import naibench as nb  # noqa: E402
import run_baseline  # noqa: E402


class NetworkTouched(RuntimeError):
    """Raised by the stub client: the script got past item loading."""


@pytest.fixture
def split_dir(tmp_path: Path) -> Path:
    """A v1-shaped folder built from the v0 items: each item goes to the file its id hashes to."""
    shutil.copy(nb.MANIFEST_FILE, tmp_path / "corpus-manifest.json")
    rows = [json.loads(line) for line in nb.QUESTIONS_FILE.read_text(encoding="utf-8").splitlines() if line]
    for kind in nb.SPLITS:
        chosen = [r for r in rows if nb.split_of(r["id"]) == kind]
        (tmp_path / f"questions-{kind}.jsonl").write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in chosen), encoding="utf-8"
        )
    return tmp_path


@pytest.fixture
def ledger(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "results" / "test-ledger.jsonl"
    monkeypatch.setattr(nb, "TEST_LEDGER_FILE", path)
    return path


@pytest.fixture
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def stub(*args: Any, **kwargs: Any) -> None:
        raise NetworkTouched

    for module in (eval_retrieval, eval_answers, run_baseline):
        monkeypatch.setattr(module, "NaiClient", stub)


def test_split_is_a_stable_hash_of_the_id_with_about_40_percent_dev() -> None:
    ids = [f"v1-{n:04d}" for n in range(5000)]
    share = sum(nb.split_of(i) == "dev" for i in ids) / len(ids)
    assert 0.37 < share < 0.43
    # Pinned values: changing the rule would silently move items between splits.
    assert [nb.split_of(i) for i in ("v1-0001", "v1-0002", "v1-0003", "nb-001")] == [
        "test",
        "test",
        "dev",
        "test",
    ]


def test_split_file_kind_only_matches_split_files() -> None:
    assert nb.split_file_kind(Path("v1/questions-test.jsonl")) == "test"
    assert nb.split_file_kind(Path("v1/questions-dev.jsonl")) == "dev"
    assert nb.split_file_kind(Path("questions.jsonl")) is None
    assert nb.split_file_kind(Path("questions-testing.jsonl")) is None


def test_test_split_is_refused_without_final_run(split_dir: Path, ledger: Path) -> None:
    test_file = split_dir / "questions-test.jsonl"
    for load in (nb.load_items, nb.load_all_items, nb.review_summary):
        with pytest.raises(nb.TestSplitError, match="--final-run"):
            load(test_file)
    assert not ledger.exists()


def test_dev_split_loads_and_is_not_ledgered(split_dir: Path, ledger: Path) -> None:
    items = nb.load_items(split_dir / "questions-dev.jsonl")
    assert items and all(nb.split_of(i.id) == "dev" for i in items)
    assert not ledger.exists()


def test_final_run_loads_the_test_split_and_appends_to_the_ledger(split_dir: Path, ledger: Path) -> None:
    test_file = split_dir / "questions-test.jsonl"
    items = nb.load_items(test_file, final_run=True, run_label="vane-1-final")
    nb.load_items(test_file, reviewed_only=True, final_run=True, run_label="second")
    entries = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
    assert len(entries) == 2
    first = entries[0]
    assert (
        first["label"] == "vane-1-final" and first["items"] == len(items) and first["file"] == test_file.name
    )
    assert first["dataset_sha256"] == nb.dataset_sha256(test_file, split_dir / "corpus-manifest.json")
    assert entries[1]["reviewed_only"] is True and entries[1]["items"] == 0
    assert {"date", "commit"} <= first.keys()


def test_an_item_in_the_wrong_split_file_is_invalid(split_dir: Path) -> None:
    dev, test = split_dir / "questions-dev.jsonl", split_dir / "questions-test.jsonl"
    stray = test.read_text(encoding="utf-8").splitlines()[0]
    dev.write_text(dev.read_text(encoding="utf-8") + stray + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="hashes to the test split"):
        nb.load_items(dev)
    assert any("hashes to test" in e for e in nb.validate_splits(dev, test))


def test_validate_splits_checks_both_files_without_returning_items(split_dir: Path, ledger: Path) -> None:
    assert nb.validate_splits(split_dir / "questions-dev.jsonl", split_dir / "questions-test.jsonl") == []
    assert not ledger.exists()


@pytest.mark.parametrize(
    "main",
    [eval_retrieval.main, eval_answers.main, run_baseline.main],
    ids=["retrieval", "answers", "baseline"],
)
def test_tuning_scripts_cannot_load_the_test_split(
    main: Any, split_dir: Path, ledger: Path, no_network: None
) -> None:
    with pytest.raises(SystemExit, match=r"refused: .*test split"):
        main(["--bench", str(split_dir / "questions-test.jsonl")])
    assert not ledger.exists()
    with pytest.raises(NetworkTouched):  # the dev split gets past loading to the (stubbed) server
        main(["--bench", str(split_dir / "questions-dev.jsonl")])
    assert not ledger.exists()


@pytest.mark.parametrize(
    "main",
    [eval_retrieval.main, eval_answers.main, run_baseline.main],
    ids=["retrieval", "answers", "baseline"],
)
def test_scripts_record_final_runs_in_the_ledger(
    main: Any, split_dir: Path, ledger: Path, no_network: None
) -> None:
    with pytest.raises(NetworkTouched):
        main(["--bench", str(split_dir / "questions-test.jsonl"), "--final-run", "--label", "final-x"])
    (entry,) = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
    assert entry["label"] == "final-x"


def test_committed_v1_split_files_are_valid() -> None:
    if not nb.V1_DEV_FILE.exists() and not nb.V1_TEST_FILE.exists():
        pytest.skip("no v1 questions yet")
    assert nb.validate_splits() == []


def _review_module() -> Any:
    import importlib.util

    spec = importlib.util.spec_from_file_location("review", nb.BENCH_DIR / "review.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_review_tool_opens_the_test_split_only_with_test_split(
    split_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    review = _review_module()
    test_file = str(split_dir / "questions-test.jsonl")
    with pytest.raises(SystemExit):
        review.main(["--file", test_file, "--summary"])
    assert "--test-split" in capsys.readouterr().err
    assert review.main(["--file", test_file, "--summary", "--test-split"]) == 0
    assert "reviewed=0/" in capsys.readouterr().out
