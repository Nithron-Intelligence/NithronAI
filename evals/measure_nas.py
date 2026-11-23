"""
Measure nAI on NAS-like hardware: indexing time, query latency and memory
==========================================================================

Run against nAI + Ollama started with infra/compose.bench.nas-sim.yaml (CPU only, limited
cores and RAM) to get **simulated NAS** numbers, or against nAI on a real NAS with
``--environment real-nas``. Results are always labelled with the environment.

Measures, on the nai-bench corpus:
- indexing from scratch (scan + OCR + embeddings; the model download is excluded)
- /search latency (hybrid) over all answerable questions (median, p95)
- extractive answers (/ask/stream, no LLM): time to first token and total
- LLM answers (/ask/stream with the configured Ollama model): time to first token, total, tokens/s
- memory and CPU of the containers (docker stats, polled continuously): peak and after indexing

    python evals/measure_nas.py --label simulated-nas \\
        --profile "nai-core 2 CPUs / 4 GB, Ollama 2 CPUs / 4 GB, Ryzen 9 7950X host"
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import threading
import time
from datetime import date
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from naibench import NaiClient, load_items, review_summary

RESULTS = Path(__file__).resolve().parent / "results"
UNITS = {"B": 1, "KiB": 1024, "MiB": 1024**2, "GiB": 1024**3, "kB": 1000, "MB": 1000**2, "GB": 1000**3}


def parse_mem(text: str) -> float:
    """'512.3MiB' or '1.2GiB' -> MiB."""
    for unit in sorted(UNITS, key=len, reverse=True):
        if text.endswith(unit):
            return float(text[: -len(unit)]) * UNITS[unit] / 1024**2
    return 0.0


class StatsSampler(threading.Thread):
    """Samples `docker stats` for some containers; keeps per-phase peaks."""

    def __init__(self, containers: list[str], interval: float = 0.5) -> None:
        super().__init__(daemon=True)
        self.containers = containers
        self.interval = interval
        self.phase = "startup"
        self.samples: list[dict[str, Any]] = []
        self._halt = threading.Event()
        self.errors: list[str] = []

    def run(self) -> None:
        fmt = "{{.Name}}\t{{.MemUsage}}\t{{.CPUPerc}}"
        while not self._halt.is_set():
            try:
                out = subprocess.run(
                    ["docker", "stats", "--no-stream", "--format", fmt, *self.containers],
                    capture_output=True,
                    text=True,
                    timeout=30,
                ).stdout
            except (OSError, subprocess.TimeoutExpired) as e:
                self.errors.append(str(e))
                self._halt.wait(self.interval)
                continue
            for line in out.strip().splitlines():
                try:
                    name, mem, cpu = line.split("\t")
                    used = parse_mem(mem.split("/")[0].strip())
                    cpu_percent = float(cpu.rstrip("%"))
                except ValueError:  # container gone, '--' values, unexpected format
                    self.errors.append(f"unparsed docker stats line: {line!r}")
                    continue
                self.samples.append({"phase": self.phase, "name": name, "mem_mib": used, "cpu": cpu_percent})
            self._halt.wait(self.interval)

    def stop(self) -> None:
        self._halt.set()

    def summary(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for name in self.containers:
            rows = [s for s in self.samples if s["name"] == name]
            if not rows:
                result[name] = {"no-samples": {"peak_mem_mib": 0, "mean_cpu_percent": 0}}
                continue
            phases = sorted({s["phase"] for s in rows})
            result[name] = {
                phase: {
                    "peak_mem_mib": round(max(s["mem_mib"] for s in rows if s["phase"] == phase)),
                    "mean_cpu_percent": round(statistics.mean(s["cpu"] for s in rows if s["phase"] == phase)),
                }
                for phase in phases
            }
        return result


def pct(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, int(len(ordered) * q))], 3)


def timed_stream(client: NaiClient, question: str, use_llm: bool) -> dict[str, Any]:
    start = time.monotonic()
    first = None
    tokens = 0
    model = None
    for event, data in client.ask_stream(question, top_k=5, use_llm=use_llm):
        if event == "token":
            tokens += 1
            first = first if first is not None else time.monotonic() - start
        elif event == "done":
            model = data.get("model")
    total = time.monotonic() - start
    generating = total - (first or 0)
    return {
        "ttft": round(first or total, 3),
        "total": round(total, 3),
        "token_events_per_s": round(tokens / generating, 1) if generating > 0 else 0.0,
        "model": model,
    }


def wait_for_embedding_model(client: NaiClient, timeout: float = 900) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        emb = client.detailed_health().get("embeddings") or {}
        if emb.get("state") in ("ready", "disabled", None):  # disabled: keyword-only mode
            return
        if emb.get("state") == "error":
            raise RuntimeError(f"embedding model failed: {emb.get('error')}")
        time.sleep(2)
    raise TimeoutError("embedding model did not load")


def measure(args: argparse.Namespace) -> dict[str, Any]:
    client = NaiClient(args.api_url, args.api_key, timeout=600)
    client.wait_until_up()
    sampler = StatsSampler(args.containers.split(","))
    sampler.start()

    sampler.phase = "1-model-load"
    wait_for_embedding_model(client)  # downloads/loads the model; not part of the indexing time

    sampler.phase = "2-indexing"
    started = time.monotonic()
    source_id = client.ensure_source(args.corpus_path)
    state = client.wait_until_indexed(source_id, timeout=3600)
    index_seconds = time.monotonic() - started

    sampler.phase = "3-idle-after-indexing"
    time.sleep(5)

    items = [i for i in load_items() if i.answerable]
    sampler.phase = "4-search"
    for item in items[:5]:  # warm-up
        client.search(item.question, top_k=10, method="hybrid")
    search = []
    methods: set[str] = set()  # "bm25" when nAI runs keyword-only (NAI_EMBEDDINGS=auto on a small box)
    for item in items:
        t = time.monotonic()
        methods.add(client.search(item.question, top_k=10, method="hybrid").get("method", "?"))
        search.append(time.monotonic() - t)

    sampler.phase = "5-extractive-answers"
    extractive = [timed_stream(client, i.question, use_llm=False) for i in items]

    llm: list[dict[str, Any]] = []
    health = client.detailed_health()
    if args.llm_questions and (health.get("config") or {}).get("llm_enabled"):
        sampler.phase = "6-llm-answers"
        timed_stream(client, items[0].question, use_llm=True)  # loads the model into Ollama
        llm = [timed_stream(client, i.question, use_llm=True) for i in items[1 : 1 + args.llm_questions]]

    sampler.stop()
    sampler.join(timeout=5)
    source = state["source"]
    return {
        "label": args.label,
        "environment": args.environment,
        "profile": args.profile,
        "date": date.today().isoformat(),
        "nai_version": health.get("version"),
        "config": health.get("config"),
        "embeddings_model": (health.get("embeddings") or {}).get("model"),
        "embeddings_mode": (health.get("embeddings") or {}).get("mode"),
        "embeddings_reason": (health.get("embeddings") or {}).get("reason"),
        "search_methods": sorted(methods),
        "review": review_summary(),
        "indexing": {
            "files": source.get("document_count"),
            "chunks": (state["health"].get("index") or {}).get("total_chunks"),
            "seconds": round(index_seconds, 1),
        },
        "search_seconds": {"n": len(search), "median": pct(search, 0.5), "p95": pct(search, 0.95)},
        "extractive_answer_seconds": {
            "n": len(extractive),
            "median_total": pct([e["total"] for e in extractive], 0.5),
            "p95_total": pct([e["total"] for e in extractive], 0.95),
        },
        "llm_answer": (
            {
                "n": len(llm),
                "model": llm[0].get("model"),
                "median_ttft": pct([e["ttft"] for e in llm], 0.5),
                "median_total": pct([e["total"] for e in llm], 0.5),
                "p95_total": pct([e["total"] for e in llm], 0.95),
                "median_token_events_per_s": pct([e["token_events_per_s"] for e in llm], 0.5),
            }
            if llm
            else None
        ),
        "containers": sampler.summary(),
        "sampler_errors": sampler.errors[:20],
    }


def _embeddings_text(r: dict[str, Any]) -> str:
    """Embedding model, or the keyword-only reason (results from before 0.7.0 have no mode)."""
    if r.get("embeddings_mode") in ("off", "auto-off"):
        return f"embeddings off (keyword-only; {r.get('embeddings_reason')})"
    return f"embeddings `{r['embeddings_model']}`"


def markdown(r: dict[str, Any]) -> str:
    env = "SIMULATED NAS" if r["environment"] == "simulated-nas" else "REAL NAS"
    lines = [
        f"# nAI on NAS-class hardware ({env}) – {r['date']}",
        "",
        f"**Environment: {env}.** {r['profile']}",
        "",
        "Simulated means a desktop CPU limited with Docker (`--cpus`, `--memory`); one desktop core is "
        "considerably faster than a typical NAS core, so real NAS numbers will be slower."
        if r["environment"] == "simulated-nas"
        else "Measured on real NAS hardware.",
        "",
        f"nAI {r['nai_version']}, {_embeddings_text(r)}, reranker `{(r['config'] or {}).get('reranker')}`, "
        f"OCR on. nai-bench corpus: {r['indexing']['files']} files, {r['indexing']['chunks']} chunks.",
        "",
        "| Measurement | Value |",
        "|---|---|",
        f"| Indexing from scratch (scan + OCR + embeddings) | {r['indexing']['seconds']} s |",
        f"| Search ({'/'.join(r.get('search_methods') or ['hybrid'])}), median / p95 | {r['search_seconds']['median']} s / {r['search_seconds']['p95']} s |",
        f"| Extractive answer, median / p95 | {r['extractive_answer_seconds']['median_total']} s / "
        f"{r['extractive_answer_seconds']['p95_total']} s |",
    ]
    if r.get("llm_answer"):
        llm = r["llm_answer"]
        lines += [
            f"| LLM answer ({llm['n']} questions, `{llm['model']}`): time to first token, median | {llm['median_ttft']} s |",
            f"| LLM answer: total, median / p95 | {llm['median_total']} s / {llm['p95_total']} s |",
            f"| LLM streaming speed, median | {llm['median_token_events_per_s']} token events/s |",
        ]
    lines += ["", "Memory and CPU per phase (docker stats, polled continuously, about every 1–2 s):", ""]
    lines += ["| Container | Phase | Peak memory (MiB) | Mean CPU % |", "|---|---|---|---|"]
    for name, phases in r["containers"].items():
        for phase, v in phases.items():
            lines.append(f"| {name} | {phase} | {v['peak_mem_mib']} | {v['mean_cpu_percent']} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Measure nAI latency and memory on NAS-like hardware")
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument("--api-key")
    parser.add_argument("--corpus-path", default="/shares/nai-bench")
    parser.add_argument("--containers", default="nai-bench-nai-core-1,nai-bench-ollama-1")
    parser.add_argument("--environment", choices=("simulated-nas", "real-nas"), default="simulated-nas")
    parser.add_argument(
        "--profile", required=True, help="hardware/limits, e.g. '2 CPUs / 4 GB on a Ryzen 9 7950X'"
    )
    parser.add_argument("--llm-questions", type=int, default=10)
    parser.add_argument("--label", default="simulated-nas")
    args = parser.parse_args()

    result = measure(args)
    stem = f"{args.label}-{result['date']}"
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / f"{stem}.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    (RESULTS / f"{stem}.md").write_text(markdown(result), encoding="utf-8")
    print(markdown(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
