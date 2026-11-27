"""
Fine-tune nAI's multilingual embedding model on synthetic query-passage pairs.

Pipeline (see docs/lab/stage1-embedding-finetune.md):
  1. load pairs.jsonl (from generate_pairs.py, checked with check_overlap.py)
  2. split by passage into train / held-out eval (eval passages are never trained on)
  3. mine hard negatives for the train pairs with the base model
  4. train with MultipleNegativesRankingLoss (or the cached variant for big batches)
  5. evaluate on the held-out pairs (IR metrics) before and after training
  6. export ONNX (+ int8) for fastembed and check fastembed gives the same vectors

    # check everything up to the training call, without training
    python training/embed/train.py --pairs data/pairs.jsonl --output-dir runs/embed-v1 --dry-run
    # export and verify an existing model (e.g. the base model) without training
    python training/embed/train.py --export-only sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 \\
        --output-dir runs/base-onnx

Needs training/requirements.txt (PyTorch, sentence-transformers). Not a dependency of nai-core.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from common import NAI_CORE, check_author, read_training_rows, refuse_bench_path

sys.path.insert(0, str(NAI_CORE))
from app.nithron_models import parse_model_id

DEFAULT_BASE = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"  # Apache-2.0, nAI's default
CHECK_SENTENCES = [
    "Wie hoch ist die Kaution laut Mietvertrag?",
    "Vad kostade slutstädningen i stugan?",
    "What is the default IP address of the router?",
]


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------


def load_pairs(path: Path, limit: int | None) -> list[dict[str, Any]]:
    """Pairs with valid provenance; passage ids made consistent with passage texts."""
    pairs = [p for p in read_training_rows(path) if p.get("query") and p.get("passage")]
    for pair in pairs:
        provenance = pair.get("provenance") or {}
        if provenance.get("use") != "training":
            raise ValueError(
                f"pair {pair['query']!r} is not marked provenance.use == 'training' (principle 3)"
            )
        check_author(str(provenance.get("author") or ""))
        check_author(str(provenance.get("passage_author") or ""))
    texts: dict[str, str] = {}
    for pair in pairs:
        seen = texts.setdefault(pair["passage_id"], pair["passage"])
        if seen != pair["passage"]:
            raise ValueError(f"passage id {pair['passage_id']} is used for two different texts")
    # The same text under two ids would leak across the train/held-out split: use one id per text.
    canonical: dict[str, str] = {}
    for pid, text in sorted(texts.items()):
        canonical.setdefault(text, pid)
    pairs = [{**p, "passage_id": canonical[p["passage"]]} for p in pairs]
    return pairs[:limit] if limit else pairs


def split_by_passage(
    pairs: list[dict[str, Any]], eval_fraction: float, seed: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Hold out whole passages, so the eval measures generalization to unseen text."""
    passage_ids = sorted({p["passage_id"] for p in pairs})
    random.Random(seed).shuffle(passage_ids)
    held_out = set(passage_ids[: max(1, int(len(passage_ids) * eval_fraction))])
    train = [p for p in pairs if p["passage_id"] not in held_out]
    evaluation = [p for p in pairs if p["passage_id"] in held_out]
    return train, evaluation


def eval_corpus(
    train: list[dict[str, Any]], held_out: list[dict[str, Any]], distractors: int, seed: int
) -> dict[str, str]:
    """Held-out passages plus a fixed random sample of train passages as distractors.

    Re-encoding every train passage at each eval step would be slow for 40k passages, and
    held-out queries mostly need to beat other unseen text; the distractors keep it from being trivial.
    """
    corpus = {p["passage_id"]: p["passage"] for p in held_out}
    train_ids = sorted({p["passage_id"] for p in train})
    sample = random.Random(seed).sample(train_ids, min(distractors, len(train_ids)))
    texts = {p["passage_id"]: p["passage"] for p in train}
    corpus.update({pid: texts[pid] for pid in sample})
    return corpus


