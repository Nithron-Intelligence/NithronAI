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
NAI_CORE = EVALS.parent / "apps" / "nai-core"
sys.path[:0] = [str(EVALS), str(EVALS / "retrieval"), str(EVALS / "answers"), str(NAI_CORE)]

import eval_answers  # noqa: E402
import eval_retrieval  # noqa: E402
from naibench import (  # noqa: E402
    FINAL_RUN_HELP,
    QUESTIONS_FILE,
    NaiClient,
    cli_load_items,
    load_manifest,
    manifest_for,
    review_summary,
    split_file_kind,
)

from app.nithron_models import FAMILIES, parse_model_id  # noqa: E402

RESULTS_DIR = EVALS / "results"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_commit() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=EVALS, capture_output=True, text=True
        )
        # Only tracked changes to what produces the numbers make a run "+dirty".
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no", "--", "apps", "evals", "infra"],
            cwd=EVALS.parent,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    return out.stdout.strip() + ("+dirty" if dirty.stdout.strip() else "") if out.returncode == 0 else None


def nithron_models_in(model_ids: dict[str, str | None]) -> list[dict[str, str]]:
    """Nithron models (docs/lab/MODEL_NAMING.md) among the models a run used, with display names."""
    found = []
    for role, model_id in model_ids.items():
        ref = parse_model_id(model_id)
        if ref:
            family = FAMILIES[ref.family]
            found.append(
                {"role": role, "id": ref.hf_id, "display_name": ref.display_name, "family": family.name}
            )
    return found


def metadata(client: NaiClient, label: str, bench: Path = QUESTIONS_FILE) -> dict[str, Any]:
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
            "questions_file": bench.name,
            "split": split_file_kind(bench),
            "questions_sha256": sha256_file(bench),
            "corpus_manifest_sha256": sha256_file(manifest_for(bench)),
        },
        "client_host": {"platform": platform.platform(), "python": platform.python_version()},
        "nithron_models": nithron_models_in(
            {
                "embeddings": (health.get("embeddings") or {}).get("model"),
                "reranker": (health.get("config") or {}).get("reranker_model"),
            }
        ),
    }


def fmt(value: Any) -> str:
    return "–" if value is None else f"{value:.3f}" if isinstance(value, float) else str(value)


def review_line(review: dict[str, Any]) -> str:
    """Every report states how many items a person has reviewed (V1_PLAN.md)."""
    if not review:
        return "**Review status unknown.**"
    counts = (
        f"{review.get('reviewed', 0)} of {review.get('total', 0)} items human-reviewed "
        f"({review.get('rejected', 0)} rejected); evaluated: {review.get('evaluated')} ({review.get('scope')})."
    )
    if review.get("publishable"):
        return f"**Review:** {counts}"
    return f"**PROVISIONAL — includes unreviewed items.** Review: {counts} Published numbers use `--reviewed-only`."


def language_lines(method_report: dict[str, Any]) -> list[str]:
    """Hit@5 / MRR per question language."""
    lines = ["| Language | n | Hit@5 | MRR |", "|---|---|---|---|"]
    for name, o in sorted(method_report.get("by_language", {}).items()):
        lines.append(f"| {name} | {o['n']} | {fmt(o['hit@5'])} | {fmt(o['mrr'])} |")
    return lines


def empty_result_lines(retrieval: dict[str, Any], methods: list[str]) -> list[str]:
    """Answerable questions for which a method returned no file at all, by the cross-lingual flag.

    Embedding search drops hits below NAI_EMBEDDINGS_MIN_SCORE (cosine 0.3 by default), so an empty
    result there means no chunk came close enough, which hits cross-lingual questions first.
    """
    lines = [
        "| Method | same language: no result | question language ≠ source language: no result |",
        "|---|---|---|",
    ]
    for method in methods:
        rows = retrieval[method].get("per_question", [])
        cells = []
        for flag in ("no", "yes"):
            group = [r for r in rows if r.get("cross_lingual") == flag]
            empty = sum(1 for r in group if not r.get("retrieved"))
            cells.append(f"{empty} of {len(group)}")
        lines.append(f"| {method} | {cells[0]} | {cells[1]} |")
    return lines


