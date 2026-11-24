# Handoff

> Read this first. Any agent (Claude Code, Codex, Kimi Code, …) or person can continue from here without
> the chat history. **Every agent session updates this file before it ends** (see `CONTRIBUTING.md`).
> Keep it short; link to other docs instead of copying them.

## Status now

- **Round 9 (2026-11-24), in progress:** reranker audit, Vane 1 pilot on Granite, data scaling. Started at
  lab/stage-0 = `2e8e425`, main = `38c5ddd`, both pushed, clean (untracked local-only: `.claude/`, `CLAUDE.md`,
  `.gitattributes`, `graphify-out/`).
- **Round 9 permissions (2026-11-24):** commit, push, open and merge PRs as the human with the configured git
  identity (merge commits; no attribution trailers, no history rewrite, no force-push, never bypass branch
  protection; no tags). Start/stop the bench containers, Ollama and the ROCm trainer container; training runs
  ≤ 3 h unattended, data-generation runs ≤ 8 h unattended, each with its command and config recorded here first
  and generation writing incrementally. Delete only the listed leftovers (images `nai-core:kwonly-local`,
  `:0.7.0-local`, `:granite-local`, `:0.6.0-local`, `:lab-stage-0`, `ghcr.io/nithron/nithronai/nai-core:0.7.0`,
  volume `nai-bench_nai-nas-sim-r8-2g-data`) after checking no running container uses them; ask before deleting
  anything else. User-space installs (sudo → print the command for the human). Check free disk before every large
  download or generation run.
