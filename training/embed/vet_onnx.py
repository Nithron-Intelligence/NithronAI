"""
Vet an embedding model for nAI's runtime: export to ONNX + int8 exactly like a Vane release (train.export_onnx)
and check fastembed parity against sentence-transformers (PyTorch), for our export and for any ONNX files the
model repo ships. Run in the ROCm trainer container (PyTorch inside).

    python3 training/embed/vet_onnx.py --model ibm-granite/granite-embedding-97m-multilingual-r2 --pooling CLS \
        --out training/runs/vet-granite-97m
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from huggingface_hub import snapshot_download
from train import export_onnx, verify_fastembed


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--model", required=True)
    parser.add_argument("--pooling", default="MEAN", choices=["MEAN", "CLS"])
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    results: dict[str, float | str] = {}
    ours = export_onnx(args.model, args.out / "export", quantize=True)
    upstream = Path(snapshot_download(args.model, allow_patterns=["onnx/*", "*.json", "tokenizer*"]))
    for label, folder, file in [
        ("our fp32", ours, "onnx/model.onnx"),
        ("our int8", ours, "onnx/model_quint8_avx2.onnx"),
        ("upstream fp32", upstream, "onnx/model.onnx"),
        ("upstream int8", upstream, "onnx/model_quint8_avx2.onnx"),
    ]:
        if not (folder / file).exists():
            results[label] = "missing"
            continue
        try:
            results[label] = round(verify_fastembed(folder, args.model, 0.0, args.pooling, file), 4)
        except Exception as e:  # report and continue with the other variants
            results[label] = f"error: {e}"[:200]
        size = (folder / file).stat().st_size
        print(f"{label:14} min cosine vs PyTorch: {results[label]}  ({size / 1e6:.0f} MB)", flush=True)
    (args.out / "parity.json").write_text(
        json.dumps({"model": args.model, "pooling": args.pooling, **results}, indent=1)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
