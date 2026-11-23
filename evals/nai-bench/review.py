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
decision is written immediately, so you can stop at any time.

    python evals/nai-bench/review.py                    # next unreviewed items
    python evals/nai-bench/review.py --reviewer "Jane"  # default: git config user.name
    python evals/nai-bench/review.py --id nb-038        # review (or re-review) one item
    python evals/nai-bench/review.py --summary          # counts per status
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

from naibench import QUESTIONS_FILE, REVIEW_STATUSES, _item_from_json, review_summary, validate  # noqa: E402

SRC_DIR = HERE / "corpus-src"
MANIFEST = HERE / "corpus-manifest.json"
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


def source_texts() -> dict[str, str]:
    """corpus file -> its source text (without front matter)."""
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    texts = {}
    for entry in manifest:
        src = HERE / entry["source_text"]
        body = src.read_text(encoding="utf-8").split("\n---\n", 1)[-1]
        texts[entry["file"]] = body
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


def show(row: dict[str, Any], texts: dict[str, str], out: Callable[[str], None]) -> None:
    out("")
    out("=" * 78)
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


def check_item(row: dict[str, Any]) -> list[str]:
    """Validate one (edited) item the same way the loaders do; returns the problems."""
    try:
        item = _item_from_json(row)
    except (KeyError, TypeError) as e:
        return [f"missing or malformed field: {e}"]
    return validate([item], check_counts=False)


def decide(
    row: dict[str, Any],
    reviewer: str,
    ask: Callable[[str], str],
    out: Callable[[str], None],
    use_editor: bool = True,
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
            problems = check_item(fixed)
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


def run(
    path: Path,
    reviewer: str,
    ids: list[str] | None,
    ask: Callable[[str], str] = input,
    out: Callable[[str], None] = print,
    use_editor: bool = True,
) -> dict[str, int]:
    rows = read_rows(path)
    texts = source_texts()
    todo = [
        i
        for i, r in enumerate(rows)
        if (r["id"] in ids if ids else r.get("review_status", "unreviewed") == "unreviewed")
    ]
    done = {"accepted": 0, "fixed": 0, "rejected": 0, "skipped": 0}
    out(f"{len(todo)} item(s) to review as {reviewer!r}")
    for index in todo:
        show(rows[index], texts, out)
        result = decide(rows[index], reviewer, ask, out, use_editor)
        if result == "quit":
            break
        if result == "skip":
            done["skipped"] += 1
            continue
        assert isinstance(result, dict)
        rows[index] = result
        write_rows(path, rows)  # every decision is saved at once
        done[result["review_status"]] += 1
    return done


def default_reviewer() -> str:
    try:
        name = subprocess.run(["git", "config", "user.name"], capture_output=True, text=True).stdout.strip()
    except OSError:
        name = ""
    return name or os.environ.get("USER", "unknown")


def main() -> int:
    parser = argparse.ArgumentParser(description="Review nai-bench questions one at a time")
    parser.add_argument("--file", type=Path, default=QUESTIONS_FILE)
    parser.add_argument("--reviewer", default=None, help="your name (default: git config user.name)")
    parser.add_argument("--id", action="append", help="review this item id (repeatable), even if reviewed")
    parser.add_argument(
        "--no-editor", action="store_true", help="edit fixes field by field instead of $EDITOR"
    )
    parser.add_argument("--summary", action="store_true", help="print counts per review status and exit")
    args = parser.parse_args()

    if args.summary:
        counts = review_summary(args.file)
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
    try:
        done = run(args.file, reviewer, args.id, use_editor=not args.no_editor)
    except (EOFError, KeyboardInterrupt):
        print("\nstopped; decisions made so far are saved")
        return 0
    print(f"\ndone: {done}")
    counts = review_summary(args.file)
    print(f"reviewed so far: {counts['reviewed']} of {counts['total']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
