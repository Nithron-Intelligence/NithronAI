# nAI evaluations

| What | Where |
|---|---|
| The benchmark (corpus, questions, review tool, v1 plan) | [`nai-bench/`](nai-bench/README.md) |
| Retrieval eval (Recall, Precision, Hit, MRR, nDCG, page Hit) | [`retrieval/eval_retrieval.py`](retrieval/README.md) |
| Answer-quality eval (facts, citations, refusals, language, optional judge) | [`answers/eval_answers.py`](answers/eval_answers.py) |
| Full run with pinned settings + Markdown summary | [`run_baseline.py`](run_baseline.py) |
| Reranker comparison (offline, same candidates as nAI) | [`rerankers/bench_rerankers.py`](rerankers/bench_rerankers.py) |
| NAS-like measurements (indexing time, latency, memory) | [`measure_nas.py`](measure_nas.py) |
| End-to-end smoke test with Ollama | [`smoke_ollama.sh`](smoke_ollama.sh) |
| Results | [`results/`](results/) |

Every result file records the git commit, nAI version, models, settings, dataset hashes and how many
items are human-reviewed. Numbers from runs that include unreviewed items are marked **PROVISIONAL**;
published numbers use `--reviewed-only`.

## Reproduce

All commands run from the repository root. Python: the nai-core venv (`apps/nai-core/.venv`, see
`CONTRIBUTING.md`) has everything except the reranker comparison, which needs `training/requirements.txt`.
The bench stack is kept **stopped, not removed** between runs: its volumes hold the Ollama models and the
index. `docker compose ... stop` to pause, `start` to resume; only `down -v` deletes the volumes.

### Bench stack

```bash
# GPU (AMD, ROCm) or CPU. NAI_IMAGE / OLLAMA_IMAGE are optional overrides.
export OLLAMA_IMAGE=ollama/ollama:0.40.17-rocm
docker compose -f infra/compose.bench.yaml -f infra/compose.bench.rocm.yaml up -d --build --wait
docker compose -f infra/compose.bench.yaml exec ollama ollama pull qwen2.5:1.5b
docker compose -f infra/compose.bench.yaml exec ollama ollama pull qwen2.5:7b     # optional judge
# NVIDIA or CPU only: leave out compose.bench.rocm.yaml and OLLAMA_IMAGE.
```

### Baseline (retrieval + answers)

```bash
apps/nai-core/.venv/bin/python evals/run_baseline.py --index-corpus /shares/nai-bench \
    --judge-url http://localhost:11434/v1 --judge-model qwen2.5:7b \
    --notes "describe the hardware here"
# published numbers: add --reviewed-only (needs reviewed items: evals/nai-bench/review.py)
```

Variants used for the committed results:

```bash
# reranker on (restarts nai-core with NAI_RERANKER=true)
NAI_RERANKER=true docker compose -f infra/compose.bench.yaml -f infra/compose.bench.rocm.yaml up -d --wait nai-core
apps/nai-core/.venv/bin/python evals/run_baseline.py --label baseline-rerank --methods hybrid --no-llm
# a bigger answering model as a reference
NAI_LLM_MODEL=qwen2.5:7b docker compose -f infra/compose.bench.yaml -f infra/compose.bench.rocm.yaml up -d --wait nai-core
apps/nai-core/.venv/bin/python evals/run_baseline.py --label reference-qwen2.5-7b --methods hybrid \
    --judge-url http://localhost:11434/v1 --judge-model qwen2.5:7b
```

### Reranker comparison

```bash
python -m venv .venv-train && .venv-train/bin/pip install torch --index-url https://download.pytorch.org/whl/cpu
.venv-train/bin/pip install -r training/requirements.txt
# nAI must run with NAI_RERANKER=false (the default)
apps/nai-core/.venv/bin/python evals/rerankers/bench_rerankers.py collect --output /tmp/candidates.json
.venv-train/bin/python evals/rerankers/bench_rerankers.py run --candidates /tmp/candidates.json --threads 2 \
    --output evals/results/rerankers-$(date +%F).json
```

### Simulated NAS

```bash
docker compose -f infra/compose.bench.yaml -f infra/compose.bench.rocm.yaml stop
OLLAMA_IMAGE=ollama/ollama:0.40.17-rocm \
    docker compose -f infra/compose.bench.yaml -f infra/compose.bench.nas-sim.yaml up -d --wait
apps/nai-core/.venv/bin/python evals/measure_nas.py --label simulated-nas \
    --profile "nai-core 2 CPUs / 4 GB, Ollama 2 CPUs / 4 GB (CPU only) on a Ryzen 9 7950X"
# back to the normal bench stack (the nas-sim data volume is kept)
docker compose -f infra/compose.bench.yaml -f infra/compose.bench.rocm.yaml up -d --wait
```

On a real NAS: run nAI there, index `evals/nai-bench/corpus`, and use `--environment real-nas` with the
NAS model in `--profile` (and `--containers` set to the container names on that NAS).

### Smoke test

```bash
ROCM=1 evals/smoke_ollama.sh     # stops the stack afterwards; KEEP=1 leaves it running, CLEAN=1 removes it
```

### CI

The `nai-bench Evaluation` job (`.github/workflows/ci.yml`) runs retrieval and extractive answers with
Tesseract (`eng+deu`, like the image) on every push to `main`, and uploads the results as an artifact.
