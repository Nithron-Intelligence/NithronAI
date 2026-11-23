# Handoff

> Read this first. Any agent (Claude Code, Codex, Kimi Code, …) or person can continue from here without
> the chat history. **Every agent session updates this file before it ends** (see `CONTRIBUTING.md`).
> Keep it short; link to other docs instead of copying them.

## Status now

- **Updated:** 2026-11-23, round 3, step 0 (this file created).
- **Branch:** `lab/stage-0` (all lab work), based on local `main` (release 0.5.0). **Nothing is pushed.**
- **Done:** rounds 1–2 (see History). Round 3 step 0 (handoff doc, `AGENTS.md`).
- **In progress:** round 3. Steps, in order:
  1. Fix the release on `main`: LICENSE byte-identical to NithronOS (`6c7bc57`), Niro in NOTICE, move the
     local `v0.5.0` tag, CHANGELOG line, rebase `lab/stage-0`; check whether nai-core 0.4.0 is public on GHCR.
  2. Confirmed decisions: reranker auto-policy (bge, top 10, off on NAS-class), embedding-model-change
     detection (ask to re-index), TrueNAS adapter step 1 (read-only API discovery + custom-app compose + doc),
     LICENSE files for `evals/` and `training/` (Apache-2.0) and nai-bench items (CC-BY-4.0),
     `docs/business/licensing-options.md`.
  3. nai-bench v1: dev/test split with a guard, first 100 corpus files, first 100 questions, review.py
     progress/resume.
  4. NithronOS template sync instructions in `docs/KNOWN_ISSUES.md`.
- **Next after round 3:** human review of nai-bench items; finish v1 (to 300+ files, 625 questions);
  synthetic corpus generator for Stage 1; Vane 1 / Loupe 1 pilot training on the GPU.

## Waiting on the human

- **Pushes** (agents never push): `main`, tag `v0.5.0` (triggers the GHCR release), remote branch deletion
  `phase1-ask-your-nas`. Commands: see the last round's final report; to be refreshed in step 1.
- **Licensing direction** for nAI itself (NCL + commercial vs dual license vs open core): not decided.
- **nai-bench review:** all items are unreviewed (`python evals/nai-bench/review.py`).
- **Trademark search** for Nithron Vane / Loupe / Tern / Nox before any public release.
- **NithronOS template sync:** hand the step list (round 3 step 4) to the session that owns NithronOS.
- **Branch `chore/ncl-add-nithro`:** obsolete (stale "Nithro" text); delete or keep?
- **Docker disk:** ~50 GB images (ROCm PyTorch ~40 GB) + ~46 GB build cache; prune when not needed.

## Decisions log (newest first)

