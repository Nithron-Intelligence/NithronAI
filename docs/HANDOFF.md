# Handoff

> Read this first. Any agent (Claude Code, Codex, Kimi Code, …) or person can continue from here without
> the chat history. **Every agent session updates this file before it ends** (see `CONTRIBUTING.md`).
> Keep it short; link to other docs instead of copying them.

## Status now

- **Updated:** 2026-11-23, round 3, end of the second session (it took over mid-step 2 after the first one
  ran out of tokens). Stopped cleanly at a commit; **no uncommitted work.**
- **Branch:** `lab/stage-0` (all lab work), on top of local `main` (release 0.5.0, tag `v0.5.0` = `d496d16`).
  **Nothing is pushed.**
- **Done in round 3:** steps 0, 1, 2a–2e and 4 (see History). The facts from the old CLAUDE.md are in
  committed docs (ADR-0003, README roadmap, KNOWN_ISSUES).
- **Next: step 3, nai-bench v1 (not started).** Do it in this order, closing out (HANDOFF + checks + commit)
  after each bullet and every 25 files or questions:
  1. **Split rules first.** v1 lives in `evals/nai-bench/v1/`: `questions-dev.jsonl` and
     `questions-test.jsonl` (separate files) plus its own corpus and manifest. Split by hash, never by hand:
     `sha256(item_id)` mod 100 < 40 → dev, else test (V1_PLAN.md: 40/60). Every loader (`naibench.load_items`
     and the eval scripts) refuses the test file unless called with an explicit `--final-run` flag, and each
     final run appends a line (date, commit, label, item count, dataset hash) to
     `evals/results/test-ledger.jsonl`. Add a test that `eval_retrieval`/`eval_answers`/`run_baseline` can't
     load test items without the flag. v0 (`evals/nai-bench/questions.jsonl`) stays as the frozen smoke set.
  2. **Training guard:** `training/embed/check_overlap.py` already rejects nai-bench text; also make
     `training/embed/common.py` refuse any input row whose provenance says `use: eval-only` or a Claude
     author, with a test (only `train.py` checks this today).
  3. **review.py for short sessions:** show progress ("23/100 reviewed"), `q`/Ctrl+C keep all decisions,
     resume at the first unreviewed item, one-line summary at the end; tests for save and resume.
  4. **Corpus:** first 100 v1 files per V1_PLAN.md (EUR-Lex in 5 languages, DE/SE statutes, US federal
     publications, Gutenberg distractors, fictional docs); download with `curl`, record source URL, license,
     retrieval date, author and SHA-256 per file in the v1 manifest; Claude-written files say so and are
     eval-only. Close out every 25 files.
  5. **Questions:** first 100 v1 questions spread over the 4 categories × 5 languages (+ unanswerable), all
     `review_status: unreviewed`, `provenance.author: claude` ("Claude-written"), `use: eval-only`;
     validate with `naibench.validate`. Close out every 25 questions.
- **After round 3:** human review of nai-bench items; finish v1 (to 300+ files, 625 questions);
  synthetic corpus generator for Stage 1; Vane 1 / Loupe 1 pilot training on the GPU.

## Waiting on the human

- **Pushes** (agents never push). Checked 2026-11-23 with `git ls-remote` + `git fetch`: **`origin/main`
  moved** to `c7d20d4` (PRs #1 and #2 merged on GitHub: the same Nithro→Niro LICENSE/NOTICE sync, LICENSE
  hash identical). Local `main` (release commits, tag `v0.5.0` = `d496d16`) has **diverged**, so a plain push
  is rejected. Merging is clean and changes no files (verified with `git merge-tree`); the tag can stay:
  ```bash
  git switch main
  git merge origin/main -m "Merge origin/main (Niro license sync, PRs #1 and #2)"   # no file changes
  git push origin main
  git push origin v0.5.0      # runs release.yml: publishes nai-core:0.5.0, moves latest and 0
  git merge lab/stage-0       # optional: bring the lab work onto main (clean in this order; not ff)
  git push origin main
  git push origin lab/stage-0 # optional backup of the branch
  git push origin --delete phase1-ask-your-nas chore/ncl-add-nithro license-niro   # all merged
  git branch -D chore/ncl-add-nithro                                               # local copy
  ```
  Don't merge `lab/stage-0` straight into `origin/main` first: NOTICE conflicts in that order.
  GHCR (anonymous check, 2026-11-23): `nai-core` tags `0.4.0`, `0.4`, `0`, `latest`, `sha-6686b59` are
  public; manifest 0.4.0 → 200.
- **Licensing direction** for nAI itself (NCL + commercial vs dual license vs open core): not decided.
- **nai-bench review:** all items are unreviewed (`python evals/nai-bench/review.py`).
- **Trademark search** for Nithron Vane / Loupe / Tern / Nox before any public release.
- **NithronOS template sync:** hand the patch in `docs/KNOWN_ISSUES.md` ("Hand-over: NithronOS template sync";
  applies cleanly to NithronOS `47def8c`) to the session that owns NithronOS.
