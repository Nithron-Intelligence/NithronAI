"""
Run the full nai-bench evaluation against a running nAI server
==============================================================

Retrieval (per search method), extractive answers, LLM answers (when the server has
an LLM) and, optionally, an LLM judge. Writes ``results/<label>-<date>.json`` and a
short Markdown summary next to it, with the configuration that produced the numbers
(git commit, nAI version, embedding model, reranker, LLM, dataset hashes).

    docker compose -f infra/compose.bench.yaml up -d
    docker compose -f infra/compose.bench.yaml exec ollama ollama pull qwen2.5:1.5b
    python evals/run_baseline.py --index-corpus /shares/nai-bench
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any

import httpx

EVALS = Path(__file__).resolve().parent
sys.path[:0] = [str(EVALS), str(EVALS / "retrieval"), str(EVALS / "answers")]

import eval_answers  # noqa: E402
import eval_retrieval  # noqa: E402
from naibench import MANIFEST_FILE, QUESTIONS_FILE, NaiClient, load_items  # noqa: E402

RESULTS_DIR = EVALS / "results"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_commit() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=EVALS, capture_output=True, text=True
        )
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=EVALS, capture_output=True, text=True)
    except OSError:
        return None
    return out.stdout.strip() + ("+dirty" if dirty.stdout.strip() else "") if out.returncode == 0 else None


def metadata(client: NaiClient, label: str) -> dict[str, Any]:
    health = client.detailed_health()
    return {
        "label": label,
        "date": date.today().isoformat(),
        "git_commit": git_commit(),
        "nai_version": health.get("version"),
        "config": health.get("config"),
        "embeddings": {k: (health.get("embeddings") or {}).get(k) for k in ("provider", "model")},
        "index": health.get("index"),
        "dataset": {
            "questions_sha256": sha256_file(QUESTIONS_FILE),
            "corpus_manifest_sha256": sha256_file(MANIFEST_FILE),
        },
        "client_host": {"platform": platform.platform(), "python": platform.python_version()},
    }


def fmt(value: Any) -> str:
    return "–" if value is None else f"{value:.3f}" if isinstance(value, float) else str(value)


def markdown(report: dict[str, Any]) -> str:
    meta = report["meta"]
    retrieval = report["retrieval"]
    cfg = meta.get("config") or {}
    lines = [
        f"# nai-bench {meta['label']} – {meta['date']}",
        "",
        f"nAI {meta['nai_version']} at commit `{meta['git_commit']}`; embeddings "
        f"`{meta['embeddings']['model']}` ({meta['embeddings']['provider']}); reranker `{cfg.get('reranker')}`; "
        f"{retrieval['questions']} answerable + {retrieval['skipped_unanswerable']} unanswerable questions over "
        f"{(meta.get('index') or {}).get('total_documents')} files.",
        "",
        "## Retrieval (document level)",
        "",
        "| Method | MRR | Hit@1 | Hit@5 | Recall@5 | Precision@5 | nDCG@5 | Page Hit@5 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for method in report["methods"]:
        o = retrieval[method]["overall"]
        lines.append(
            f"| {method} | {fmt(o['mrr'])} | {fmt(o['hit@1'])} | {fmt(o['hit@5'])} | {fmt(o['recall@5'])} | "
            f"{fmt(o['precision@5'])} | {fmt(o['ndcg@5'])} | {fmt(o['page_hit@5'])} |"
        )
    best = report["methods"][-1]
    lines += [
        "",
        f"Hit@5 / MRR by category ({best}):",
        "",
        "| Category | n | Hit@5 | MRR |",
        "|---|---|---|---|",
    ]
    for name, o in retrieval[best]["by_category"].items():
        lines.append(f"| {name} | {o['n']} | {fmt(o['hit@5'])} | {fmt(o['mrr'])} |")
    lines += [
        "",
        "## Answers",
        "",
        "| Mode | Correct (all facts) | Fact recall | Citation hit | Unsupported numbers | False refusal | "
        "Correct refusal | Language match | Judge correct | Judge grounded | Median s |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for name, ans in report["answers"].items():
        o = ans["overall"]
        lines.append(
            f"| {name} | {fmt(o['correct'])} | {fmt(o['fact_recall'])} | {fmt(o['citation_hit'])} | "
            f"{fmt(o['answers_with_unsupported_numbers'])} | {fmt(o['false_refusal'])} | {fmt(o['correct_refusal'])} | "
            f"{fmt(o['language_match_all'])} | {fmt(o.get('judge_correct_norm'))} | "
            f"{fmt(o.get('judge_grounded_norm'))} | {fmt(ans['latency']['median_seconds_total'])} |"
        )
    lines += [
        "",
        "Rates are 0–1. Extractive answers quote passages, so their refusal and language numbers say little.",
        "Judge scores are normalized to 0–1 and only present when a judge model was given.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the nai-bench baseline")
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument("--api-key", default=None)
    parser.add_argument(
        "--index-corpus", metavar="SERVER_PATH", help="index this path as the nai-bench source first"
    )
    parser.add_argument("--methods", default="bm25,embedding,hybrid")
    parser.add_argument(
        "--no-llm", action="store_true", help="skip LLM answers even if the server has an LLM"
    )
    parser.add_argument("--judge-url")
    parser.add_argument("--judge-model")
    parser.add_argument("--label", default="baseline")
    parser.add_argument("--out-dir", type=Path, default=RESULTS_DIR)
    args = parser.parse_args()

    client = NaiClient(args.api_url, args.api_key)
    client.wait_until_up()
    if args.index_corpus:
        client.wait_until_indexed(client.ensure_source(args.index_corpus))
    items = load_items()
    methods = [m.strip() for m in args.methods.split(",") if m.strip()]
    meta = metadata(client, args.label)

    report: dict[str, Any] = {"meta": meta, "methods": methods}
    report["retrieval"] = eval_retrieval.evaluate(client, items, methods)
    judge_client = httpx.Client(base_url=args.judge_url.rstrip("/"), timeout=300) if args.judge_url else None
    report["answers"] = {
        "extractive": eval_answers.evaluate(client, items, use_llm=False),
    }
    if not args.no_llm and (meta.get("config") or {}).get("llm_enabled"):
        llm = eval_answers.evaluate(
            client, items, use_llm=True, judge_client=judge_client, judge_model=args.judge_model
        )
        report["answers"]["llm: " + ", ".join(llm["models"] or ["?"])] = llm

    args.out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{args.label}-{meta['date']}"
    json_path, md_path = args.out_dir / f"{stem}.json", args.out_dir / f"{stem}.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(markdown(report), encoding="utf-8")
    print(markdown(report))
    print(f"wrote {json_path} and {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
