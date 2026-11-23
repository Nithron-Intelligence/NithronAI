"""
nAI answer-quality evaluation on nai-bench
==========================================

Asks every nai-bench question through ``POST /ask/stream`` (so streaming is tested
too) and scores the answers. Deterministic checks always run; an LLM judge is
optional (``--judge-url``) and its rubric is ``JUDGE_RUBRIC`` below, quoted in
``evals/nai-bench/README.md``.

Deterministic metrics (answerable questions unless noted):
  fact_recall          share of the item's gold facts found in the answer text
  correct              every gold fact found
  citation_hit         a gold file is among the citations nAI returned
  inline_citation_precision
                       of the corpus files the answer text names, the share that are gold
                       (None when it names none)
  unsupported_numbers  numbers in the answer that appear in none of the cited passages
                       (a cheap hallucination signal; groundedness proxy)
  language_match       detected answer language == question language
  false_refusal        the answer says the files don't contain it, but they do
  correct_refusal      (unanswerable) the answer says the files don't contain it

The appended '**Sources:**' list is removed before scoring the answer text.

Usage:
    python evals/answers/eval_answers.py --output answers.json            # LLM answers
    python evals/answers/eval_answers.py --extractive --output answers.json
    python evals/answers/eval_answers.py --judge-url http://localhost:11434/v1 --judge-model qwen2.5:7b
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from naibench import (
    FINAL_RUN_HELP,
    QUESTIONS_FILE,
    BenchItem,
    NaiClient,
    answer_body,
    cli_load_items,
    contains_fact,
    detect_language,
    is_cross_lingual,
    is_refusal,
    load_manifest,
    matches_gold,
    mean,
    normalize,
    numbers_in,
)

JUDGE_RUBRIC = """You grade one answer from a question-answering system over a user's private files.
You get the question, the reference answer (or "UNANSWERABLE" if the files do not contain the answer),
the passages the system retrieved, and the system's answer.

Score each criterion and reply with JSON only:
{"correct": 0|1|2, "grounded": 0|1|2, "refusal_ok": true|false, "explanation": "<one sentence>"}

correct:    2 = agrees with the reference answer on every fact that matters;
            1 = partly right or missing a key fact; 0 = wrong, or answers an UNANSWERABLE question.
            For UNANSWERABLE questions: 2 if the answer says the files don't contain it, else 0.
grounded:   2 = every claim is supported by the retrieved passages; 1 = minor unsupported detail;
            0 = a key claim is not supported by the passages (even if it happens to be true).