- **Round 9, section 1 done:** state checked (as above). Docker cleanup: deleted `nai-core:0.7.0-local`,
  `:granite-local`, `:0.6.0-local`, `:lab-stage-0`, `ghcr.io/nithron/nithronai/nai-core:0.7.0`, then
  `nai-core:kwonly-local` once the bench stack was recreated on a new image, and the volume
  `nai-bench_nai-nas-sim-r8-2g-data`. The images share most layers: the first five deletions freed **0.95 GB**; the
  image store went 54.16 → 53.21 GB net, after also adding `nai-core:r9-bench` and deleting `kwonly-local`; the
  volume was negligible (volumes stayed at 30.14 GB). Docker still holds ~53 GB of images and
  ~49 GB of build cache (pruning those needs the human's go).
- **Round 9, section 2 done: reranker lineage audit** ([reranker-audit.md](lab/reranker-audit.md), commit `5d09e94`).
  bge-reranker-v2-m3 **fails** (MS MARCO in bge-m3's and its own fine-tuning data); its int8 ONNX repo states no
  license (low risk, unverifiable provenance); Qwen3-Reranker-0.6B **fails** (MS MARCO in the supervised data).
  No clean multilingual reranker with a training-data statement exists; the closest, Horizon-Labs
  multilingual-reranker-small/-base (permissive data, labels distilled from Qwen3-Reranker-4B), measured on v1
  dev with the reranker-on setup (top 10, 8 threads): MRR none 0.834, bge 0.896 (0.81 s), Horizon-small 0.886
  (0.42 s), Horizon-base 0.905 (0.98 s); all tied within ±0.09
  ([results](../evals/results/v1-dev-rerankers-r9-2026-11-24.md)). Defaults unchanged; decisions under "Waiting on
  the human".
- **Round 9, section 3 done: Vane 1 rc1 on Granite** ([results](../evals/results/v1-dev-vane1-rc1-2026-11-24.md)).
  Pilot pairs re-checked (1,875 rows, 0 nai-bench overlap, guard passed); config committed first (`c44e19b`);
  trained 22 steps in 13 s. v1 dev, embedding-only MRR / Hit@5: granite 0.854 / 0.979, **rc1 0.853 / 0.936**,
  rc0 (MiniLM pilot) 0.613 / 0.766, MiniLM 0.444 / 0.532; cross-language MRR granite 0.735, rc1 0.759; offline
  hybrid MRR granite 0.843, rc1 0.853. **No measurable gain** (all inside ±0.09); the pilot data's closeness to
  v1's fictional files would have inflated a gain, so the flat result says 1,875 pairs are too few for Granite.
  `training/runs/vane1-rc1/model` stays local (not exported, not published, no default change).
- **Round 9 run log (commands recorded before each run):**
  - Reranker comparison (CPU, done): `docker compose -f training/docker/compose.rocm.yaml run --rm -e
    HIP_VISIBLE_DEVICES= trainer python3 evals/rerankers/bench_rerankers.py run --candidates
    training/runs/rerank-r9/candidates-v1dev.json --bench evals/nai-bench/v1/questions-dev.jsonl --rerank-top 10
    --threads 8 --models "…" --output evals/results/v1-dev-rerankers-r9-2026-11-24.json` (candidates from
    `bench_rerankers.py collect` against the bench stack: image `nai-core:r9-bench` = local build of `2e8e425`,
    volume `nai-bench-v1-granite97-data`, reranker off).
  - Vane 1 rc1 training (GPU, ≤ 3 h): config [`training/configs/vane1-rc1-granite.json`](../training/configs/vane1-rc1-granite.json),
    command = its `command` field (granite 97m, seed 13, 1 epoch, batch 64, lr 2e-5, max length 256, 1 hard
    negative, `--no-export`, `timeout 3h`, log `training/runs/vane1-rc1/train.log`).
- **Updated:** 2026-11-23, round 8 session 2 (keyword-only mode for small NAS boxes, then release 0.7.0). In
  **Round 8 finished:** sections 2 (keyword-only mode) and 3 (release 0.7.0) done; nothing else started.
- **Round 8 permissions (2026-11-23, restated for session 2 the same day):** commit, push, open and merge PRs as the human (merge commits; no attribution,
  no history rewrite, no force-push, never bypass branch protection); create and push **v0.7.0 once** (never move or
  re-push a tag, no other tags); user-space installs; start/stop bench and ROCm trainer containers (GPU runs ≤ 3 h,
  command and config recorded here first); ask before deleting anything except own test containers. Session 2: start/stop the bench containers only; if
  sudo asks for a password, print the command for the human and wait.
- **Round 8 state:** session 2 started at lab/stage-0 = `622de73`, main = `f671c7b`, both pushed, clean.
  HANDOFF split into this page + [HANDOFF-history.md](HANDOFF-history.md) (`730e70e`).
- **Round 8 end state:** PR #11 (templates → 0.7.0) merged as `38c5ddd`, PR CI and main CI (run 45266117359) green.
  main = `38c5ddd`; lab/stage-0 = main plus this HANDOFF-only commit; both pushed. Tag `v0.7.0` → `6a85f52`.
  Merged this round: PR #9 (`1f6d5ba`), #10 (`6a85f52`), #11 (`38c5ddd`).
- **Round 8, section 2 done: keyword-only mode.** PR #9 merged as `1f6d5ba`; PR CI and main CI (run 45260344370,
  incl. nai-bench) green. `NAI_EMBEDDINGS=auto|on|off` (default auto;
  `NAI_EMBEDDINGS_ENABLED=false` = off); `hardware.embeddings_auto_decision` (threshold **2.5 GB** effective memory,
  inclusive); `EmbeddingService.decision()/wanted()` cached per process and used by the service, worker, retriever,
  `/health`, `/system` (`features.embeddings.mode` on/off/auto-on/auto-off + `reason`), startup log; web UI notice for
  auto-off; `/health/detailed` now always returns embedding stats. Tests: `tests/test_keyword_only.py` (2 GB box, 2g,
  3g, 4g, overrides, upgrade from 0.6.0 on 2 GB = keyword-only without prompt and model never loaded, upgrade on 3g =
  ask-before-re-index); conftest pins `NAI_EMBEDDINGS=on` so other tests don't depend on host RAM.
  Measured (`evals/results/simulated-nas-keyword-only-2g-2026-11-23.md`, 2 CPU / 2g, nai-bench v0 corpus): mode
  auto-off, **peak 143 MiB**, **search median 0.002 s** (p95 0.002), indexing 4.0 s. v1 dev keyword-only
  (`evals/results/v1-dev-keyword-only-2026-11-23.md`, PROVISIONAL): **MRR 0.842, Hit@5 0.894**, cross-language
  Hit@5 0.643 (exactly the expected BM25 row). Test image `nai-core:kwonly-local` (local only); new volume
  `nai-bench_nai-nas-sim-r8-2g-data`.
- **Round 8, section 3 done: 0.7.0 published.** Release PR #10 merged as `6a85f52` (version 0.7.0, CHANGELOG
  `[0.7.0] – 2026-11-23`); main CI run 45261589923 green (incl. nai-bench). Local build `nai-core:0.7.0-local` from
  `6a85f52` smoke-tested, then tag **`v0.7.0`** (annotated) on `6a85f52`, pushed once; release.yml run 45263561632
  succeeded; GitHub Release v0.7.0 published; GHCR tags `0.7.0`, `0.7`, `sha-6a85f52`, `latest` (amd64 + arm64).
  Anonymous pull (empty Docker config) of `ghcr.io/nithron/nithronai/nai-core:0.7.0` OK. Smoke tests (2 CPUs,
  auth off, no LLM, two uploaded text files; same script on the local build and the published image, all PASS):
  2g → `auto-off`, keyword question answered (`/ask`, extractive, cites car.txt), search method bm25, ~88 MiB;
  3g → `auto-on` (Granite), semantic-only query (`method=embedding`, "automobile coverage") finds car.txt, ~1.18 GiB;
  `--user 568:568` (no limit) → model downloaded, `auto-on`, semantic-only query OK, 0 permission errors. Test
  containers and data dirs removed. Follow-up PR: NithronOS template here, TrueNAS compose and
  `scripts/truenas-vm/install_app.py` → 0.7.0; hand-over item 3 now says 0.7.0.
