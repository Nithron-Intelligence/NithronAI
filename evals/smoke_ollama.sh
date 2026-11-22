#!/usr/bin/env bash
# nAI + Ollama end-to-end smoke test, from a clean stack to a pass/fail result.
#
#   evals/smoke_ollama.sh                 # CPU Ollama
#   ROCM=1 evals/smoke_ollama.sh          # AMD GPU (ROCm image + /dev/kfd, /dev/dri)
#   KEEP=1 evals/smoke_ollama.sh          # leave the stack running afterwards
#
# Needs: docker compose, python3 with httpx (e.g. apps/nai-core/.venv). Model: $NAI_LLM_MODEL
# (default qwen2.5:1.5b, Apache-2.0, ~1 GB download).
set -euo pipefail

cd "$(dirname "$0")/.."
export NAI_LLM_MODEL="${NAI_LLM_MODEL:-qwen2.5:1.5b}"
PYTHON="${PYTHON:-apps/nai-core/.venv/bin/python}"
[ -x "$PYTHON" ] || PYTHON=python3

files=(-f infra/compose.bench.yaml)
if [ "${ROCM:-0}" = "1" ]; then
    export OLLAMA_IMAGE="${OLLAMA_IMAGE:-ollama/ollama:0.40.17-rocm}"
    files+=(-f infra/compose.bench.rocm.yaml)
fi

cleanup() {
    if [ "${KEEP:-0}" != "1" ]; then
        docker compose "${files[@]}" down -v
    fi
}
trap cleanup EXIT

docker compose "${files[@]}" up -d --build --wait
docker compose "${files[@]}" exec -T ollama ollama pull "$NAI_LLM_MODEL"
"$PYTHON" evals/smoke_ollama.py --corpus-path /shares/nai-bench