refusal_ok: true if the answer refuses exactly when it should (refuses on UNANSWERABLE,
            answers otherwise); false if it refuses wrongly or invents an answer."""


# ---------------------------------------------------------------------------
# Asking
# ---------------------------------------------------------------------------


def ask(client: NaiClient, item: BenchItem, top_k: int, use_llm: bool) -> dict[str, Any]:
    """Run one question through /ask/stream and collect answer, citations and timings."""
    started = time.monotonic()
    first_token: float | None = None
    tokens: list[str] = []
    citations: list[dict[str, Any]] = []
    done: dict[str, Any] = {}
    errors: list[Any] = []
    for event, data in client.ask_stream(item.question, top_k=top_k, use_llm=use_llm):
        if event == "citations":
            citations = data
        elif event == "token":
            if first_token is None:
                first_token = time.monotonic() - started
            tokens.append(data.get("text", ""))
        elif event == "error":
            errors.append(data)
        elif event == "done":
            done = data
    return {
        "answer": "".join(tokens),
        "citations": citations,
        "method": done.get("method"),
        "model": done.get("model"),
        "stream_errors": errors,
        "streamed_tokens": len(tokens),
        "seconds_to_first_token": round(first_token, 3) if first_token is not None else None,
        "seconds_total": round(time.monotonic() - started, 3),
    }


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def named_files(text: str, corpus_files: list[str]) -> list[str]:
    """Corpus files whose file name appears in the text."""
    lowered = text.lower()
    return [f for f in corpus_files if Path(f).name.lower() in lowered]


def score(item: BenchItem, run: dict[str, Any], corpus_files: list[str]) -> dict[str, Any]:
    body = answer_body(run["answer"])
    refused = is_refusal(body)
    detected = detect_language(body)
    row: dict[str, Any] = {
        "id": item.id,
        "category": item.category,
        "language": item.language,
        "detected_language": detected,
        "language_match": None if detected is None else detected == item.language,
        "refused": refused,
    }
    if not item.answerable:
        row["correct_refusal"] = refused
        return row

    cited_paths = [c.get("doc_path", "") for c in run["citations"]]
    passages = " ".join(c.get("text", "") for c in run["citations"])
    named = named_files(body, corpus_files)
    facts = [contains_fact(body, f) for f in item.gold_facts]
    contradicted = any(contains_fact(body, f) for f in item.forbidden_facts)
    # A number is supported if it appears in the passages, the question or a cited file path
    # (source labels). Substring match on normalized text, so truncated CSV rows still count.
    supported_text = normalize(" ".join([passages, item.question, *cited_paths]))
    row.update(
        {
            "fact_recall": mean([1.0 if f else 0.0 for f in facts]),
            "correct": all(facts) and not contradicted,
            "citation_hit": any(matches_gold(p, g) for p in cited_paths for g in item.gold_files),
            "inline_citation_precision": (
                mean([1.0 if f in item.gold_files else 0.0 for f in named]) if named else None
            ),
            "unsupported_numbers": sorted(n for n in numbers_in(body) if n not in supported_text),
            # A refusal phrase next to the right facts ("the warranty does not include labour") is not a refusal.
            "false_refusal": refused and not all(facts),
        }
    )
    return row


def judge(
    http: httpx.Client, model: str, item: BenchItem, run: dict[str, Any], max_passage_chars: int = 1200
) -> dict[str, Any]:
    """Optional LLM-as-judge through any OpenAI-compatible /chat/completions endpoint."""
    passages = "\n---\n".join(
        f"[{c.get('doc_path')}, page {c.get('page')}]\n{c.get('text', '')[:max_passage_chars]}"
        for c in run["citations"]
    )
    reference = item.gold_answer if item.answerable else "UNANSWERABLE"
    user = (
        f"Question: {item.question}\n\nReference answer: {reference}\n\n"
        f"Retrieved passages:\n{passages}\n\nSystem answer:\n{answer_body(run['answer'])}"
    )
    response = http.post(
        "/chat/completions",
        json={
            "model": model,
            "temperature": 0,
            "messages": [{"role": "system", "content": JUDGE_RUBRIC}, {"role": "user", "content": user}],
        },
    )
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    match = re.search(r"\{.*\}", content, re.S)
    if not match:
        return {"judge_error": "no JSON in judge reply", "judge_raw": content[:500]}
    try:
        verdict: dict[str, Any] = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {"judge_error": "invalid JSON in judge reply", "judge_raw": content[:500]}
    return {f"judge_{k}": v for k, v in verdict.items()}


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

RATE_KEYS = (
    "fact_recall",
    "correct",
    "citation_hit",
    "inline_citation_precision",
    "language_match",
    "false_refusal",
)


def _rate(rows: list[dict[str, Any]], key: str) -> float | None:
    values = [float(r[key]) for r in rows if r.get(key) is not None]
    return round(mean(values), 4) if values else None


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    answerable = [r for r in rows if r["category"] != "unanswerable"]
    unanswerable = [r for r in rows if r["category"] == "unanswerable"]
    out: dict[str, Any] = {"n": len(rows), "answerable": len(answerable), "unanswerable": len(unanswerable)}
    for key in RATE_KEYS:
        out[key] = _rate(answerable, key)
    out["answers_with_unsupported_numbers"] = _rate(
        [{"x": bool(r["unsupported_numbers"])} for r in answerable], "x"
    )
    out["correct_refusal"] = _rate(unanswerable, "correct_refusal")
    out["language_match_all"] = _rate(rows, "language_match")
    for key in ("judge_correct", "judge_grounded"):
        values = [float(r[key]) / 2 for r in rows if isinstance(r.get(key), (int, float))]
        if values:
            out[f"{key}_norm"] = round(mean(values), 4)
    return out


def evaluate(
    client: NaiClient,
    items: list[BenchItem],
    top_k: int = 5,
    use_llm: bool = True,
    judge_client: httpx.Client | None = None,
    judge_model: str | None = None,
) -> dict[str, Any]:
    manifest = load_manifest()
    corpus_files = [e["file"] for e in manifest]
    rows, errors = [], []
    models, methods = set(), set()
    for item in items:
        try:
            run = ask(client, item, top_k, use_llm)
        except Exception as e:  # report and keep going
            errors.append({"id": item.id, "error": str(e)})
            continue
        models.add(run["model"])
        methods.add(run["method"])
        row = score(item, run, corpus_files)
        row["cross_lingual"] = "yes" if is_cross_lingual(item, manifest) else "no"
        if judge_client is not None and judge_model:
            try:
                row.update(judge(judge_client, judge_model, item, run))
            except Exception as e:
                row["judge_error"] = str(e)
        row.update(
            {
                "answer": run["answer"],
                "cited": [c.get("doc_path") for c in run["citations"]],
                "seconds_to_first_token": run["seconds_to_first_token"],
                "seconds_total": run["seconds_total"],
                "stream_errors": run["stream_errors"],
            }
        )
        rows.append(row)
    by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_category[row["category"]].append(row)
    latencies = sorted(r["seconds_total"] for r in rows)
    ttft = sorted(r["seconds_to_first_token"] for r in rows if r["seconds_to_first_token"] is not None)
    return {
        "use_llm": use_llm,
        "answer_methods": sorted(m for m in methods if m),
        "models": sorted(m for m in models if m),
        "judge_model": judge_model,
        "overall": aggregate(rows),
        "by_category": {k: aggregate(v) for k, v in sorted(by_category.items())},
        "by_cross_lingual": {
            flag: aggregate(
                [r for r in rows if r.get("cross_lingual") == flag and r["category"] != "unanswerable"]
            )
            for flag in ("yes", "no")
        },
        "latency": {
            "median_seconds_total": latencies[len(latencies) // 2] if latencies else None,
            "median_seconds_to_first_token": ttft[len(ttft) // 2] if ttft else None,
        },
        "errors": errors,
        "per_question": rows,
    }


def print_summary(report: dict[str, Any]) -> None:
    o = report["overall"]
    print(
        f"\nnai-bench answers ({'LLM: ' + ', '.join(report['models']) if report['use_llm'] else 'extractive'})"
    )
    for key in (*RATE_KEYS, "answers_with_unsupported_numbers", "correct_refusal", "language_match_all"):
        print(f"  {key:<34}{o.get(key)}")
    for key in ("judge_correct_norm", "judge_grounded_norm"):
        if key in o:
            print(f"  {key:<34}{o[key]}")
    print(f"  latency (median total / first token): {report['latency']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate nAI answer quality on nai-bench")
    parser.add_argument("--bench", type=Path, default=QUESTIONS_FILE)
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument(
        "--reviewed-only", action="store_true", help="only human-reviewed items (published numbers)"
    )
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--extractive", action="store_true", help="use_llm=false (quote passages, no LLM)")
    parser.add_argument("--judge-url", help="OpenAI-compatible base URL for the optional LLM judge")
    parser.add_argument("--judge-model", help="model name for the judge")
    parser.add_argument("--judge-api-key", default=None)
    parser.add_argument("--limit", type=int, help="only the first N questions (smoke runs)")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--final-run", action="store_true", help=FINAL_RUN_HELP)
    parser.add_argument("--label", default="eval_answers", help="run label for the test ledger")
    args = parser.parse_args(argv)

    items = cli_load_items(args.bench, args.reviewed_only, args.final_run, args.label)[: args.limit]
    judge_client = None
    if args.judge_url:
        headers = {"Authorization": f"Bearer {args.judge_api_key}"} if args.judge_api_key else {}
        judge_client = httpx.Client(base_url=args.judge_url.rstrip("/"), headers=headers, timeout=300)
    report = evaluate(
        NaiClient(args.api_url, args.api_key),
        items,
        top_k=args.top_k,
        use_llm=not args.extractive,
        judge_client=judge_client,
        judge_model=args.judge_model,
    )
    print_summary(report)
    if args.output:
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
