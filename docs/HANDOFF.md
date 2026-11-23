# Handoff

> Read this first. Any agent (Claude Code, Codex, Kimi Code, …) or person can continue from here without
> the chat history. **Every agent session updates this file before it ends** (see `CONTRIBUTING.md`).
> Keep it short; link to other docs instead of copying them.

## Status now

- **Updated:** 2026-11-23, round 4 (lab work → main, release 0.6.0 prep, v1 dev baseline, difficulty rebalance,
  next-stage plan). **Release 0.5.0 is published; 0.6.0 is being prepared (not tagged).**
- **Round 4 permissions (2026-11-23):** the human authorized this session to commit, push, open and merge PRs as
  them (git identity, SSH key, gh auth already configured); no attribution trailers, no history rewrite, no
  force-push, never bypass branch protection; merge PRs with a merge commit (not squash/rebase). Release
  switch: **STOP BEFORE TAGGING** (no tags this session; never move or re-push a tag). User-space installs
  (sudo commands go to the human). May start/stop the bench containers and the TrueNAS VM. Ask before deleting
  anything (Docker images, build cache, VM files, `~/.venvs/nai-bench-build`). NithronOS repo read-only. Never
  load the nai-bench test split; `--final-run` is the human's decision.
- **Round 4, section 1 done:** PR #3 (lab/stage-0 → main, 19 commits) merged with a merge commit as `3163618`;
  its first CI run failed only on mypy over `training/embed/common.py` (CI type-checks training/embed, the local
  commands didn't), fixed in `41facf4`; PR CI then green. main CI on `3163618` green incl. nai-bench evaluation
  (run 45189836839). main = lab/stage-0 = `3163618` (local and origin) before this close-out.
- **Round 4, section 2 done (release 0.6.0 prepared, NOT tagged):** PR #4 merged as `06c29e0` (CHANGELOG
  `## [0.6.0] – 2026-11-23`, version 0.6.0, TrueNAS guide → `nai-core:0.6.0`); PR CI and main CI (run 45190939370) green.
  Image built from `06c29e0` with `git archive 06c29e0 | docker build -f apps/nai-core/Dockerfile -t
  nai-core:0.6.0-local -`: `/health` reports 0.6.0 (default user `nai`); as `--user 568:568` with a throwaway data
  dir (`HOME=/`) the embedding model downloaded into `/app/data/.cache/huggingface`, NLTK data readable, 0
  permission errors, an embedding-only query with no shared keywords found the right file (the auto reranker
  policy also turned on and loaded on this 32-core host). Test containers removed. Tag commands are under
  "Waiting on the human".
- **Round 4, section 3 done (v1 dev baseline, PROVISIONAL):** `evals/results/v1-dev-baseline-2026-11-23.{md,json}`
  at `22336af` with nai-core 0.6.0 (local build), reranker off, qwen2.5:1.5b, judge qwen2.5:7b, dev split only (43
  items, 0 reviewed). Hybrid MRR 0.714 / Hit@5 0.909; BM25 0.841 / 0.879; embedding 0.557 / 0.606. Cross-language
  (n = 12) hybrid Hit@5 0.750 / MRR 0.596 vs same-language 1.000 / 0.782; embedding cross 0.667 / 0.613. The 0.3
  cutoff emptied no result list on v1 (10 452 chunks); the failure is ranking (books outrank the right document).
  LLM answers correct 0.455, correct refusal 0.30. Fixed on the way: evaluate() used v0's manifest for v1 items
  (`22336af`). Bench stack stopped; v1 index kept in the `nai-bench_nai-bench-v1-data` volume.
- **Round 4 next command:** section 4, 50 more v1 questions (v1-0101…0150: 26 easy, 3 medium, 21 hard → 45/60/45
  of 150), generator in the scratchpad (`…/scratchpad/questions/gen_v1_questions.py 125`, then 150).
- **Branches:** `main` = `lab/stage-0` (fast-forwarded after the release merge), both pushed;
  `lab/stage-0` tracks `origin/lab/stage-0`. Work continues on `lab/stage-0`; push it after each close-out.
- **Push authorization:** on 2026-11-23 the human authorized this session to commit, merge and push as them
  (no force-push). The general rule in CONTRIBUTING.md (agents never push) still stands for other sessions.
