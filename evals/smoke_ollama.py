"""
End-to-end smoke test: nAI + Ollama + nai-bench corpus
=====================================================

Checks that a running nAI (see ``infra/compose.bench.yaml``) with an Ollama model
indexes the nai-bench corpus and streams cited LLM answers back:

1. /health is ok and the LLM component is up
2. the nai-bench source is indexed (OCR included) and every chunk has an embedding
3. for a few questions (German, English, Swedish, one scanned invoice), /ask/stream
   sends citations first, then several token events, then done with method "llm";
   the citations include the gold file (a missing gold fact in the answer only warns:
   that is answer quality, which nai-bench measures)

Exit code 0 when every check passes. Usage:

    python evals/smoke_ollama.py [--api-url http://localhost:8000] [--corpus-path /shares/nai-bench]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from naibench import NaiClient, contains_fact, load_items, matches_gold

SMOKE_IDS = ("nb-001", "nb-002", "nb-013", "nb-018")
MIN_TOKEN_EVENTS = 3


def check(ok: bool, label: str, failures: list[str], hard: bool = True) -> None:
    """Print a check; failed hard checks fail the run, soft ones only warn."""
    print(f"  [{'ok' if ok else 'FAIL' if hard else 'warn'}] {label}")
    if not ok and hard:
        failures.append(label)


def main() -> int:
    parser = argparse.ArgumentParser(description="nAI + Ollama end-to-end smoke test")
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument("--api-key", default=None)
    parser.add_argument(
        "--corpus-path", default="/shares/nai-bench", help="corpus path as the server sees it"
    )
    args = parser.parse_args()

    client = NaiClient(args.api_url, args.api_key)
    failures: list[str] = []

    print("health")
    health = client.health()
    check(health.get("status") == "ok", "nAI /health ok", failures)
    check(bool(health.get("components", {}).get("llm")), "LLM component available", failures)

    print("indexing")
    state = client.wait_until_indexed(client.ensure_source(args.corpus_path))
    source, emb = state["source"], state["health"].get("embeddings") or {}
    check(source["document_count"] >= 20, f"corpus indexed ({source['document_count']} files)", failures)
    embedded = emb.get("pending") == 0 and (emb.get("vectors") or 0) > 0
    check(embedded, f"all chunks embedded ({emb.get('vectors')})", failures)

    items = {i.id: i for i in load_items()}
    for item_id in SMOKE_IDS:
        item = items[item_id]
        print(f"ask {item.id} ({item.language}): {item.question}")
        events = list(client.ask_stream(item.question, top_k=5, use_llm=True))
        kinds = [kind for kind, _ in events]
        citations: list[dict[str, Any]] = next((data for kind, data in events if kind == "citations"), [])
        done: dict[str, Any] = next((data for kind, data in events if kind == "done"), {})
        answer = "".join(data.get("text", "") for kind, data in events if kind == "token")
        check(kinds[:1] == ["citations"], "citations event comes first", failures)
        check(
            kinds.count("token") >= MIN_TOKEN_EVENTS,
            f"answer streamed ({kinds.count('token')} token events)",
            failures,
        )
        check("error" not in kinds, "no error event", failures)
        check(done.get("method") == "llm", f"answered by the LLM ({done.get('model')})", failures)
        cited = [c["doc_path"] for c in citations]
        check(any(matches_gold(p, g) for p in cited for g in item.gold_files), "gold file is cited", failures)
        # Answer quality is nai-bench's job; here a wrong fact only warns (small models do get it wrong).
        has_facts = all(contains_fact(answer, f) for f in item.gold_facts)
        check(has_facts, f"answer has {list(item.gold_facts)}", failures, hard=False)
        print(f"    answer: {answer.splitlines()[0][:160] if answer else '(empty)'}")

    print(f"\n{'PASSED' if not failures else 'FAILED'}: {len(failures)} failed check(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
