"""
Generate synthetic (query, passage) pairs with an open-weight teacher model.

For every passage, the teacher writes short questions a NAS user might ask that the
passage answers: some in the passage's language, some in other languages
(cross-lingual), some as keyword searches. Talks to any OpenAI-compatible
endpoint (Ollama by default). Only teacher models on the allow-list in common.py
are accepted (lab principle 3), and every pair records its provenance.

    python training/embed/generate_pairs.py --passages data/passages.jsonl \\
        --output data/pairs.jsonl --model qwen2.5:7b --limit 1000

Then run check_overlap.py before training.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from collections import Counter
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import httpx
from common import (
    append_jsonl,
    check_author,
    detect_language,
    read_jsonl,
    refuse_bench_path,
    teacher_license,
    write_jsonl,
)

PROMPT_VERSION = "pairs-v1"
LANGUAGE_NAMES = {"en": "English", "de": "German", "sv": "Swedish", "fr": "French", "pt": "Portuguese"}
MIN_QUERY_CHARS, MAX_QUERY_CHARS = 8, 200

SYSTEM_PROMPT = """You write search queries for a private file search engine on a home or small-office NAS.
Given one passage from a user's files, write queries that this passage answers well.
Rules:
- Each query must be answerable from the passage alone, and must not copy long phrases from it.
- Write like a real user: short, specific, sometimes informal ("how much was the dishwasher repair").
- Never invent facts that are not in the passage.
Reply with JSON only: {"queries": [{"text": "...", "language": "<code>", "style": "question|keywords"}]}"""


def user_prompt(passage: dict[str, Any], languages: list[str], per_passage: int) -> str:
    wanted = ", ".join(f"{LANGUAGE_NAMES.get(code, code)} ({code})" for code in languages)
    return (
        f"Passage (from the file {passage.get('file')}):\n<<<\n{passage['text']}\n>>>\n\n"
        f"Write {per_passage} queries in these languages: {wanted}. "
        "At least one should be a keyword-style search, the rest natural questions."
    )


def pick_languages(
    passage: dict[str, Any], all_languages: list[str], rng: random.Random, count: int
) -> list[str]:
    """The passage's own language plus other languages for cross-lingual queries."""
    own = passage.get("language") or "en"
    others = [lang for lang in all_languages if lang != own]
    rng.shuffle(others)
    return [own, *others[: max(0, count - 1)]]


def parse_queries(content: str) -> list[dict[str, Any]]:
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.S)  # Qwen3 thinking blocks
    match = re.search(r"\{.*\}", content, re.S)
    if not match:
        return []
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    queries = data.get("queries", []) if isinstance(data, dict) else []
    return [q for q in queries if isinstance(q, dict) and isinstance(q.get("text"), str)]


def ask_teacher(http: httpx.Client, args: argparse.Namespace, messages: list[dict[str, str]]) -> str | None:
    """One chat completion with retries; None if the teacher keeps failing (the run goes on)."""
    for attempt in range(1, args.retries + 1):
        try:
            response = http.post(
                "/chat/completions",
                json={"model": args.model, "temperature": args.temperature, "messages": messages},
            )
            response.raise_for_status()
            content: str = response.json()["choices"][0]["message"]["content"]
            return content
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
            print(f"  teacher call failed (attempt {attempt}/{args.retries}): {e}", file=sys.stderr)
            time.sleep(2**attempt)
    return None