| Date | Decision | Reason |
|---|---|---|
| 2026-11-23 | Second platform after NithronOS: **TrueNAS** (read-only API discovery + custom-app compose first; no permission sync yet). | Compose-native custom apps, big audience, JSON-RPC API with per-user keys, NFSv4 ACLs; Unraid's store asks for an OSI license. |
| 2026-11-23 | Lab code (`evals/`, `training/`) Apache-2.0; nai-bench items we write CC-BY-4.0; third-party corpus files keep their own licenses. nAI's own license direction **not decided**. | Model claims must be reproducible by others; core licensing needs a lawyer. |
| 2026-11-23 | **Reranker:** off on NAS-class hardware; auto-enable `BAAI/bge-reranker-v2-m3-int8` on stronger hardware, reranking only the top 10; overridable. | bge: MRR 0.793 → 0.918 but 2–4 s per question on 2 cores. |
| 2026-11-23 | **Loupe 1** = fine-tune of `bge-reranker-v2-m3` (int8), distilled from `Qwen3-Reranker-0.6B` as teacher. | Best permissive, multilingual, NAS-viable reranker; Qwen3 best but ~40 s/question. |
| 2026-11-23 | **No model that needs `trust_remote_code`** (we never run code from model repos). | Security; it also rules out models without ONNX builds. |
| 2026-11-23 | **Vane 1** base = `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (Apache-2.0); `multilingual-e5-small` (MIT) is the comparison candidate; base-model training data audit is open. | Drop-in upgrade for existing indexes. |
| 2026-11-23 | **Model names:** Vane (embeddings), Loupe (reranker), Tern (small answering), Nox (flagship + agent); one syllable each; public names always "Nithron …"; IDs `nithron/<family>-<version>[-mini|-max]`; `.5` minor steps; any Vane change forces a re-index; defined only in `app/nithron_models.py`. | [MODEL_NAMING.md](lab/MODEL_NAMING.md). |
| 2026-11-23 | **nAI is NAS-agnostic** (any NAS OS); NithronOS is the reference platform; NAS specifics behind adapters (ADR-0004). Stage 3 = NAS agent model on a common tool interface. | Sell beyond NithronOS. |
| 2026-11-23 | `packages/` (rag-kit, toolpacks, model-router) deleted; poppler (GPL) must not come back. | Unused; licensing. |
| 2026-11-23 | nai-bench v1 = 500 answerable + 125 unanswerable, even over 4 categories × 5 languages; dev/test split; only human-reviewed items count. | ±0.03 MRR margin (V1_PLAN.md). |
| 2026-11-22 | **Lab direction** (ADR-0002): Nithron AI builds private local models for NAS-class hardware. Stages: 0 measurement (nai-bench), 1 Vane/Loupe, 2 Tern/Nox answering models, 3 NAS agent model, 4 lab practice (reports, open weights, auto-install). | Niche nobody serves; nAI is the product. |
| 2026-11-22 | **Data rules (binding):** (1) never train on users' NAS data, questions or answers without explicit opt-in; training data is synthetic or public and permissively licensed. (2) Check and record every model/dataset/tool license before use ([register](lab/MODEL_AND_DATA_LICENSES.md)). (3) Never generate training data with services whose terms forbid training competing models, **including Claude**; use approved open-weight teachers; every item has `provenance`; **Claude-written text is `use: eval-only` and never in training splits**. (4) Every model claim is backed by a committed nai-bench result. Nothing from `evals/nai-bench/` is ever used for training. | Legal and reputational safety. |
| 2026-11-22 | Benchmark LLM runs at temperature 0. | 0.1 gave ±0.09 swings between identical runs. |
| 2026-11-21 | `LICENSE` must stay **byte-identical** to NithronOS's; product text goes in `NOTICE`. No AGPL/GPL dependencies. | Shared Nithron Community License. |
| 2026-11-21 | Product scope (ADR-0003): don't compete with chat UIs; simple UI; interoperability via `/v1` and MCP. | Focus. |

## History

- **Round 1 (2026-11-22):** lab direction and docs; nai-bench v0 (27 files, 56 questions); eval harness;
  Ollama smoke test; Stage 1 plan and `training/embed/` skeleton. Baseline (v0, provisional): hybrid MRR
  **0.793**, Hit@5 0.933; qwen2.5:1.5b answers correct 0.578, correct refusal 0.545; qwen2.5:7b reference
  correct 0.822. Key commits (after rebase): `9e9a99f` nai-bench, `ee6ec73` smoke, `d4bd130` baseline,
  `ec38d6b` lab docs, `2d8cec5` Stage 1.
- **Round 2 (2026-11-23):** release 0.5.0 on `main` (`5534fca`, local tag); docs moved out of CLAUDE.md
  (`dd25e00`); NAS adapter layer (`5c583f9`); reranker off by default (`9e20901`); model names (`cf0ad0a`);
  nai-bench v1 plan (`a2ec841`) and review workflow (`3f3c184`); business draft (`0eb5e3e`); simulated NAS
  (`f93d102`); reranker comparison (`cff67d8`); ROCm trainer (`c51226f`).
  - Rerankers (top-30, 2 threads): none 0.793; old English default 0.791; mmarco 0.802; **bge-m3 int8 0.918**
    (3.7 s; top-10: 0.878 at 2.1 s); Qwen3-Reranker 0.956 (40 s).
  - Simulated NAS (2 CPUs / 4 GB each, CPU only): index 27 s; search 0.20 s; extractive answer 0.20 s;
    qwen2.5:1.5b answer 4.7 s median (p95 21 s); nai-core 1.1 GB, Ollama 1.6 GB.
  - ROCm smoke: 2 training steps + ONNX export on the RX 7900 XTX in 37 s.
- **Round 3 (2026-11-23):** in progress (see Status).

## How to resume

```bash
# Setup (Python 3.11; never `uv run` inside apps/nai-core: it re-syncs and wipes .venv)
cd apps/nai-core && uv venv -p 3.11 .venv && uv pip install -p .venv/bin/python -r requirements-full.txt \
    pytest pytest-asyncio httpx ruff==0.17.6 mypy && cd ../..

# Tests and checks (all must pass before every commit)
(cd apps/nai-core && .venv/bin/python -m pytest -q && .venv/bin/ruff check app tests \
    && .venv/bin/ruff format --check app tests && .venv/bin/mypy app)
apps/nai-core/.venv/bin/python -m pytest -q evals/tests training/tests
apps/nai-core/.venv/bin/ruff check --config apps/nai-core/pyproject.toml evals training

# Bench stack (kept STOPPED, not removed: volumes hold models + index). AMD GPU -> ROCm overlay.
export OLLAMA_IMAGE=ollama/ollama:0.40.17-rocm
docker compose -f infra/compose.bench.yaml -f infra/compose.bench.rocm.yaml up -d --wait   # start
docker compose -f infra/compose.bench.yaml -f infra/compose.bench.rocm.yaml stop           # pause (not down -v)

# Benchmark (details and variants: evals/README.md)
apps/nai-core/.venv/bin/python evals/run_baseline.py --index-corpus /shares/nai-bench
python evals/nai-bench/review.py --summary

# ROCm trainer (AMD GPU; PyTorch only inside the container, never on the host)
docker compose -f training/docker/compose.rocm.yaml run --rm trainer python3 training/docker/gpu_check.py
```

Gotchas: the GPU is AMD (RX 7900 XTX, 24 GB) → ROCm containers only; the container writes files as root
(chown afterwards, see `training/README.md`); Docker uses ~100 GB (images + build cache); system Python is
3.14, use the 3.11 venv; commit as the user with no AI attribution; ask before pushes, deletions, system
package installs.

## Where things live

[README](../README.md) · [CONTRIBUTING](../CONTRIBUTING.md) · [ARCHITECTURE](ARCHITECTURE.md) ·
[KNOWN_ISSUES](KNOWN_ISSUES.md) · [ADRs](ADRs/) · [Lab ROADMAP](lab/ROADMAP.md) ·
[MODEL_NAMING](lab/MODEL_NAMING.md) · [License register](lab/MODEL_AND_DATA_LICENSES.md) ·
[Stage 1 plan](lab/stage1-embedding-finetune.md) · [NAS adapters](architecture/nas-adapters.md) ·
[Business: product and licensing](business/product-and-licensing.md) ·
[nai-bench](../evals/nai-bench/README.md) and [v1 plan](../evals/nai-bench/V1_PLAN.md) ·
[Evals and reproduce commands](../evals/README.md) · [Training](../training/README.md) ·
[Releasing](RELEASING.md)
