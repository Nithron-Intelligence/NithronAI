"""review.py for short sessions: progress, clean stop (q / Ctrl+C / Ctrl+D), resume, one-line summary."""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from types import ModuleType

import pytest

EVALS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EVALS))

import naibench as nb  # noqa: E402


def _review() -> ModuleType:
    spec = importlib.util.spec_from_file_location("nai_review_short", nb.BENCH_DIR / "review.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


review = _review()


@pytest.fixture
def questions(tmp_path: Path) -> Path:
    path = tmp_path / "questions.jsonl"
    shutil.copy(nb.QUESTIONS_FILE, path)
    return path


@pytest.fixture
def state(tmp_path: Path) -> Path:
    return tmp_path / "state" / "review-state.json"


def _asker(*answers: str | type[BaseException]) -> Callable[[str], str]:
    """Answers in order; an exception class is raised instead (Ctrl+C / Ctrl+D)."""
    queue: Iterator[str | type[BaseException]] = iter(answers)

    def ask(_: str) -> str:
        answer = next(queue)
        if isinstance(answer, type):
            raise answer
        return answer

    return ask


def _session(
    questions: Path, state: Path, *answers: str | type[BaseException]
) -> tuple[dict[str, int], list[str]]:
    lines: list[str] = []
    done = review.run(questions, "Test Reviewer", None, ask=_asker(*answers), out=lines.append, state=state)
    return done, lines


def _shown_ids(lines: list[str]) -> list[str]:
    return [line.split()[0] for line in lines if line.startswith("nb-")]


def _status(questions: Path) -> dict[str, str]:
    return {r["id"]: r.get("review_status", "unreviewed") for r in review.read_rows(questions)}


def test_each_item_shows_overall_and_session_progress(questions: Path, state: Path) -> None:
    _, lines = _session(questions, state, "a", "", "q")
    progress = [line for line in lines if "reviewed ·" in line]
    assert "[0/56 reviewed · item 1 of 56 this session]" in progress[0]
    assert "[1/56 reviewed · item 2 of 56 this session]" in progress[1]


@pytest.mark.parametrize("stop", ["q", KeyboardInterrupt, EOFError], ids=["q", "ctrl-c", "ctrl-d"])
def test_stopping_keeps_every_decision_and_prints_a_summary(
    questions: Path, state: Path, stop: str | type[BaseException]
) -> None:
    done, lines = _session(questions, state, "a", "", "r", "wrong page", stop)
    assert done == {"accepted": 1, "fixed": 0, "rejected": 1, "skipped": 0, "stopped": 1}
    status = _status(questions)
    assert (
        status["nb-001"] == "accepted" and status["nb-002"] == "rejected" and status["nb-003"] == "unreviewed"
    )
    assert lines[-1] == (
        "stopped early: 1 accepted, 0 fixed, 1 rejected, 0 skipped this session; "
        "questions.jsonl: 2/56 reviewed, 1 usable (accepted or fixed), 54 left"
    )
    nb.load_all_items(questions)  # the file is still valid after the interruption


def test_ctrl_c_in_the_middle_of_a_note_saves_nothing_for_that_item(questions: Path, state: Path) -> None:
    done, _ = _session(questions, state, "a", KeyboardInterrupt)  # Ctrl+C at the "note" prompt
    assert done["accepted"] == 0 and done["stopped"] == 1
    assert _status(questions)["nb-001"] == "unreviewed"


def test_next_session_resumes_after_the_last_item_and_brings_skips_back_last(
    questions: Path, state: Path
) -> None:
    _session(questions, state, "s", "a", "", "q")  # skip nb-001, accept nb-002, quit at nb-003
    assert json.loads(state.read_text(encoding="utf-8")) == {str(questions.resolve()): "nb-002"}

    _, lines = _session(questions, state, "a", "", "q")
    shown = _shown_ids(lines)
    assert shown == ["nb-003", "nb-004"]  # resumed after nb-002; nb-003 accepted, quit at nb-004
    assert lines[0].startswith("55 item(s) to review") and "1/56 reviewed so far" in lines[0]

    rows = review.read_rows(questions)
    order = [rows[i]["id"] for i in review.todo_order(rows, None, "nb-003")]
    assert order[0] == "nb-004" and order[-1] == "nb-001"  # the skipped item comes at the end of the round


def test_a_finished_round_says_done(questions: Path, state: Path) -> None:
    lines: list[str] = []
    done = review.run(
        questions, "Test Reviewer", ["nb-005"], ask=_asker("a", ""), out=lines.append, state=state
    )
    assert done["stopped"] == 0 and lines[-1].startswith("done: 1 accepted")


def test_position_file_is_outside_the_repo_and_overridable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("NAI_REVIEW_STATE", raising=False)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    assert review.state_file() == tmp_path / "cache" / "nai-bench" / "review-state.json"
    monkeypatch.setenv("NAI_REVIEW_STATE", str(tmp_path / "x.json"))
    assert review.state_file() == tmp_path / "x.json"
    assert review.load_position(tmp_path / "missing.json", Path("q.jsonl")) is None
    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
    assert review.load_position(tmp_path / "broken.json", Path("q.jsonl")) is None


def test_excerpts_come_from_text_corpus_files_when_there_is_no_source_text(tmp_path: Path) -> None:
    (tmp_path / "corpus" / "Gesetze").mkdir(parents=True)
    (tmp_path / "corpus" / "Gesetze" / "act.txt").write_text("Article 1. Text of the act.", encoding="utf-8")
    (tmp_path / "corpus" / "scan.pdf").write_bytes(b"%PDF-1.4")
    manifest = [{"file": "Gesetze/act.txt", "language": "en"}, {"file": "scan.pdf", "language": "en"}]
    (tmp_path / "corpus-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    texts = review.source_texts(tmp_path / "questions-dev.jsonl")
    assert texts["Gesetze/act.txt"] == "Article 1. Text of the act."
    assert texts["scan.pdf"].startswith("(not a text file")