- **Done:** round 3 steps 0, 1, 2a–2e, 4; release pushed and verified (see History).
- **TrueNAS VM session (2026-11-23):** the human authorized committing and pushing `lab/stage-0` (no push to
  main, no tags, no branch deletion, no force-push) and user-space installs; ask before deleting anything
  outside `~/vms/truenas-test/`. Checks done: main CI for `c9d3d05` green (run 45142725988); 437 GB free in
  `~`; `/dev/kvm` usable by `nox`; `qemu-system-x86_64` and `qemu-img` installed, `expect` and a VNC client
  not. A second session the same day (2026-11-23) got the same permissions again from the human (commit and
  push `lab/stage-0` as them, no attribution trailers, no history rewrite/force-push, no push to main, no
  tags, no branch deletion; user-space installs; ask before deleting outside the VM directory).
- **nai-bench v1 session (2026-11-23):** the human (from another Claude Code account) authorized this
  session to commit and push `lab/stage-0` as them (no attribution trailers, no history rewrite, no
  force-push, no push to main, no tags, no branch deletion, no image pushed to any registry), user-space
  installs (Python packages, download tools, Playwright browsers; sudo commands go to the human), and
  starting/configuring/stopping the TrueNAS test VM; ask before deleting anything.
  NithronOS repo read-only. Part 2 (TrueNAS custom-app test) only if step 3 finishes with room to spare.
- **TrueNAS VM test: done (2026-11-23, session 2).** TrueNAS Community Edition **25.10.8** (current stable;
  27.0.0 is RC), ISO SHA-256 `af5c8cea…f419d7bc` matched the `.sha256` file and the download page. Installed
  headless over the serial console; configured and tested with `scripts/truenas-vm/` (README there has every
  command). All 8 adapter checks pass by host name and by IP with only the read-only key (results table in
  `packaging/truenas/README.md`). Adapter fixes: errors show `error.data.reason`; no deprecated websockets
  `connect()`; fixtures recorded from 25.10.8. Findings: the default cert names only `localhost` and 25.10
  can't create CAs, so real installs import their own certificate; certificates need key identifiers for
  Python 3.13+ strict verification (`make-cert.sh` adds them). **VM is shut down, files kept** in
  `~/vms/truenas-test/` (9.6 GB after the custom-app test, was 5.9 GB); secrets in
  `~/vms/truenas-test/secrets.env` (mode 600: TrueNAS admin password, `nai-reader` API key, nAI admin
  password); CA in `pki/`, SSH key for the VM in `ssh/`. Restart:
  `scripts/truenas-vm/start-vm.sh`, API on `https://localhost:8443` after ~3 min. `lab/stage-0` has no CI
  (CI runs on main/develop and PRs only); local checks passed before every commit.
