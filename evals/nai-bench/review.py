"""
nai-bench human review
======================

Shows unreviewed questions one at a time, with the gold answer, facts and an excerpt of each
gold source, and records your decision in questions.jsonl:

  a  accept   the item is correct as written
  f  fix      edit the item (opens $EDITOR on its JSON, or asks field by field), then accept it as fixed
  r  reject   the item is wrong or unusable; you give a reason (rejected items are never evaluated)
  s  skip     decide later
  q  quit

Only accepted and fixed items count toward published numbers (see V1_PLAN.md). Every
decision is written immediately, so you can stop at any time (q, Ctrl+C or Ctrl+D) and lose nothing.
Each item shows your progress ("23/100 reviewed"); the next session resumes after the last item you
looked at (skipped items come back at the end of the round), and every session ends with a one-line
summary. The position is kept in ~/.cache/nai-bench/review-state.json (NAI_REVIEW_STATE overrides).

    python evals/nai-bench/review.py                    # next unreviewed items
    python evals/nai-bench/review.py --reviewer "Jane"  # default: git config user.name
    python evals/nai-bench/review.py --id nb-038        # review (or re-review) one item
    python evals/nai-bench/review.py --summary          # counts per status
    python evals/nai-bench/review.py --file evals/nai-bench/v1/questions-dev.jsonl   # v1 dev split
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from naibench import (  # noqa: E402
    QUESTIONS_FILE,
    REVIEW_STATUSES,
    _item_from_json,
    load_manifest,
    manifest_for,
    review_summary,
    split_file_kind,
    validate,
)

# Corpus files shown as text when the manifest has no source text for them (downloaded v1 files).
TEXT_SUFFIXES = (".txt", ".md", ".csv", ".html", ".htm", ".xml", ".json", ".yml", ".yaml", ".py", ".sh")
EXCERPT_CHARS = 700
EDITABLE = (
    "question",
    "gold_answer",
    "gold_facts",
    "forbidden_facts",
    "gold_sources",
    "category",
    "difficulty",
)


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------


def read_rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    """Atomic rewrite, one JSON object per line, in the original order."""
    tmp = path.with_suffix(".jsonl.tmp")
    tmp.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    tmp.replace(path)


def source_texts(questions: Path) -> dict[str, str]:
    """corpus file -> text to excerpt: its source text (without front matter) if the manifest names one,
    else the corpus file itself when it is a text file."""
    manifest_path = manifest_for(questions)
    texts = {}
    for entry in load_manifest(manifest_path):
        if entry.get("source_text"):
            src = manifest_path.parent / entry["source_text"]
            texts[entry["file"]] = src.read_text(encoding="utf-8").split("\n---\n", 1)[-1]
            continue
        corpus_file = manifest_path.parent / "corpus" / entry["file"]
        if corpus_file.suffix.lower() in TEXT_SUFFIXES and corpus_file.is_file():
            texts[entry["file"]] = corpus_file.read_text(encoding="utf-8", errors="replace")
        else:
            texts[entry["file"]] = f"(not a text file: open {corpus_file})"
    return texts


def excerpt(text: str, facts: list[str]) -> str:
    """The part of a source around the first gold fact found in it (else its beginning)."""
    lowered = text.lower()
    for fact in facts:
        for alt in fact.split("|"):
            pos = lowered.find(alt.strip().lower())
            if alt.strip() and pos >= 0:
                start = max(0, pos - EXCERPT_CHARS // 2)
                return ("…" if start else "") + text[start : start + EXCERPT_CHARS].strip() + "…"
    return text[:EXCERPT_CHARS].strip() + ("…" if len(text) > EXCERPT_CHARS else "")


def show(row: dict[str, Any], texts: dict[str, str], out: Callable[[str], None], progress: str = "") -> None:
    out("")
    out("=" * 78 + (f"\n{progress}" if progress else ""))
    out(
        f"{row['id']}  [{row['category']}, {row['difficulty']}, {row['language']}]  status: {row.get('review_status')}"
    )
    out(f"Q: {row['question']}")
    if row.get("gold_answer"):
        out(f"Gold answer: {row['gold_answer']}")
        out(f"Gold facts: {row.get('gold_facts')}   Forbidden: {row.get('forbidden_facts', [])}")
    else:
        out(f"UNANSWERABLE. Note: {row.get('notes')}")
    out(f"Author: {row.get('provenance', {}).get('author')}")
    for source in row.get("gold_sources", []):
        where = ", ".join(
            x
            for x in (f"page {source.get('page')}" if source.get("page") else "", source.get("section") or "")
            if x
        )
        out(f"--- {source['file']}{' (' + where + ')' if where else ''}")
        out(excerpt(texts.get(source["file"], "(source text not found)"), row.get("gold_facts", [])))


# ---------------------------------------------------------------------------
# Decisions
# ---------------------------------------------------------------------------


def edit_with_editor(row: dict[str, Any]) -> dict[str, Any]:
    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR")
    if not editor:
        raise RuntimeError("no $EDITOR")
    editable = {k: row.get(k) for k in EDITABLE}
    with tempfile.NamedTemporaryFile("w+", suffix=".json", delete=False, encoding="utf-8") as handle:
        json.dump(editable, handle, ensure_ascii=False, indent=2)
        name = handle.name
    try:
        subprocess.run([*shlex.split(editor), name], check=True)
        changed = json.loads(Path(name).read_text(encoding="utf-8"))
    finally:
        os.unlink(name)
    return {**row, **{k: v for k, v in changed.items() if k in EDITABLE}}


def edit_by_prompt(row: dict[str, Any], ask: Callable[[str], str]) -> dict[str, Any]:
    """Field-by-field editing; Enter keeps a value; JSON for lists/objects."""
    updated = dict(row)
    for key in EDITABLE:
        current = json.dumps(row.get(key), ensure_ascii=False)
        answer = ask(f"  {key} [{current}]: ").strip()
        if answer:
            updated[key] = (
                json.loads(answer) if answer[:1] in "[{" or answer in ("null", "true", "false") else answer
            )
    return updated


def check_item(row: dict[str, Any], questions: Path | None = None) -> list[str]:
    """Validate one (edited) item the same way the loaders do; returns the problems."""
    try:
        item = _item_from_json(row)
    except (KeyError, TypeError) as e:
        return [f"missing or malformed field: {e}"]
    manifest = load_manifest(manifest_for(questions)) if questions else None
    return validate([item], manifest, check_counts=False)


def decide(
    row: dict[str, Any],
    reviewer: str,
    ask: Callable[[str], str],
    out: Callable[[str], None],
    use_editor: bool = True,
    questions: Path | None = None,
) -> dict[str, Any] | str:
    """Returns the updated row, or 'skip' / 'quit'."""
    while True:
        choice = ask("[a]ccept  [f]ix  [r]eject  [s]kip  [q]uit > ").strip().lower()[:1]
        stamp = {"reviewed_by": reviewer, "reviewed_at": date.today().isoformat()}
        if choice == "a":
            note = ask("note (optional): ").strip() or None
            return {**row, "review_status": "accepted", "review_note": note, **stamp}
        if choice == "f":
            try:
                fixed = edit_with_editor(row) if use_editor else edit_by_prompt(row, ask)
            except RuntimeError:
                fixed = edit_by_prompt(row, ask)
            except (subprocess.CalledProcessError, json.JSONDecodeError, OSError) as e:
                out(f"edit failed ({e}); the item is unchanged")
                continue
            problems = check_item(fixed, questions)
            if problems:
                out("the edited item is not valid, nothing saved:\n  " + "\n  ".join(problems))
                continue
            note = ask("what did you fix? ").strip() or "fixed in review"
            return {**fixed, "review_status": "fixed", "review_note": note, **stamp}
        if choice == "r":
            reason = ""
            while not reason:
                reason = ask("why reject? ").strip()
            return {**row, "review_status": "rejected", "review_note": reason, **stamp}
        if choice in ("s", "q"):
            return "skip" if choice == "s" else "quit"
        out("please answer a, f, r, s or q")


def state_file() -> Path:
    """Where review positions are kept (outside the repo): NAI_REVIEW_STATE, else the user cache."""
    if os.environ.get("NAI_REVIEW_STATE"):
        return Path(os.environ["NAI_REVIEW_STATE"])
    cache = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return cache / "nai-bench" / "review-state.json"


def load_position(state: Path, questions: Path) -> str | None:
    """Id of the last item looked at in ``questions`` (None if none or unreadable)."""
    try:
        data = json.loads(state.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    value = data.get(str(questions.resolve())) if isinstance(data, dict) else None
    return value if isinstance(value, str) else None


def save_position(state: Path, questions: Path, item_id: str) -> None:
    try:
        data = json.loads(state.read_text(encoding="utf-8"))
        data = data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        data = {}
    data[str(questions.resolve())] = item_id
    state.parent.mkdir(parents=True, exist_ok=True)
    tmp = state.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
    tmp.replace(state)


def todo_order(rows: list[dict[str, Any]], ids: list[str] | None, last_id: str | None) -> list[int]:
    """Row indexes to review: the given ids, else unreviewed items starting after ``last_id``
    (so skipped items come back at the end of a round instead of first)."""
    if ids:
        return [i for i, r in enumerate(rows) if r["id"] in ids]
    todo = [i for i, r in enumerate(rows) if r.get("review_status", "unreviewed") == "unreviewed"]
    last = next((i for i, r in enumerate(rows) if r["id"] == last_id), None)
    if last is None:
        return todo
    return [i for i in todo if i > last] + [i for i in todo if i <= last]


def decided(rows: list[dict[str, Any]]) -> int:
    """Items with any decision (accepted, fixed or rejected)."""
    return sum(1 for r in rows if r.get("review_status", "unreviewed") != "unreviewed")


def summary_line(done: dict[str, int], rows: list[dict[str, Any]], questions: Path) -> str:
    """One line: this session's decisions, then the file's overall progress."""
    session = ", ".join(f"{done[k]} {k}" for k in ("accepted", "fixed", "rejected", "skipped"))
    usable = sum(1 for r in rows if r.get("review_status") in ("accepted", "fixed"))
    how = "stopped early" if done.get("stopped") else "done"
    return (
        f"{how}: {session} this session; {questions.name}: {decided(rows)}/{len(rows)} reviewed, "
        f"{usable} usable (accepted or fixed), {len(rows) - decided(rows)} left"
    )


def run(
    path: Path,
    reviewer: str,
    ids: list[str] | None,
    ask: Callable[[str], str] = input,
    out: Callable[[str], None] = print,
    use_editor: bool = True,
    state: Path | None = None,
) -> dict[str, int]:
    """Review items until done or stopped; every decision and the position are saved at once.

    q, Ctrl+C (KeyboardInterrupt) and Ctrl+D (EOFError) all stop cleanly with ``stopped`` = 1.
    """
    state = state or state_file()
    rows = read_rows(path)
    texts = source_texts(path)
    todo = todo_order(rows, ids, None if ids else load_position(state, path))
    done = {"accepted": 0, "fixed": 0, "rejected": 0, "skipped": 0, "stopped": 0}
    out(f"{len(todo)} item(s) to review as {reviewer!r}; {decided(rows)}/{len(rows)} reviewed so far")
    for number, index in enumerate(todo, start=1):
        progress = f"[{decided(rows)}/{len(rows)} reviewed · item {number} of {len(todo)} this session]"
        try:
            show(rows[index], texts, out, progress)
            result = decide(rows[index], reviewer, ask, out, use_editor, path)
        except (KeyboardInterrupt, EOFError):
            out("")  # the prompt line was left open
            result = "quit"
        if result == "quit":
            done["stopped"] = 1
            break
        save_position(state, path, rows[index]["id"])
        if result == "skip":
            done["skipped"] += 1
            continue
        assert isinstance(result, dict)
        rows[index] = result
        write_rows(path, rows)  # every decision is saved at once
        done[result["review_status"]] += 1
    out(summary_line(done, rows, path))
    return done


def default_reviewer() -> str:
    try:
        name = subprocess.run(["git", "config", "user.name"], capture_output=True, text=True).stdout.strip()
    except OSError:
        name = ""
    return name or os.environ.get("USER", "unknown")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Review nai-bench questions one at a time")
    parser.add_argument("--file", type=Path, default=QUESTIONS_FILE)
    parser.add_argument("--reviewer", default=None, help="your name (default: git config user.name)")
    parser.add_argument("--id", action="append", help="review this item id (repeatable), even if reviewed")
    parser.add_argument(
        "--no-editor", action="store_true", help="edit fixes field by field instead of $EDITOR"
    )
    parser.add_argument("--summary", action="store_true", help="print counts per review status and exit")
    parser.add_argument(
        "--test-split",
        action="store_true",
        help="allow opening a test split (questions-test*.jsonl) for human review; never use it for tuning",
    )
    args = parser.parse_args(argv)
    if split_file_kind(args.file) == "test" and not args.test_split:
        parser.error(f"{args.file.name} is the test split: pass --test-split to review it (people only)")

    if args.summary:
        counts = review_summary(args.file, allow_test=args.test_split)
        print(
            " ".join(f"{s}={counts[s]}" for s in REVIEW_STATUSES),
            f"reviewed={counts['reviewed']}/{counts['total']}",
        )
        return 0
    reviewer = args.reviewer or default_reviewer()
    if re.search(r"claude|gpt|gemini", reviewer, re.I) or reviewer.strip().lower() in ("", "unknown", "root"):
        parser.error("reviews must be done by a named person: pass --reviewer 'Your Name'")
    if args.id:
        known = {r["id"] for r in read_rows(args.file)}
        for missing in sorted(set(args.id) - known):
            print(f"warning: no item with id {missing!r}", file=sys.stderr)
    run(args.file, reviewer, args.id, use_editor=not args.no_editor)  # prints the one-line summary
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