- **Branch `chore/ncl-add-nithro`** (local + remote) and remote `license-niro`: both already merged into
  `origin/main` (PRs #1, #2); deletion commands are in the push block above.
- **Docker disk:** ~50 GB images (ROCm PyTorch ~40 GB) + ~46 GB build cache; prune when not needed.
- **TrueNAS manual test** on a real TrueNAS (VM) with a read-only API key: `packaging/truenas/README.md`.
- **Reranker ONNX license:** fastembed's int8 bge build comes from `onnx-community/bge-reranker-v2-m3-ONNX`,
  whose card states no license (base model Apache-2.0); fine for now, Loupe 1 ships our own export.
- **UI checks:** CONTRIBUTING.md lists no UI test procedure; the new re-index notice was checked by rendering
  the function in Node only. Decide whether to add a Playwright smoke test.

## Decisions log (newest first)

| Date | Decision | Reason |
|---|---|---|
| 2026-11-23 | Second platform after NithronOS: **TrueNAS** (read-only API discovery + custom-app compose first; no permission sync yet). | Compose-native custom apps, big audience, JSON-RPC API with per-user keys, NFSv4 ACLs; Unraid's store asks for an OSI license. |
| 2026-11-23 | Lab code (`evals/`, `training/`) Apache-2.0; nai-bench items we write CC-BY-4.0 (was CC0); third-party corpus files keep their own licenses. Official texts downloaded byte-exact; scope in `NOTICE`. nAI's own license direction **not decided**. | Model claims must be reproducible by others; core licensing needs a lawyer. |
| 2026-11-23 | **Embedding-model change:** nAI detects it by model ID, keeps the old vectors, pauses semantic search and asks an admin before re-indexing (`NAI_EMBEDDINGS_AUTO_REINDEX=true` opts back into automatic re-embedding). Vane weights are never replaced under the same ID. | Silent re-embeds took hours on big NAS indexes; a same-name weight swap would mix incompatible vectors. |
| 2026-11-23 | Version rules accepted: `.5` minor steps, `-mini`/`-max` variants, any Vane change forces a re-index. | Proposed in round 2. |
| 2026-11-23 | **Reranker:** `NAI_RERANKER=auto|on|off` (default auto; true/false still work); default model `BAAI/bge-reranker-v2-m3-int8`; top 10 (`NAI_RERANKER_CANDIDATES`). Auto = on only with 8+ effective cores (physical, capped by cgroup quota), 8+ GB RAM, 2+ GB free, AVX2 on x86; GPU doesn't count (CPU onnxruntime). NithronOS template: off. | Budget ~1 s per question for the top 10; measured 2.1 s (2 threads), 1.1 s (4), 0.7 s (8) on Zen 4 (provisional, v0 unreviewed). |
| 2026-11-23 | Hardware detection honours cgroup CPU quota / memory limit and counts physical cores. | Inside `docker --cpus=2` it used to report the whole host (32 CPUs). |
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
  correct 0.822. Key commits ("subject" `hash as of the round-3 rebase`; hashes change when the branch is
  rebased, search by subject): "Add nai-bench…" `4f71db4`, "Add an nAI + Ollama bench stack…" `b277682`,
  "Record the nai-bench baseline…" `2306b19`, "Write down the Nithron AI lab direction" `d6f036e`,
  "Plan the Stage 1 embedding fine-tune…" `b2dfac0`.
- **Round 2 (2026-11-23):** release 0.5.0 on `main` ("Release 0.5.0" `5534fca`); docs moved out of CLAUDE.md
  (`9be6c78`); NAS adapter layer (`caf55c6`); reranker off by default (`d7c266c`); model names (`12fb275`);
  nai-bench v1 plan (`20818bf`) and review workflow (`80f588d`); business draft (`5d19696`); simulated NAS
  (`cf687f8`); reranker comparison (`e1d252f`); ROCm trainer (`d67dcb7`); review fixes (`7f47cf9`).
  - Rerankers (top-30, 2 threads): none 0.793; old English default 0.791; mmarco 0.802; **bge-m3 int8 0.918**
    (3.7 s; top-10: 0.878 at 2.1 s); Qwen3-Reranker 0.956 (40 s).
  - Simulated NAS (2 CPUs / 4 GB each, CPU only): index 27 s; search 0.20 s; extractive answer 0.20 s;
    qwen2.5:1.5b answer 4.7 s median (p95 21 s); nai-core 1.1 GB, Ollama 1.6 GB.
  - ROCm smoke: 2 training steps + ONNX export on the RX 7900 XTX in 37 s.
- **Round 3 (2026-11-23), session 2 commits:** `3222ff6` ask before re-embedding on model change, `2932379`
  docs + version rules, `37381c2` reranker auto policy + cgroup-aware hardware detection, `0f1c251` TrueNAS
  adapter step 1, `255feea` lab code Apache-2.0 / nai-bench CC-BY-4.0, `f054402` licensing options,
  `94057f2` NithronOS template patch, then the closing HANDOFF commit. Tests: 215 nai-core, 66 evals/training.
- **Round 3 (2026-11-23):** handoff doc; LICENSE synced with NithronOS (sha256 `62f2cf4c…c05c177`, "Sync
  LICENSE with NithronOS…" `d496d16` on `main`), tag moved, branch rebased. New session from step 2: 2a
  embedding-model change detection (`3222ff6`); 2b reranker auto policy + cgroup-aware hardware detection;
  bge int8 top-10 latency: 2 threads 2.08 s, 4 threads 1.09 s, 8 threads 0.70 s
  (`evals/results/rerankers-threads-2026-11-23.md`); 2c TrueNAS adapter step 1 (read-only discovery, 10 tests
  with a fake JSON-RPC server, `packaging/truenas/`); 2d `evals/` + `training/` Apache-2.0, nai-bench items
  CC-BY-4.0 (scope in `NOTICE`; root LICENSE unchanged); 2e `docs/business/licensing-options.md` (NCL vs
  AGPL dual vs open core; Unraid CA needs an OSI license); step 4 NithronOS template patch (reranker off,
  `NAI_NAS_PLATFORM=nithronos`). Rest in progress (see Status).

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
[Licensing options](business/licensing-options.md) ·
[nai-bench](../evals/nai-bench/README.md) and [v1 plan](../evals/nai-bench/V1_PLAN.md) ·
[Evals and reproduce commands](../evals/README.md) · [Training](../training/README.md) ·
[Releasing](RELEASING.md)
