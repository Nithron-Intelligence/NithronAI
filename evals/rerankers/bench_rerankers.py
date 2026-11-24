"""
Benchmark candidate rerankers on nai-bench (offline, same candidates as nAI)
============================================================================

1. ``collect``: asks a running nAI (reranker off) for the top-30 hybrid candidates of every
   answerable nai-bench question and saves them (query, ranked chunks with file, page, text).
2. ``run``: for each candidate model, a fresh worker process re-scores those candidates exactly
   like nAI's reranker does (query vs chunk text), with a CPU thread limit to mimic a NAS, and
   records nai-bench retrieval metrics, latency per query and peak memory.

Backends: ``fastembed`` (what nAI runs), ``st`` (sentence-transformers CrossEncoder) and
``qwen3`` (Qwen3-Reranker's yes/no scoring). Needs training/requirements.txt (PyTorch,
sentence-transformers, fastembed) plus httpx; not part of nai-core.

    python evals/rerankers/bench_rerankers.py collect --output candidates.json
    python evals/rerankers/bench_rerankers.py run --candidates candidates.json --threads 2 \\
        --output evals/results/rerankers-2026-11-23.json

``--bench`` picks the questions file (default v0; v1 dev: ``evals/nai-bench/v1/questions-dev.jsonl``,
never a test split). ``--rerank-top N`` re-scores only the first N candidates and keeps the rest in
hybrid order, which is what nAI does (``NAI_RERANKER_CANDIDATES``, default 10).
"""

from __future__ import annotations

import argparse
import json
import resource
import statistics
import subprocess
import sys
import time
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

EVALS = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(EVALS), str(EVALS / "retrieval")]

import eval_retrieval  # noqa: E402
from naibench import (  # noqa: E402
    QUESTIONS_FILE,
    NaiClient,
    is_cross_lingual,
    load_items,
    load_manifest,
    manifest_for,
    mean,
)

CANDIDATES_PER_QUERY = 30
K_VALUES = (1, 3, 5, 10)

# name -> (backend, model id, license, params, note)
MODELS: dict[str, tuple[str, str, str, str, str]] = {
    "ms-marco-MiniLM-L-6 (current default)": (
        "fastembed",
        "Xenova/ms-marco-MiniLM-L-6-v2",
        "Apache-2.0",
        "22M",
        "English-only; trained on MS MARCO (non-commercial data terms)",
    ),
    "bge-reranker-v2-m3 int8": (
        "fastembed",
        "BAAI/bge-reranker-v2-m3-int8",
        "Apache-2.0",
        "568M",
        "multilingual (XLM-R); fastembed ships an int8 ONNX (0.57 GB)",
    ),
    "mmarco-mMiniLMv2-L12": (
        "st",
        "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1",
        "Apache-2.0",
        "118M",
        "15 languages; trained on mMARCO (translated MS MARCO, non-commercial data terms)",
    ),
    "Qwen3-Reranker-0.6B": (
        "qwen3",
        "Qwen/Qwen3-Reranker-0.6B",
        "Apache-2.0",
        "596M",
        "LLM-style yes/no scoring; 100+ languages",
    ),
    "Horizon multilingual-reranker-small int8": (
        "onnx",
        "Horizon-Labs/multilingual-reranker-small",
        "Apache-2.0",
        "141M",
        "mmBERT-small (ModernBERT); data: FineWeb/FineWeb-2, MIRACL train, WebFAQ, synthetic queries; "
        "labels distilled from Qwen3-Reranker-4B (round 9 audit)",
    ),
    "Horizon multilingual-reranker-base int8": (
        "onnx",
        "Horizon-Labs/multilingual-reranker-base",
        "Apache-2.0",
        "308M",
        "mmBERT-base (ModernBERT); same data and teacher as the small model (round 9 audit)",
    ),
}

