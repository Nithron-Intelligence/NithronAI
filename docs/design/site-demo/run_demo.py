"""Run the website's three demo questions against a running nAI and write run.json (see README.md).

    python run_demo.py --base http://127.0.0.1:8765 --commit <git commit of the nAI build> --image <image tag>

Expects nAI with authentication off, the demo corpus mounted read-only at /shares/demo and
NAI_SOURCES_ALLOWED_ROOTS=["/shares"]. Adds the corpus as a NAS folder, waits until it is scanned and fully
embedded, then asks each question once through /ask (LLM off: nAI's extractive answer) and records what nAI
returned, unchanged. Standard library only.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
QUESTIONS = [
    "When does the car insurance renew?",
    "What is the notice period for the internet contract?",
    "How much is invoice 2027-041 and when is it due?",
]
TOP_K = 3


def call(base: str, path: str, body: dict[str, Any] | None = None) -> Any:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(base + path, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.load(response)


def wait_until(check: Any, what: str, timeout: float = 900) -> Any:
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        value = check()
        if value:
            return value
        time.sleep(2)
    raise TimeoutError(f"gave up waiting for {what}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the website demo questions against nAI and write run.json"
    )
    parser.add_argument("--base", default="http://127.0.0.1:8765")
    parser.add_argument("--commit", required=True, help="git commit nAI was built from")
    parser.add_argument("--image", required=True, help="the image the run used")
    parser.add_argument("--out", type=Path, default=HERE / "run.json")
    parser.add_argument("--note", default="", help="added to the note (for example why the reranker is off)")
    args = parser.parse_args()

    health = wait_until(lambda: call(args.base, "/health"), "nAI to answer")
    call(args.base, "/sources", {"name": "Demo corpus", "path": "/shares/demo"})
    wait_until(
        lambda: all(s["last_scan_status"] == "ok" and not s["scanning"] for s in call(args.base, "/sources")),
        "the scan",
    )
    system = wait_until(
        lambda: (
            (s := call(args.base, "/system"))["features"]["embeddings"]["state"] == "ready"
            and s["features"]["embeddings"]["pending"] == 0
            and s
        ),
        "every passage to be embedded",
    )
    embeddings = system["features"]["embeddings"]
    documents = call(args.base, "/documents?page_size=200")["documents"]

    # One untimed query first, so the times below are for a running nAI, not for loading its models.
    call(args.base, "/search", {"query": "warm-up", "top_k": 1})
    runs = []
    for question in QUESTIONS:
        started = time.perf_counter()
        answer = call(args.base, "/ask", {"question": question, "top_k": TOP_K, "use_llm": False})
        seconds = time.perf_counter() - started
        retrieval = call(args.base, "/search", {"query": question, "top_k": TOP_K})["method"]
        runs.append(
            {
                "question": question,
                "retrieval": retrieval,
                "answer_method": answer["method"],
                "seconds": round(seconds, 3),
                "passages": [
                    {
                        "rank": rank,
                        "file": f"{c['source_name']}/{c['doc_path']}"
                        if c.get("source_name")
                        else c["doc_path"],
                        "page": c.get("page"),
                        "section": c.get("heading"),
                        "score": c["score"],
                        "text": c["text"],
                    }
                    for rank, c in enumerate(answer["citations"], start=1)
                ],
                "answer": answer["answer"],
            }
        )

    result = {
        "label": "Sample data: nAI 0.7.0, a demo corpus",
        "note": "A real run of nAI as built from the commit below, over a demo corpus of fictional documents written "
        "for the nAI website (see README.md). Draft, awaiting Thiago's approval."
        + (f" {args.note}" if args.note else ""),
        "nai_version": health["version"],
        "commit": args.commit,
        "image": args.image,
        "ran_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": {
            "embeddings": True,
            "embedding_model": embeddings["model"],
            "embedding_provider": embeddings["provider"],
            "reranker": bool(system["features"]["reranker"].get("active")),
            "llm": False,
            "answer": "extractive (nAI's own excerpts; no language model)",
            "top_k": TOP_K,
        },
        "corpus": sorted(f"{d['source_name']}/{d['path']}" for d in documents),
        "questions": runs,
    }
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", "utf-8")
    print(f"wrote {args.out}: {len(runs)} questions over {len(documents)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