def generate(
    http: httpx.Client, args: argparse.Namespace, passages: list[dict[str, Any]], license_id: str
) -> Iterator[dict[str, Any]]:
    rng = random.Random(args.seed)
    languages = [code.strip() for code in args.languages.split(",") if code.strip()]
    seen: set[str] = set()
    created = date.today().isoformat()
    stats = args.stats
    system = SYSTEM_PROMPT + ("\n/no_think" if args.no_think else "")
    for index, passage in enumerate(passages, 1):
        wanted = pick_languages(passage, languages, rng, args.languages_per_passage)
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_prompt(passage, wanted, args.per_passage)},
        ]
        content = ask_teacher(http, args, messages)
        if content is None:
            stats["failed_passages"] += 1
            continue
        for query in parse_queries(content):
            text = " ".join(query["text"].split())
            key = text.lower()
            if (
                not MIN_QUERY_CHARS <= len(text) <= MAX_QUERY_CHARS
                or key in seen
                or key in passage["text"].lower()
            ):
                continue
            claimed, detected = query.get("language"), detect_language(text)
            if detected and claimed and detected != claimed:
                stats["language_mismatch"] += 1  # teachers mislabel languages; keep labels trustworthy
                continue
            seen.add(key)
            stats["kept"] += 1
            yield {
                "query": text,
                "query_language": query.get("language"),
                "style": query.get("style"),
                "passage_id": passage["id"],
                "passage": passage["text"],
                "passage_language": passage.get("language"),
                # Same keys as nai-bench provenance (author, use) plus generation details.
                "provenance": {
                    "author": args.model,
                    "author_license": license_id,
                    "teacher_model": args.model,
                    "prompt_version": PROMPT_VERSION,
                    "created": created,
                    "passage_author": passage.get("author"),
                    "passage_license": passage.get("license"),
                    "passage_source": passage.get("source"),
                    "use": "training",
                },
            }
        if index % 50 == 0:
            print(f"  {index}/{len(passages)} passages", file=sys.stderr)


def select_passages(args: argparse.Namespace) -> list[dict[str, Any]]:
    """Passages to process: author-checked, shuffled (so a --limit pilot covers all files), minus done ones."""
    passages = list(read_jsonl(args.passages))
    for passage in passages:
        check_author(str(passage.get("author") or ""))
        if not passage.get("author"):
            raise ValueError(
                f"passage {passage.get('id')} has no author (re-run make_passages.py with --author)"
            )
    random.Random(args.seed).shuffle(passages)
    passages = passages[: args.limit] if args.limit else passages
    if args.resume and args.output.exists():
        done = {row["passage_id"] for row in read_jsonl(args.output)}
        passages = [p for p in passages if p["id"] not in done]
        print(f"resuming: {len(done)} passages already done", file=sys.stderr)
    return passages


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate synthetic query-passage pairs with a teacher model"
    )
    parser.add_argument("--passages", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", required=True, help="approved teacher, e.g. qwen2.5:7b")
    parser.add_argument("--api-base", default="http://localhost:11434/v1", help="OpenAI-compatible endpoint")
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--languages", default="en,de,sv,fr,pt")
    parser.add_argument("--languages-per-passage", type=int, default=2)
    parser.add_argument("--per-passage", type=int, default=3, help="queries requested per passage")
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--no-think", action="store_true", help="ask Qwen3-style models not to think aloud")
    parser.add_argument("--limit", type=int, help="only N passages (a random sample, see --seed)")
    parser.add_argument("--retries", type=int, default=3, help="teacher calls per passage before skipping it")
    parser.add_argument(
        "--resume", action="store_true", help="append to --output, skipping passages already done"
    )
    parser.add_argument("--seed", type=int, default=13)
    args = parser.parse_args()

    for path in (args.passages, args.output):
        refuse_bench_path(path)
    license_id = teacher_license(args.model)
    args.stats = Counter()
    passages = select_passages(args)
    headers = {"Authorization": f"Bearer {args.api_key}"} if args.api_key else {}
    with httpx.Client(base_url=args.api_base.rstrip("/"), headers=headers, timeout=600) as http:
        rows = generate(http, args, passages, license_id)
        count = append_jsonl(args.output, rows) if args.resume else write_jsonl(args.output, rows)
    print(
        f"wrote {count} pairs from {len(passages)} passages to {args.output} (teacher {args.model}, {license_id})"
    )
    print(f"dropped {args.stats['language_mismatch']} queries whose language did not match their label")
    if args.stats["failed_passages"]:
        print(f"{args.stats['failed_passages']} passages failed after retries; run again with --resume")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