# Candidates we did not run, with the reason (shown in the report).
SKIPPED: dict[str, str] = {
    "Alibaba-NLP/gte-multilingual-reranker-base (Apache-2.0, 306M)": (
        "needs trust_remote_code (runs Python code from the model repository) and has no fastembed/ONNX "
        "build; we don't run remote code, so it can't be a Loupe base as published"
    ),
    "mixedbread-ai/mxbai-rerank-base-v2 (Apache-2.0, 494M)": (
        "LLM-based (Qwen2 architecture) like Qwen3-Reranker but needs its own scoring library; not run"
    ),
    "jinaai/jina-reranker-v2-base-multilingual": "rejected: CC-BY-NC-4.0 (non-commercial)",
    "BAAI/bge-reranker-base": "rejected: Chinese and English only",
}

QWEN3_INSTRUCTION = "Given a question about the user's files, judge whether the passage answers it"


# ---------------------------------------------------------------------------
# collect
# ---------------------------------------------------------------------------


def collect(args: argparse.Namespace) -> int:
    client = NaiClient(args.api_url, args.api_key)
    client.wait_until_up()
    health = client.detailed_health()
    if str((health.get("config") or {}).get("reranker", "false")).lower() not in ("false", "0", "no", "off"):
        raise SystemExit("start nAI with NAI_RERANKER=false: candidates must be the un-reranked hybrid list")
    rows = []
    for item in (i for i in load_items(Path(args.bench)) if i.answerable):
        data = client.search(item.question, top_k=CANDIDATES_PER_QUERY, method="hybrid")
        rows.append({"id": item.id, "question": item.question, "results": data["results"]})
    Path(args.output).write_text(json.dumps(rows, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"saved candidates for {len(rows)} questions to {args.output}")
    return 0


# ---------------------------------------------------------------------------
# scorers (worker side)
# ---------------------------------------------------------------------------


def fastembed_scorer(model_id: str, threads: int) -> Callable[[str, list[str]], list[float]]:
    from fastembed.rerank.cross_encoder import TextCrossEncoder

    model = TextCrossEncoder(model_name=model_id, threads=threads)
    return lambda query, docs: [float(s) for s in model.rerank(query, docs)]


def st_scorer(model_id: str, threads: int) -> Callable[[str, list[str]], list[float]]:
    import torch
    from sentence_transformers import CrossEncoder

    torch.set_num_threads(threads)
    model = CrossEncoder(model_id, device="cpu", max_length=512)  # never trust_remote_code
    return lambda query, docs: [float(s) for s in model.predict([(query, d) for d in docs], batch_size=16)]


def qwen3_scorer(model_id: str, threads: int) -> Callable[[str, list[str]], list[float]]:
    """Qwen3-Reranker: P("yes") for 'does this document answer the query', per the model card."""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    torch.set_num_threads(threads)
    tokenizer = AutoTokenizer.from_pretrained(model_id, padding_side="left")
    model = AutoModelForCausalLM.from_pretrained(model_id, torch_dtype=torch.float32).eval()
    yes, no = tokenizer.convert_tokens_to_ids("yes"), tokenizer.convert_tokens_to_ids("no")
    prefix = (
        "<|im_start|>system\nJudge whether the Document meets the requirements based on the Query and the "
        'Instruct provided. Note that the answer can only be "yes" or "no".<|im_end|>\n<|im_start|>user\n'
    )
    suffix = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"

    def score(query: str, docs: list[str]) -> list[float]:
        texts = [
            f"{prefix}<Instruct>: {QWEN3_INSTRUCTION}\n<Query>: {query}\n<Document>: {d}{suffix}"
            for d in docs
        ]
        scores: list[float] = []
        with torch.no_grad():
            for start in range(0, len(texts), 8):
                batch = tokenizer(
                    texts[start : start + 8],
                    padding=True,
                    truncation=True,
                    max_length=1024,
                    return_tensors="pt",
                )
                logits = model(**batch).logits[:, -1, :]
                pair = torch.stack([logits[:, no], logits[:, yes]], dim=1)
                scores += torch.nn.functional.softmax(pair, dim=1)[:, 1].tolist()
        return scores

    return score


def onnx_scorer(model_id: str, threads: int) -> Callable[[str, list[str]], list[float]]:
    """A cross-encoder's own int8 ONNX file (onnx/model_quantized.onnx) on onnxruntime, like fastembed."""
    from sentence_transformers import CrossEncoder

    model = CrossEncoder(
        model_id,
        device="cpu",
        max_length=512,
        backend="onnx",
        model_kwargs={
            "file_name": "onnx/model_quantized.onnx",
            "provider": "CPUExecutionProvider",
            "session_options": _ort_options(threads),
        },
    )  # never trust_remote_code
    return lambda query, docs: [float(s) for s in model.predict([(query, d) for d in docs], batch_size=16)]


def _ort_options(threads: int) -> Any:
    import onnxruntime

    options = onnxruntime.SessionOptions()
    options.intra_op_num_threads = threads
    options.inter_op_num_threads = 1
    return options


SCORERS = {"fastembed": fastembed_scorer, "st": st_scorer, "qwen3": qwen3_scorer, "onnx": onnx_scorer}


def split_head(
    results: list[dict[str, Any]], top: int | None
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """The candidates to re-score and the rest (kept in hybrid order); ``None`` re-scores all."""
    if top is None:
        return results, []
    return results[:top], results[top:]


def worker(args: argparse.Namespace) -> int:
    """Score all candidates with one model; print a JSON report on stdout."""
    backend, model_id = MODELS[args.model][0], MODELS[args.model][1]
    candidates = json.loads(Path(args.candidates).read_text(encoding="utf-8"))
    started = time.monotonic()
    scorer = SCORERS[backend](model_id, args.threads)
    load_seconds = time.monotonic() - started
    scorer("warm-up", ["warm-up passage"])
    reranked, latencies = [], []
    for row in candidates:
        head, tail = split_head(row["results"], args.rerank_top)
        docs = [r["text"] for r in head]
        t = time.monotonic()
        scores = scorer(row["question"], docs) if docs else []
        latencies.append(time.monotonic() - t)
        order = sorted(range(len(docs)), key=lambda i: scores[i], reverse=True)
        reranked.append({"id": row["id"], "results": [head[i] for i in order] + tail})
    peak_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    print(
        json.dumps(
            {
                "reranked": reranked,
                "latencies": latencies,
                "load_seconds": load_seconds,
                "peak_rss_mb": peak_mb,
            }
        )
    )
    return 0


# ---------------------------------------------------------------------------
# run (parent side)
# ---------------------------------------------------------------------------


def score_ranking(per_question: list[dict[str, Any]], bench: Path = QUESTIONS_FILE) -> dict[str, Any]:
    items = {i.id: i for i in load_items(bench)}
    manifest = load_manifest(manifest_for(bench))
    rows = []
    for entry in per_question:
        item = items[entry["id"]]
        row = eval_retrieval.score_item(item, entry["results"], K_VALUES)
        row["cross_lingual"] = "yes" if is_cross_lingual(item, manifest) else "no"
        rows.append(row)
    return {
        "overall": eval_retrieval.aggregate(rows, K_VALUES),
        "by_category": eval_retrieval.breakdown(rows, "category", K_VALUES),
        "by_language": eval_retrieval.breakdown(rows, "language", K_VALUES),
        "by_cross_lingual": eval_retrieval.breakdown(rows, "cross_lingual", K_VALUES),
    }


def run(args: argparse.Namespace) -> int:
    candidates = json.loads(Path(args.candidates).read_text(encoding="utf-8"))
    bench = Path(args.bench)
    report: dict[str, Any] = {
        "date": date.today().isoformat(),
        "bench": str(bench),
        "threads": args.threads,
        "candidates_per_query": CANDIDATES_PER_QUERY,
        "rerank_top": args.rerank_top,
        "questions": len(candidates),
        "notes": args.notes,
        "models": {"none (hybrid RRF order)": {"metrics": score_ranking(candidates, bench)}},
        "skipped": SKIPPED,
    }
    names = [n.strip() for n in args.models.split(",")] if args.models else list(MODELS)
    for name in names:
        print(f"== {name}", file=sys.stderr)
        cmd = [sys.executable, __file__, "worker", "--model", name, "--candidates", args.candidates]
        cmd += ["--rerank-top", str(args.rerank_top)] if args.rerank_top else []
        done = subprocess.run([*cmd, "--threads", str(args.threads)], capture_output=True, text=True)
        if done.returncode != 0:
            report["models"][name] = {"error": done.stderr.strip().splitlines()[-1:]}
            print(done.stderr[-2000:], file=sys.stderr)
            continue
        out = json.loads(done.stdout.strip().splitlines()[-1])
        lat = sorted(out["latencies"])
        backend, model_id, license_id, params, note = MODELS[name]
        report["models"][name] = {
            "model": model_id,
            "backend": backend,
            "license": license_id,
            "params": params,
            "note": note,
            "metrics": score_ranking(out["reranked"], bench),
            "latency_seconds": {
                "median": round(statistics.median(lat), 3),
                "p90": round(lat[int(len(lat) * 0.9)], 3),
                "mean": round(mean(lat), 3),
            },
            "load_seconds": round(out["load_seconds"], 1),
            "peak_rss_mb": round(out["peak_rss_mb"]),
        }
    Path(args.output).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    Path(args.output).with_suffix(".md").write_text(markdown(report), encoding="utf-8")
    print(markdown(report))
    return 0


def fmt(value: Any) -> str:
    return "–" if value is None else f"{value:.3f}" if isinstance(value, float) else str(value)


def markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# nai-bench reranker comparison – {report['date']}",
        "",
        *([report["notes"], ""] if report.get("notes") else []),
        f"Each model re-scores the same top-{report.get('rerank_top') or report['candidates_per_query']} "
        f"hybrid candidates from nAI for {report['questions']} answerable questions of "
        f"`{report.get('bench', 'evals/nai-bench/questions.jsonl')}`, on {report['threads']} CPU threads. "
        f"Document-level metrics; latency is per question "
        f"({report.get('rerank_top') or report['candidates_per_query']} passages).",
        "",
        "| Reranker | License | Params | MRR | Hit@1 | Hit@5 | Page Hit@5 | MRR cross-lingual | "
        "Hit@5 cross-lingual | Median s | p90 s | Peak RAM MB |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for name, entry in report["models"].items():
        if "error" in entry:
            lines.append(f"| {name} | | | error: {' '.join(entry['error'])} | | | | | | | | |")
            continue
        o = entry["metrics"]["overall"]
        xl = entry["metrics"]["by_cross_lingual"].get("yes", {})
        lat = entry.get("latency_seconds", {})
        lines.append(
            f"| {name} | {entry.get('license', '–')} | {entry.get('params', '–')} | {fmt(o['mrr'])} | "
            f"{fmt(o['hit@1'])} | {fmt(o['hit@5'])} | {fmt(o['page_hit@5'])} | {fmt(xl.get('mrr'))} | "
            f"{fmt(xl.get('hit@5'))} | "
            f"{fmt(lat.get('median'))} | {fmt(lat.get('p90'))} | {fmt(entry.get('peak_rss_mb'))} |"
        )
    for name, reason in report.get("skipped", {}).items():
        lines.append(f"| {name} | not run: {reason} | | | | | | | | | | |")
    lines += ["", "Notes per model:", ""]
    lines += [f"- **{n}**: {e['note']}" for n, e in report["models"].items() if e.get("note")]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark rerankers on nai-bench")
    sub = parser.add_subparsers(dest="command", required=True)
    c = sub.add_parser("collect")
    c.add_argument("--api-url", default="http://localhost:8000")
    c.add_argument("--api-key")
    c.add_argument("--output", required=True)
    c.add_argument("--bench", default=str(QUESTIONS_FILE), help="questions file (never a test split)")
    r = sub.add_parser("run")
    r.add_argument("--candidates", required=True)
    r.add_argument("--threads", type=int, default=2)
    r.add_argument("--models", help="comma-separated names from MODELS (default: all)")
    r.add_argument("--notes")
    r.add_argument("--bench", default=str(QUESTIONS_FILE), help="questions file (never a test split)")
    r.add_argument("--rerank-top", type=int, help="re-score only the first N candidates (nAI: 10)")
    r.add_argument("--output", required=True)
    w = sub.add_parser("worker")
    w.add_argument("--model", required=True)
    w.add_argument("--candidates", required=True)
    w.add_argument("--threads", type=int, default=2)
    w.add_argument("--rerank-top", type=int)
    args = parser.parse_args()
    return {"collect": collect, "run": run, "worker": worker}[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