- **Next (not started; needs the human's go for GPU runs, this session allowed bench containers only):** Vane 1
  Granite pilot (`vane-1-rc1`). First command: `apps/nai-core/.venv/bin/python training/embed/check_overlap.py
  training/data/vane1-pilot/pairs-clean.jsonl` (must report no nai-bench overlap); the rest of the steps are under
  "Round 6 stopped here" in [HANDOFF-history.md](HANDOFF-history.md).
- **Earlier rounds (1–7):** full status notes and History moved to [HANDOFF-history.md](HANDOFF-history.md)
  (2026-11-23). Round 7 ended with PR #8 merged as `f671c7b` (Granite memory: peak 1 759 MiB reranker off, 3 340 MiB
  forced on). Open lab work, in order: Vane 1 Granite pilot (`vane-1-rc1`), reranker lineage audit, fusion weights,
  Granite quantization; commands under "Round 6 stopped here" in the history file.

## Waiting on the human

- **Reranker lineage audit failed (2026-11-24, [reranker-audit.md](lab/reranker-audit.md)):** both
  `bge-reranker-v2-m3` (shipped) and `Qwen3-Reranker-0.6B` (Loupe 1 teacher) have MS MARCO (non-commercial) in
  their stated training data. Decisions needed:
  1. **Shipped auto-enable (0.6.0, 0.7.0):** on 8+ core / 8+ GB boxes nAI downloads and runs bge-reranker-v2-m3.
     Options: (a) accept and record for the lawyer, as MiniLM was until 0.7.0; (b) make `NAI_RERANKER=auto`
     resolve to off in the next release until a clean reranker exists (explicit `on` keeps working); (c) switch the
     default to a cleaner model. No default was changed.
  2. **Loupe 1:** its planned base and teacher both fail. Proposal: a cross-encoder from a clean encoder (Granite
     R2 multilingual, audited; or mmBERT, MIT) trained on Vane 1's licensed data with `mistral-small3.1` labels,
     instead of distilling from a reranker with MS MARCO in its lineage. Needs your go.
  3. **Closest third-party alternative:** `Horizon-Labs/multilingual-reranker-small` (Apache-2.0, 141M,
     permissive data list, but labels distilled from Qwen3-Reranker-4B): v1 dev MRR 0.886 vs bge 0.896 (tied
     within ±0.09) at half the latency (0.42 s vs 0.81 s per question, 8 cores). Whether "clean data, distilled
     labels" passes is your call.
  4. The int8 ONNX nAI downloads (`onnx-community/bge-reranker-v2-m3-ONNX`) states no license (an automatic
     conversion of Apache-2.0 weights): low risk, but provenance is unverifiable.
  5. Quora question pairs' terms (in bge-reranker's data) could not be read (site 403); check by hand if needed.
