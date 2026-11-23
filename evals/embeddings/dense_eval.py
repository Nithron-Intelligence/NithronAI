"""
Offline embedding-only retrieval eval on the nai-bench v1 **dev** split (for checkpoints that aren't exported
to ONNX yet, e.g. the Vane 1 pilot). Three steps:

    # in the nai-core image (it has Tesseract for the scans): chunk the v1 corpus like nAI, write the dev questions
    docker run --rm --user "$(id -u):$(id -g)" -v "$PWD:/repo" -w /repo --entrypoint python nai-core:0.6.0-local \
        evals/embeddings/dense_eval.py export --out training/runs/vane1-pilot/eval
    # ROCm trainer container (PyTorch + sentence-transformers): rank files per question with a model
    python3 evals/embeddings/dense_eval.py rank --data training/runs/vane1-pilot/eval --model <hf id or path> \
        --name base
    # host: metrics overall, per category, per language and cross-language vs same-language
    apps/nai-core/.venv/bin/python evals/embeddings/dense_eval.py score --data training/runs/vane1-pilot/eval \
        --names base,pilot

Only the dev split is loaded (``naibench.load_items`` refuses the test split). Ranking is by cosine similarity
of nAI's chunk input ("<context header>\\n<text>"), best chunk per file, no 0.3 cutoff, no BM25; it measures
the embedding model alone, so compare it with nAI's embedding-only numbers, not with hybrid.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

EVALS = Path(__file__).resolve().parents[1]
REPO = EVALS.parent


def export(out: Path) -> None:
    nai_core = (
        Path("/app") if Path("/app/app").is_dir() else REPO / "apps" / "nai-core"
    )  # inside the nai-core image
    sys.path[:0] = [str(EVALS), str(nai_core)]
    import naibench as nb

    from app.utils.extractors import extract
    from app.utils.text import chunk_sections

    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for entry in nb.load_manifest(nb.V1_MANIFEST_FILE):
        path = nb.V1_CORPUS_DIR / entry["file"]
        extracted = extract(str(path), ocr=True, ocr_languages="eng+deu")
        title = extracted.metadata.get("title")
        for chunk in chunk_sections(extracted.sections, entry["file"], title=title, max_chars=1000):
            text = f"{chunk.context}\n{chunk.text}" if chunk.context else chunk.text
            rows.append({"file": entry["file"], "text": text})
    (out / "passages.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), "utf-8"
    )
    items = [i for i in nb.load_items(nb.V1_DEV_FILE) if i.answerable]
    (out / "questions.jsonl").write_text(
        "".join(json.dumps({"id": i.id, "question": i.question}, ensure_ascii=False) + "\n" for i in items),
        "utf-8",
    )
    print(
        f"{len(rows)} passages from {len({r['file'] for r in rows})} files; {len(items)} answerable dev questions"
    )


def rank(data: Path, model_name: str, name: str, top: int = 20) -> None:
    import numpy as np
    from sentence_transformers import SentenceTransformer

    passages = [json.loads(line) for line in (data / "passages.jsonl").read_text("utf-8").splitlines()]
    questions = [json.loads(line) for line in (data / "questions.jsonl").read_text("utf-8").splitlines()]
    model = SentenceTransformer(model_name)
    model.max_seq_length = 256
    p = model.encode(
        [r["text"] for r in passages], batch_size=128, normalize_embeddings=True, show_progress_bar=False
    )
    q = model.encode([r["question"] for r in questions], batch_size=128, normalize_embeddings=True)
    scores = q @ p.T
    out: dict[str, list[str]] = {}
    for qi, row in enumerate(questions):
        files: list[str] = []
        for pi in np.argsort(-scores[qi]):
            f = passages[pi]["file"]
            if f not in files:
                files.append(f)
            if len(files) == top:
                break
        out[row["id"]] = files
    (data / f"rankings-{name}.json").write_text(
        json.dumps({"model": model_name, "rankings": out}, indent=1), "utf-8"
    )
    print(f"ranked {len(out)} questions with {model_name} over {len(passages)} passages")


def score(data: Path, names: list[str]) -> str:
    sys.path.insert(0, str(EVALS))
    import naibench as nb

    manifest = nb.load_manifest(nb.V1_MANIFEST_FILE)
    items = {i.id: i for i in nb.load_items(nb.V1_DEV_FILE) if i.answerable}
    lines = ["| Model | Group | n | MRR | Hit@1 | Hit@5 |", "|---|---|---|---|---|---|"]
    result: dict[str, Any] = {}
    for name in names:
        run = json.loads((data / f"rankings-{name}.json").read_text("utf-8"))
        rows = []
        for qid, ranked in run["rankings"].items():
            item = items[qid]
            rows.append(
                {
                    "category": item.category,
                    "language": item.language,
                    "cross": "cross-language" if nb.is_cross_lingual(item, manifest) else "same language",
                    "mrr": nb.reciprocal_rank(ranked, item.gold_files),
                    "hit1": nb.hit_at_k(ranked, item.gold_files, 1),
                    "hit5": nb.hit_at_k(ranked, item.gold_files, 5),
                }
            )
        groups: dict[str, list[dict[str, Any]]] = {"overall": rows}
        for key in ("cross", "category", "language"):
            for row in rows:
                groups.setdefault(f"{key}: {row[key]}", []).append(row)
        result[name] = {}
        for group, members in groups.items():
            m = {k: nb.mean([r[k] for r in members]) for k in ("mrr", "hit1", "hit5")}
            result[name][group] = {"n": len(members), **m}
            lines.append(
                f"| {name} | {group} | {len(members)} | {m['mrr']:.3f} | {m['hit1']:.3f} | {m['hit5']:.3f} |"
            )
    (data / "scores.json").write_text(json.dumps(result, indent=1), "utf-8")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export")
    e.add_argument("--out", type=Path, required=True)
    r = sub.add_parser("rank")
    r.add_argument("--data", type=Path, required=True)
    r.add_argument("--model", required=True)
    r.add_argument("--name", required=True)
    s = sub.add_parser("score")
    s.add_argument("--data", type=Path, required=True)
    s.add_argument("--names", required=True)
    args = parser.parse_args()
    if args.cmd == "export":
        export(args.out)
    elif args.cmd == "rank":
        rank(args.data, args.model, args.name)
    else:
        print(score(args.data, [n.strip() for n in args.names.split(",")]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