- **Step 3, nai-bench v1: first round done (2026-11-23).** All five bullets below are done: split guard,
  training guard, review.py for short sessions, 100 corpus files, 100 questions (dev 43 / test 57, all
  unreviewed). **Next command:** part 2 of this session, the TrueNAS custom-app test ("Next 2" below), or, in a
  later round, v1 to 300+ files / 625 questions (more easy and hard items; ≥ 5 questions per cross-lingual
  language pair).
  1. **Split rules (done):** rules in `evals/nai-bench/README.md` ("Dev/test split"); `naibench.split_of`,
     guard in `load_items`/`load_all_items`, `--final-run` + `--label` in `eval_retrieval.py`,
     `eval_answers.py`, `run_baseline.py` (+ `--bench`), `review.py --test-split`, ledger
     `evals/results/test-ledger.jsonl` (created on the first final run), `naibench.validate_splits`; tests in
     `evals/tests/test_splits.py` (fail when the guard is disabled). Original requirement: v1 lives in `evals/nai-bench/v1/`: `questions-dev.jsonl` and
     `questions-test.jsonl` (separate files) plus its own corpus and manifest. Split by hash, never by hand:
     `sha256(item_id)` mod 100 < 40 → dev, else test (V1_PLAN.md: 40/60). Every loader (`naibench.load_items`
     and the eval scripts) refuses the test file unless called with an explicit `--final-run` flag, and each
     final run appends a line (date, commit, label, item count, dataset hash) to
     `evals/results/test-ledger.jsonl`. Add a test that `eval_retrieval`/`eval_answers`/`run_baseline` can't
     load test items without the flag. v0 (`evals/nai-bench/questions.jsonl`) stays as the frozen smoke set.
  2. **Training guard (done):** `common.read_training_rows` (used by `generate_pairs.py` and `train.py`)
     refuses nai-bench paths, `use: eval-only` rows, forbidden authors (incl. `provenance.model`) and rows
     with nai-bench item fields; tests in `training/tests/test_guards.py` (8 fail with the check disabled).
     Original requirement: `training/embed/check_overlap.py` already rejects nai-bench text; also make
     `training/embed/common.py` refuse any input row whose provenance says `use: eval-only` or a Claude
     author, with a test (only `train.py` checks this today).
  3. **review.py for short sessions (done):** progress line per item, q / Ctrl+C / Ctrl+D stop cleanly,
     position in `~/.cache/nai-bench/review-state.json` (resume after the last item; skips come back last),
     one-line summary, v1 excerpts from text corpus files; tests in `evals/tests/test_review.py`.
     Original requirement: show progress ("23/100 reviewed"), `q`/Ctrl+C keep all decisions,
     resume at the first unreviewed item, one-line summary at the end; tests for save and resume.
  4. **Corpus (done, 100/100):** batch 4 = 15 fictional + 10 scans/photos (all 10 OCR-checked in
     `nai-core:lab-baseline` with eng+deu). Totals: fictional 45 (CC-BY-4.0, Claude, eval-only), EU 20,
     DE/SE/US official texts 20, Gutenberg 15; en 30, de 21, sv 18, fr 16, pt 15; 17 MB. Batch 3 = 5 Gutenberg books (2 fr, 3 pt) + 20 fictional files (`v1/corpus-src/`,
     built by `build_corpus.py --root evals/nai-bench/v1`, which merges with the downloaded entries).
     Earlier: batch 2 = 15 FTC/CPSC rules from 16 CFR (govinfo PDFs; consumer.ftc.gov blocks
     curl) and 10 Gutenberg books (3 en, 3 de, 3 sv, 1 fr; gutenberg.org 503s, pglaf mirror works); 14 MB.
     `v1/fetch_corpus.py` + `v1/sources.json` + `v1/corpus-manifest.json`; batch 1 =
     4 EU acts × 5 languages (2011/83, 2019/771, 2023/988, 2017/1369; XHTML from the Publications Office
     CELLAR API because EUR-Lex blocks curl), 3 German regulations (HeizkostenV, BetrKV, WoFlV), 2 Swedish
     statutes (konsumentköplag, konsumenttjänstlag); 6.2 MB. Tests: `evals/tests/test_v1_corpus.py`.
     Original requirement: first 100 v1 files per V1_PLAN.md (EUR-Lex in 5 languages, DE/SE statutes, US federal
     publications, Gutenberg distractors, fictional docs); download with `curl`, record source URL, license,
     retrieval date, author and SHA-256 per file in the v1 manifest; Claude-written files say so and are
     eval-only. Close out every 25 files.
  5. **Questions (done, 100/100):** plan for the first 100 = per language 4 lookup, 4 cross-lingual (each question
     language paired once with each other document language), 4 table/scan-OCR, 4 multi-hop, 4 unanswerable
     (near misses); ids `v1-0001…`, split by `naibench.split_of` into `v1/questions-dev.jsonl` /
     `v1/questions-test.jsonl`; all `unreviewed`, `provenance.author: claude`, `written_by: Claude-written`,
     `use: eval-only`. EU-act questions list all five language versions as gold (each answers it), so EU acts
     are never used for cross-lingual items. Law facts were checked against the stored texts (HeizkostenV
     § 7, BetrKV § 1(2), WoFlV § 4, 2011/83 Art. 9, 2019/771 Art. 10, konsumentköplag 3:17, konsumenttjänstlag
     17 §, 16 CFR 429 and 435). Batch 1 = v1-0001…0025 (20 German, 5 English). Batch 4 = v1-0076…0100 (5 French, 20 Portuguese). Batch 3 = v1-0051…0075 (10 Swedish, 15 French). Batch 2 = v1-0026…0050 (15 English, 10 Swedish).
     Original requirement: first 100 v1 questions spread over the 4 categories × 5 languages (+ unanswerable), all
     `review_status: unreviewed`, `provenance.author: claude` ("Claude-written"), `use: eval-only`;
     validate with `naibench.validate`. Close out every 25 questions.
- **TrueNAS custom-app test: done (2026-11-23).** nAI built from `lab/stage-0` (local image
  `nai-core:lab-stage-0`, loaded with `docker save | ssh … sudo docker load`, no registry) installed with
  `packaging/truenas/compose.yaml` via `app.create` (`scripts/truenas-vm/install_app.py`); `test_app.py`: all 6
  checks pass (runs as 568, datasets read-only, semantic search on, discovery connected from inside the app over
  `wss://10.0.2.15` with the read-only key + CA file, 4 documents indexed, 2 extractive answers from the right
  files, key not in the app log). **Fixed:** the image didn't work as another uid (HF cache in `/.cache`, NLTK
  data in private `/home/nai` → keyword search only): `HF_HOME=/app/data/.cache/huggingface`, NLTK in
  `/opt/nltk_data` (`tests/test_dockerfile.py`, CHANGELOG). Guide fixes in `packaging/truenas/` (Apps pool first,
  TrueNAS IP not localhost in the URL, cert must name it, 0.5.0 too old). Not verified: the certificate-import UI
  menu names (a headless browser would need the admin password in tool calls; left marked unverified). VM shut
  down, files kept; the app `nai` stays installed in the VM. **Next command:** a later round: release a version
  after 0.5.0 so the TrueNAS guide can point at a published image, then re-run step 8 of
  `scripts/truenas-vm/README.md` with it.