- **NithronOS template → 0.7.0:** hand the patch in `docs/KNOWN_ISSUES.md` (items 1–4; item 3 is now the 0.7.0
  version bump, item 4 the memory text with keyword-only below 2.5g) to the session that owns NithronOS.
- **Pushes:** none pending (main and lab/stage-0 pushed; lab/stage-0 is one HANDOFF commit ahead).
- **Licensing direction** for nAI itself (NCL + commercial vs dual license vs open core): not decided.
- **nai-bench review:** all items are unreviewed: v0 56 (`python evals/nai-bench/review.py`), v1 150 (dev 62:
  `review.py --file evals/nai-bench/v1/questions-dev.jsonl`; test 88 needs `--test-split`).
- **Embedding base:** decided in round 6 (Granite R2 97m, the default since 0.7.0). The old MiniLM base is
  replaced; its pilot `vane-1-rc0` stays a learning run. Upstream CC-BY-SA in Granite's lineage (Wikipedia, Stack
  Exchange) is recorded for lawyer review before any commercial deal (decision 2).
- **Hugging Face:** `nithron/vane-1` under Apache-2.0 is a proposal waiting on the human; dataset release open.
- **Trademark search** for Nithron Vane / Loupe / Tern / Nox before any public release.
- **NithronOS template sync:** hand the patch in `docs/KNOWN_ISSUES.md` ("Hand-over: NithronOS template sync";
  applies cleanly to NithronOS `47def8c`) to the session that owns NithronOS.
- **Docker disk (round 8 additions):** images `nai-core:kwonly-local` and `nai-core:0.7.0-local` (local builds,
  ~1.3 GB each), the pulled `ghcr.io/nithron/nithronai/nai-core:0.7.0`, volume `nai-bench_nai-nas-sim-r8-2g-data`.
- **Docker disk:** ~50 GB images (ROCm PyTorch ~40 GB) + ~46 GB build cache, plus the local
  `nai-core:lab-stage-0` (1.3 GB, 2026-11-23) and `nai-core:0.6.0-local` (1.3 GB, the 0.6.0 smoke-test build),
  and the Docker volume `nai-bench_nai-bench-v1-data` (v1 index); prune when not needed (ask first). Added in
  round 5: Ollama models `mistral-small3.1` (15 GB) and `phi4-mini` (2.5 GB) in `nai-bench_ollama-models`, the
  pulled `ghcr.io/nithron/nithronai/nai-core:0.6.0` (1.3 GB), `training/data/vane1-pilot` (19 MB),
  `training/runs/vane1-pilot` (1.8 GB incl. trainer checkpoints), `training/.cache` (0.46 GB, base model). Added in
  round 6: image `nai-core:granite-local` (1.3 GB), volumes `nai-bench_nai-bench-v1-granite97-data`,
  `…-granite311-data` (partial), `nai-bench_nai-nas-sim-r6-minilm-data`, `…-r6-granite97-data`, Granite 97m/311m in
  `training/.cache` (~1.6 GB with the ONNX files) and `training/runs/vet-granite-97m` (~0.5 GB exports). Build venv for nai-bench rendering:
  `~/.venvs/nai-bench-build` (user space).
- **TrueNAS:** adapter and custom app tested on 25.10.8 in a VM (2026-11-23). Still open: the UI menu names
  for certificate import in `packaging/truenas/README.md` (unverified); the guide needs a release after 0.5.0
  (0.5.0 has no adapter and runs keyword-only as the apps user). Release decision is the human's.
- **Reranker ONNX license:** fastembed's int8 bge build comes from `onnx-community/bge-reranker-v2-m3-ONNX`,
  whose card states no license (base model Apache-2.0); fine for now, Loupe 1 ships our own export.
- **UI checks:** CONTRIBUTING.md lists no UI test procedure; the new re-index notice was checked by rendering
  the function in Node only. Decide whether to add a Playwright smoke test.