def markdown(report: dict[str, Any]) -> str:
    meta = report["meta"]
    retrieval = report["retrieval"]
    cfg = meta.get("config") or {}
    lines = [
        f"# nai-bench {meta['label']} – {meta['date']}",
        "",
        *([meta["notes"], ""] if meta.get("notes") else []),
        review_line(meta.get("review") or {}),
        "",
        f"nAI {meta['nai_version']} at commit `{meta['git_commit']}`; embeddings "
        f"`{meta['embeddings']['model']}` ({meta['embeddings']['provider']}); reranker `{cfg.get('reranker')}`; "
        f"{retrieval['questions']} answerable + {retrieval['skipped_unanswerable']} unanswerable questions over "
        f"{(meta.get('index') or {}).get('total_documents')} files.",
        "",
        *(
            [
                "Nithron models: "
                + ", ".join(f"{m['display_name']} ({m['role']})" for m in meta["nithron_models"]),
                "",
            ]
            if meta.get("nithron_models")
            else []
        ),
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
    for flag, o in retrieval[best].get("by_cross_lingual", {}).items():
        label = "question language ≠ source language" if flag == "yes" else "same language"
        lines.append(f"| *{label}* | {o['n']} | {fmt(o['hit@5'])} | {fmt(o['mrr'])} |")
    lines += ["", f"Hit@5 / MRR by question language ({best}):", "", *language_lines(retrieval[best])]
    lines += [
        "",
        "Answerable questions with no result at all (embedding search drops hits below "
        "`NAI_EMBEDDINGS_MIN_SCORE`, cosine 0.3 by default):",
        "",
        *empty_result_lines(retrieval, report["methods"]),
    ]
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
        "Correct refusal is over the unanswerable questions; the other answer columns are over the answerable ones,",
        "except Language match (all questions).",
        "Judge scores are normalized to 0–1 and only present when a judge model was given.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
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
    parser.add_argument(
        "--reviewed-only",
        action="store_true",
        help="evaluate only human-reviewed items (required for published numbers)",
    )
    parser.add_argument("--notes", help="free text for the summary, e.g. the hardware the LLM ran on")
    parser.add_argument("--out-dir", type=Path, default=RESULTS_DIR)
    parser.add_argument("--bench", type=Path, default=QUESTIONS_FILE, help="questions file (v0 by default)")
    parser.add_argument("--final-run", action="store_true", help=FINAL_RUN_HELP)
    args = parser.parse_args(argv)

    # Load (and check the split guard) before touching the server.
    items = cli_load_items(args.bench, args.reviewed_only, args.final_run, args.label)
    if not items:
        raise SystemExit(
            "no items to evaluate (with --reviewed-only, review some first: evals/nai-bench/review.py)"
        )
    client = NaiClient(args.api_url, args.api_key)
    client.wait_until_up()
    if args.index_corpus:
        client.wait_until_indexed(client.ensure_source(args.index_corpus))
    methods = [m.strip() for m in args.methods.split(",") if m.strip()]
    meta = metadata(client, args.label, args.bench)
    meta["notes"] = args.notes
    counts = review_summary(args.bench, allow_test=args.final_run)
    meta["review"] = {
        **counts,
        "scope": "reviewed items only" if args.reviewed_only else "all non-rejected items",
        "evaluated": len(items),
        "publishable": args.reviewed_only,
    }

    report: dict[str, Any] = {"meta": meta, "methods": methods}
    manifest = load_manifest(manifest_for(args.bench))
    report["retrieval"] = eval_retrieval.evaluate(client, items, methods, manifest=manifest)
    judge_client = httpx.Client(base_url=args.judge_url.rstrip("/"), timeout=300) if args.judge_url else None
    report["answers"] = {
        "extractive": eval_answers.evaluate(client, items, use_llm=False, manifest=manifest),
    }
    if not args.no_llm and (meta.get("config") or {}).get("llm_enabled"):
        llm = eval_answers.evaluate(
            client,
            items,
            use_llm=True,
            judge_client=judge_client,
            judge_model=args.judge_model,
            manifest=manifest,
        )
        report["answers"]["llm: " + ", ".join(llm["models"] or ["?"])] = llm
        known = {m["id"] for m in meta["nithron_models"]}
        found = nithron_models_in({f"answers ({m})": m for m in llm["models"]})
        meta["nithron_models"] += [m for m in found if m["id"] not in known]

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