- **After round 3:** human review of nai-bench items; finish v1 (to 300+ files, 625 questions);
  synthetic corpus generator for Stage 1; Vane 1 / Loupe 1 pilot training on the GPU.

## Waiting on the human

- **Tag v0.6.0 (release switch was STOP BEFORE TAGGING):** main is at `06c29e0` with CI green. To publish:
  `git fetch origin && git tag -a v0.6.0 06c29e0 -m "nAI 0.6.0" && git push origin v0.6.0`, then watch
  release.yml (`gh run list --workflow release.yml --limit 1`), check an anonymous
  `docker pull ghcr.io/nithron/nithronai/nai-core:0.6.0`, repeat the `--user 568:568` smoke test on it, and do
  docs/RELEASING.md step 5 (NithronOS template → 0.6.0, here and in the NithronOS repo copy).
- **Pushes:** none pending (main = lab/stage-0 pushed).
- **Licensing direction** for nAI itself (NCL + commercial vs dual license vs open core): not decided.
- **nai-bench review:** all items are unreviewed: v0 56 (`python evals/nai-bench/review.py`), v1 100
  (`--file evals/nai-bench/v1/questions-dev.jsonl`; the test split needs `--test-split`).
- **Trademark search** for Nithron Vane / Loupe / Tern / Nox before any public release.
- **NithronOS template sync:** hand the patch in `docs/KNOWN_ISSUES.md` ("Hand-over: NithronOS template sync";
  applies cleanly to NithronOS `47def8c`) to the session that owns NithronOS.
- **Docker disk:** ~50 GB images (ROCm PyTorch ~40 GB) + ~46 GB build cache, plus the local
  `nai-core:lab-stage-0` (1.3 GB, 2026-11-23); prune when not needed. Build venv for nai-bench rendering:
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
- **nai-bench v1 + TrueNAS custom app (2026-11-23, session 3):** split guard `80378af`, training guard `ca4c908`,
  review.py `1532ba4`, v1 corpus `8a6c422` `b34437d` `71957a7` `ece720b` (100 files), v1 questions `139ad72`
  `36a7c5f` `2df48de` `408b309` (100), docs `30ceecf`, then the custom-app close-out commit (image any-user fix,
  guide fixes, `install_app.py`, `test_app.py`). Tests: 218 nai-core, 105 evals/training.
- **TrueNAS VM test (2026-11-23, session 2):** TrueNAS 25.10.8 in a QEMU/KVM VM; commits `e96e35d` (setup
  scripts), `19a2894` (adapter fixes, README results), then the certificate/HANDOFF close-out commit. Tests:
  216 nai-core, 66 evals/training.
- **Round 3 wrap-up (2026-11-23):** merged `origin/main` (PRs #1, #2) into `main` as `ae7cadc` (clean, LICENSE
  `62f2cf4c…`), CI green; pushed tag `v0.5.0` (`d496d16`): release.yml run `45140589825` succeeded; GHCR now
  has `0.5.0`, `0.5`, `sha-d496d16` and moved `latest`, `0`; anonymous pull + `/health` smoke test reported
  version 0.5.0. Merged `lab/stage-0` into `main` (`d307abf`), CI green (all 6 jobs incl. nai-bench with
  Tesseract); pushed `lab/stage-0` (tracking). Deleted merged remote branches `phase1-ask-your-nas`,
  `chore/ncl-add-nithro`, `license-niro` and the local `chore/ncl-add-nithro`.
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
# the rest of CI's lint job (added round 4 after a CI-only mypy failure)
apps/nai-core/.venv/bin/ruff format --config apps/nai-core/pyproject.toml evals training --check
apps/nai-core/.venv/bin/mypy --ignore-missing-imports evals/*.py evals/retrieval/eval_retrieval.py \
    evals/answers/eval_answers.py evals/nai-bench/build_corpus.py evals/nai-bench/review.py evals/rerankers/bench_rerankers.py
(cd training/embed && ../../apps/nai-core/.venv/bin/mypy --ignore-missing-imports common.py check_overlap.py generate_pairs.py train.py)

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