## Decisions log (newest first)

| Date | Decision | Reason |
|---|---|---|
| 2026-11-24 | **Scale Vane 1's training data** to tens of thousands of pairs or more, from sources that meet the data rules, with `mistral-small3.1` as the teacher for now. | The pilot's 1,875 pairs are far too few for Vane 1. Plan: [vane1-data-plan.md](lab/vane1-data-plan.md). |
| 2026-11-24 | **No AirLLM.** A bigger teacher is evaluated later only with llama.cpp GPU+RAM offload or a rented GPU, and only Apache-2.0 or similarly permissive models; proposed with numbers, no switch without the human's decision. | |
| 2026-11-23 | **Small boxes get keyword-only mode:** where memory can't fit Granite, nAI turns embeddings off and searches with BM25 only (`NAI_EMBEDDINGS=auto|on|off`); no second embedding model, MiniLM is not a fallback. | 2 GB NAS boxes can't fit Granite's 1.8 GB peak; MiniLM's lineage has non-commercial data. |
| 2026-11-23 | **Publish 0.7.0** once keyword-only mode is merged and every check passes. | |
| 2026-11-23 | **Embedding base → IBM `granite-embedding-97m-multilingual-r2`** (Apache-2.0, trained without MS MARCO) if it holds up on nai-bench v1 dev; it becomes Vane 1's base and nAI's default. | The old default's lineage has non-commercial data (audit). |
| 2026-11-23 | **Upstream CC-BY-SA in a base model's lineage is accepted** and recorded in the audit for lawyer review before any commercial deal; data nAI trains on directly stays CC-BY-SA-free. | Most open bases use Wikipedia/StackExchange; non-commercial terms are the hard blocker. |
| 2026-11-23 | **No release in round 6;** a default-model change goes into "Unreleased" for 0.7.0. | |
| 2026-11-23 | **Publish 0.6.0** (tag `v0.6.0` on `06c29e0`). | Prepared and smoke-tested in round 4. |
| 2026-11-23 | **Vane 1 teacher: `mistral-small3.1`** (corpus and query generation); license and quantization in the register. Deliberately not the bench judge (`qwen2.5:7b`). | Separate teacher and judge models avoid a model grading its own style. |
| 2026-11-23 | **Data rule: no CC-BY-SA material in Vane 1's training data**; only public domain, CC0, CC-BY, EU reuse texts and teacher-generated text. | Keeps the model and a dataset release free of share-alike obligations. |
| 2026-11-23 | **Vane 1: pilot now, base-model training-data audit alongside;** no full training run and no public release until the audit passes. | The base model's own training data could restrict commercial use. |
| 2026-11-23 | **Unattended GPU work** allowed in the ROCm container: each run ≤ 3 h, logs to a file, command and config recorded in HANDOFF first. | Lets long runs proceed without supervision, traceably. |
| 2026-11-23 | **No `--final-run` on the v1 test split this round;** dev split only. | Test split stays untouched until items are reviewed. |
| 2026-11-23 | **No Hugging Face publication.** `nithron/vane-1` under Apache-2.0 is a proposal waiting on the human; releasing the training dataset is open. | Release needs the audit, review and a decision. |
| 2026-11-23 | **Loupe 1 after Vane 1.** | One model at a time. |
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

Moved to [HANDOFF-history.md](HANDOFF-history.md) (rounds 1–7).

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
# the rest of CI's lint job (added round 4 after a CI-only mypy failure)
apps/nai-core/.venv/bin/ruff format --config apps/nai-core/pyproject.toml evals training --check
apps/nai-core/.venv/bin/mypy --ignore-missing-imports evals/*.py evals/retrieval/eval_retrieval.py \
    evals/answers/eval_answers.py evals/nai-bench/build_corpus.py evals/nai-bench/review.py evals/rerankers/bench_rerankers.py \
    evals/embeddings/dense_eval.py
(cd training/embed && ../../apps/nai-core/.venv/bin/mypy --ignore-missing-imports common.py check_overlap.py generate_pairs.py train.py \
    fetch_public.py generate_corpus.py select_passages.py)

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