def data_fingerprint(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# Model pieces (imported lazily so --help works without PyTorch)
# ---------------------------------------------------------------------------


def ir_evaluator(pairs: list[dict[str, Any]], corpus: dict[str, str], name: str) -> Any:
    from sentence_transformers.sentence_transformer.evaluation import InformationRetrievalEvaluator

    queries = {f"q{i}": p["query"] for i, p in enumerate(pairs)}
    relevant: dict[str, set[str]] = defaultdict(set)
    for i, p in enumerate(pairs):
        relevant[f"q{i}"].add(p["passage_id"])
    return InformationRetrievalEvaluator(
        queries=queries,
        corpus=corpus,
        relevant_docs=dict(relevant),
        name=name,
        mrr_at_k=[10],
        ndcg_at_k=[10],
        accuracy_at_k=[1, 5],
        precision_recall_at_k=[5],
        show_progress_bar=False,
    )


def consistency_filter(pairs: list[dict[str, Any]], max_positive_rank: int | None) -> list[dict[str, Any]]:
    """Drop pairs whose positive the base model ranks below ``max_positive_rank`` (``positive_rank`` from
    mine_negatives.py): such queries are usually ambiguous ("what is the directive about"). Pairs without the
    field are kept."""
    if max_positive_rank is None:
        return pairs
    return [p for p in pairs if p.get("positive_rank", 0) <= max_positive_rank]


def file_negative_datasets(train: list[dict[str, Any]], count: int) -> dict[str, dict[str, list[str]]]:
    """Columns from negatives stored in the rows (mine_negatives.py), in two groups: ``mined``
    (anchor/positive/negative_1..N, rows with at least ``count`` negatives) and ``in_batch`` (anchor/positive,
    all other rows, trained on in-batch negatives only). Empty groups are left out."""
    mined = [p for p in train if len(p.get("negatives") or []) >= count]
    rest = [p for p in train if len(p.get("negatives") or []) < count]
    groups: dict[str, dict[str, list[str]]] = {}
    if mined:
        columns = {"anchor": [p["query"] for p in mined], "positive": [p["passage"] for p in mined]}
        for n in range(count):
            columns[f"negative_{n + 1}"] = [p["negatives"][n] for p in mined]
        groups["mined"] = columns
    if rest:
        groups["in_batch"] = {"anchor": [p["query"] for p in rest], "positive": [p["passage"] for p in rest]}
    return groups


def dataset_rows(dataset: Any) -> int:
    """Rows in a Dataset or a DatasetDict (one batch always comes from one of its datasets)."""
    if hasattr(dataset, "num_rows") and isinstance(dataset.num_rows, dict):
        return int(sum(dataset.num_rows.values()))
    return len(dataset)


def build_train_dataset(train: list[dict[str, Any]], model: Any, args: argparse.Namespace) -> Any:
    from datasets import Dataset, DatasetDict
    from sentence_transformers.util import mine_hard_negatives

    if args.file_negatives:
        groups = file_negative_datasets(train, args.hard_negatives)
        if len(groups) == 1:
            return Dataset.from_dict(next(iter(groups.values())))
        # one loss for both; the trainer draws each batch from one dataset, in proportion to their sizes
        return DatasetDict({name: Dataset.from_dict(columns) for name, columns in groups.items()})

    dataset = Dataset.from_dict(
        {"anchor": [p["query"] for p in train], "positive": [p["passage"] for p in train]}
    )
    if args.hard_negatives <= 0:
        return dataset
    corpus = sorted({p["passage"] for p in train})
    return mine_hard_negatives(
        dataset,
        model,
        corpus=corpus,
        num_negatives=args.hard_negatives,
        range_min=args.negative_range_min,  # skip the very top: often unlabeled positives
        range_max=args.negative_range_max,
        relative_margin=0.05,  # negatives must score clearly below the positive
        sampling_strategy="top",
        output_format="n-tuple",
        batch_size=args.batch_size,
        verbose=False,
    )


def build_trainer(model: Any, dataset: Any, evaluator: Any, args: argparse.Namespace) -> Any:
    import torch
    from sentence_transformers import SentenceTransformerTrainer
    from sentence_transformers.sentence_transformer import losses
    from sentence_transformers.sentence_transformer.training_args import (
        BatchSamplers,
        SentenceTransformerTrainingArguments,
    )

    loss: Any
    if args.cached_loss:
        loss = losses.CachedMultipleNegativesRankingLoss(model, mini_batch_size=args.mini_batch_size)
    else:
        loss = losses.MultipleNegativesRankingLoss(model)
    use_bf16 = torch.cuda.is_available() and torch.cuda.is_bf16_supported()  # also true on ROCm builds
    training_args = SentenceTransformerTrainingArguments(
        output_dir=str(args.output_dir / "checkpoints"),
        num_train_epochs=args.epochs,
        max_steps=args.max_steps if args.max_steps else -1,
        per_device_train_batch_size=args.batch_size,
        learning_rate=args.learning_rate,
        warmup_ratio=0.1,
        bf16=use_bf16,
        batch_sampler=BatchSamplers.NO_DUPLICATES,  # in-batch negatives must not be duplicates
        eval_strategy="steps",
        eval_steps=min(args.eval_steps, args.max_steps) if args.max_steps else args.eval_steps,
        save_strategy="steps",
        save_steps=min(args.eval_steps, args.max_steps) if args.max_steps else args.eval_steps,
        save_total_limit=2,
        logging_steps=1 if args.max_steps else max(1, args.eval_steps // 5),
        seed=args.seed,
        report_to="none",
    )
    return SentenceTransformerTrainer(
        model=model, args=training_args, train_dataset=dataset, loss=loss, evaluator=evaluator
    )


# ---------------------------------------------------------------------------
# Export for fastembed
# ---------------------------------------------------------------------------


def export_onnx(model_dir: str, out_dir: Path, quantize: bool) -> Path:
    """Write <out_dir>/onnx/model.onnx (+ onnx/model_quint8_avx2.onnx) and the tokenizer files."""
    from sentence_transformers import SentenceTransformer
    from sentence_transformers.backend import export_dynamic_quantized_onnx_model

    model = SentenceTransformer(model_dir, backend="onnx")
    model.save_pretrained(str(out_dir))
    if quantize:
        export_dynamic_quantized_onnx_model(model, "avx2", str(out_dir))
    expected = [out_dir / "onnx" / "model.onnx"] + (
        [out_dir / "onnx" / "model_quint8_avx2.onnx"] if quantize else []
    )
    missing = [str(p) for p in expected if not p.is_file()]
    if missing:
        raise RuntimeError(f"ONNX export did not produce {missing}")
    return out_dir


def fastembed_pooling(model: Any) -> str:
    """fastembed's name (MEAN or CLS) for the pooling of a sentence-transformers model's Pooling module.

    Granite R2 pools the CLS token, the MiniLM base takes the mean; checking an export with the wrong one fails
    even when the export is right."""
    for module in model:
        mode = getattr(module, "pooling_mode", None)  # sentence-transformers 5.x
        if mode is None and hasattr(module, "get_pooling_mode_str"):  # older versions
            mode = module.get_pooling_mode_str()
        if isinstance(mode, str):
            if mode in ("cls", "mean"):
                return mode.upper()
            raise ValueError(f"fastembed has no pooling for {mode!r}")
    raise ValueError("the model has no Pooling module")


def verify_fastembed(
    model_dir: Path,
    reference_model: str,
    min_cosine: float = 0.99,
    pooling: str | None = None,
    model_file: str = "onnx/model.onnx",
) -> float:
    """Load the export with fastembed (what nAI runs) and compare with sentence-transformers.

    ``pooling`` (MEAN or CLS) defaults to the reference model's own; ``model_file`` picks the fp32 or the int8
    file. Returns the lowest cosine similarity over the check sentences."""
    import numpy as np
    from fastembed import TextEmbedding
    from fastembed.common.model_description import ModelSource, PoolingType
    from sentence_transformers import SentenceTransformer

    reference = SentenceTransformer(reference_model, device="cpu")
    pooling = pooling or fastembed_pooling(reference)
    expected = reference.encode(CHECK_SENTENCES, normalize_embeddings=True)
    name = f"nithron-local/export-check-{pooling.lower()}-{Path(model_file).stem}"
    try:
        TextEmbedding.add_custom_model(
            model=name,
            pooling=PoolingType[pooling],
            normalization=True,
            sources=ModelSource(hf="nithron/export-check"),  # not downloaded: specific_model_path wins
            dim=int(expected.shape[1]),
            model_file=model_file,
        )
    except ValueError:
        pass  # already registered in this process
    embedder = TextEmbedding(model_name=name, specific_model_path=str(model_dir))
    got = np.asarray(list(embedder.embed(CHECK_SENTENCES)))
    got = got / np.linalg.norm(got, axis=1, keepdims=True)
    worst = float(min((expected * got).sum(axis=1)))
    if worst < min_cosine:
        raise RuntimeError(f"fastembed vectors differ from sentence-transformers (min cosine {worst:.4f})")
    return worst


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def train_main(args: argparse.Namespace) -> int:
    from sentence_transformers import SentenceTransformer

    refuse_bench_path(args.pairs)
    release = parse_model_id(args.release)
    if release is None or release.family != "vane":
        raise ValueError(
            f"--release must be a Vane model ID like 'vane-1-rc1' or 'vane-1', got {args.release!r}"
        )
    pairs = load_pairs(args.pairs, args.limit)
    loaded = len(pairs)
    pairs = consistency_filter(pairs, args.max_positive_rank)
    if args.max_positive_rank is not None:
        print(
            f"consistency filter (positive_rank <= {args.max_positive_rank}): kept {len(pairs)} of {loaded}"
        )
    train, held_out = split_by_passage(pairs, args.eval_fraction, args.seed)
    corpus = eval_corpus(train, held_out, args.eval_distractors, args.seed)
    print(
        f"{len(pairs)} pairs: {len(train)} train, {len(held_out)} held-out; "
        f"eval corpus {len(corpus)} passages (held-out + up to {args.eval_distractors} train distractors)"
    )

    model = SentenceTransformer(args.base_model)
    model.max_seq_length = args.max_seq_length
    evaluator = ir_evaluator(held_out, corpus, "heldout")
    print("base model on held-out pairs:", {k: round(v, 4) for k, v in evaluator(model).items() if "@" in k})

    dataset = build_train_dataset(train, model, args)
    print(f"train dataset: {dataset_rows(dataset)} rows, columns {dataset.column_names}")
    trainer = build_trainer(model, dataset, evaluator, args)
    plan = {
        "release": {"id": release.hf_id, "display_name": release.display_name, "label": args.release},
        "base_model": args.base_model,
        "pairs": str(args.pairs),
        "pairs_sha256": data_fingerprint(args.pairs),
        "train_rows": dataset_rows(dataset),
        "pairs_before_consistency_filter": loaded,
        "held_out_pairs": len(held_out),
        "loss": "CachedMultipleNegativesRankingLoss" if args.cached_loss else "MultipleNegativesRankingLoss",
        "teachers": sorted({(p.get("provenance") or {}).get("author", "?") for p in pairs}),
        "passage_authors": sorted({str((p.get("provenance") or {}).get("passage_author")) for p in pairs}),
        "args": {k: str(v) for k, v in vars(args).items()},
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "training_plan.json").write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    if args.dry_run:
        print(f"dry run: everything is ready; not training. Plan: {args.output_dir / 'training_plan.json'}")
        return 0

    trainer.train()
    final = args.output_dir / "model"
    model.save_pretrained(str(final))
    print(
        "fine-tuned model on held-out pairs:",
        {k: round(v, 4) for k, v in evaluator(model).items() if "@" in k},
    )
    if args.no_export:
        print(f"saved {final}; ONNX export skipped (--no-export)")
        return 0
    onnx_dir = export_onnx(str(final), args.output_dir / "fastembed", quantize=True)
    print(f"fastembed export {onnx_dir}: min cosine vs PyTorch {verify_fastembed(onnx_dir, str(final)):.4f}")
    print("next: evaluate on nai-bench (docs/lab/stage1-embedding-finetune.md, 'Evaluation')")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Fine-tune nAI's embedding model (Stage 1)")
    parser.add_argument("--pairs", type=Path, help="pairs.jsonl from generate_pairs.py")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--base-model", default=DEFAULT_BASE)
    parser.add_argument(
        "--release", default="vane-1", help="Nithron model this run is for (docs/lab/MODEL_NAMING.md)"
    )
    parser.add_argument("--epochs", type=float, default=1.0)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--learning-rate", type=float, default=2e-5)
    parser.add_argument("--max-seq-length", type=int, default=256)
    parser.add_argument(
        "--hard-negatives", type=int, default=1, help="mined negatives per pair (0: in-batch only)"
    )
    parser.add_argument(
        "--file-negatives",
        action="store_true",
        help="use the negatives stored in the pairs file (mine_negatives.py) instead of mining during training; pairs with fewer than --hard-negatives train on in-batch negatives only",
    )
    parser.add_argument(
        "--max-positive-rank",
        type=int,
        default=None,
        help="drop pairs whose positive the base model ranked below this (positive_rank from mine_negatives.py)",
    )
    parser.add_argument("--negative-range-min", type=int, default=5)
    parser.add_argument("--negative-range-max", type=int, default=50)
    parser.add_argument(
        "--cached-loss", action="store_true", help="CachedMNRL: large batches in little memory"
    )
    parser.add_argument("--mini-batch-size", type=int, default=32)
    parser.add_argument("--eval-fraction", type=float, default=0.05)
    parser.add_argument("--eval-steps", type=int, default=500)
    parser.add_argument(
        "--eval-distractors", type=int, default=2000, help="train passages added to the eval corpus"
    )
    parser.add_argument("--limit", type=int)
    parser.add_argument("--seed", type=int, default=13)
    parser.add_argument(
        "--dry-run", action="store_true", help="prepare everything, then stop before training"
    )
    parser.add_argument(
        "--no-export", action="store_true", help="save the model but skip the ONNX/int8 export"
    )
    parser.add_argument("--max-steps", type=int, help="stop after N optimizer steps (smoke tests)")
    parser.add_argument(
        "--export-only", metavar="MODEL", help="only export MODEL to ONNX and verify with fastembed"
    )
    args = parser.parse_args()

    if args.max_steps is not None and args.max_steps <= 0:
        parser.error("--max-steps must be positive")
    if args.export_only:
        out = export_onnx(args.export_only, args.output_dir, quantize=True)
        print(
            f"exported {args.export_only} to {out}: min cosine {verify_fastembed(out, args.export_only):.4f}"
        )
        return 0
    if not args.pairs:
        parser.error("--pairs is required unless --export-only is given")
    return train_main(args)


if __name__ == "__main__":
    sys.exit(main())
