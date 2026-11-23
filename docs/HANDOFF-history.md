# Handoff history

> Older status notes and History entries moved out of [HANDOFF.md](HANDOFF.md) on 2026-11-23 to keep it a
> short status page. Newest first within each section. Nothing here is current unless HANDOFF.md points to it.

## Status notes, rounds 1–7

     poll release.yml, anonymous pull + repeat, hand-over patch bump.
- **Round 7 permissions (2026-11-23):** commit, push, open and merge PRs as the human (merge commits; no attribution,
  no history rewrite, no force-push, never bypass branch protection); **no tags**; delete the three empty
  `v1-dev-*.err` files (done); ask before deleting anything else; user-space installs and model downloads; start/stop
  bench and ROCm trainer containers; unattended GPU runs ≤ 3 h with command and config recorded here first.
- **Round 7, section 1 done: Granite memory** (`evals/results/simulated-nas-granite97-rerank-{off,on}-2026-11-23.*`,
  2 CPU / 4 GB, v0 corpus): reranker off: peak **1 759 MiB** (indexing), 1 625 idle/search, search median 0.20 s;
  reranker forced on: peak **3 340 MiB** (search), search median **20.3 s**. Templates unchanged (NithronOS 3g with
  reranking off by default; TrueNAS 4g where `auto` stays off below 8 GB); texts updated (README memory note,
  NithronOS `MEMORY_LIMIT` description, TrueNAS README, KNOWN_ISSUES hand-over item 4, CHANGELOG). Minimum 3g /
  4 GB NAS, recommended 8 GB; forcing the reranker on needs 5g.
- **Round 7 end state:** PR #8 merged as `f671c7b`, main CI green (run 45243889687); main = `f671c7b`, lab/stage-0 = main
  plus this HANDOFF-only commit, both pushed.
- **Round 7 stopped after section 1 (context budget).** Next, in order: section 2 (Vane 1 Granite pilot, commands
  under "Round 6 stopped here"), section 3 (reranker audit, same place), then 4 (fusion weights) and 5 (Granite
  quantization) from the round-7 prompt. The first command: re-run `check_overlap.py` on
  `training/data/vane1-pilot/pairs-clean.jsonl`.
- **Round 6 permissions (2026-11-23):** commit, push, open and merge PRs as the human (merge commits; no attribution
  trailers, no history rewrite, no force-push, never bypass branch protection); **no tags**; user-space installs,
  Hugging Face and Ollama downloads (sudo → the human); start/stop the bench and ROCm trainer containers; unattended
  GPU runs ≤ 3 h with command and config recorded here first; ask before deleting anything (images, volumes, Ollama
  models, HF caches, training runs). NithronOS read-only; never load the test split; v1 dev only, PROVISIONAL.
- **Round 6 start checks:** lab/stage-0 = `d59dfac`, in sync. Three empty untracked files `v1-dev-*.err` in the repo
  root are stderr logs from round 5's baseline script (not deleted; ask). The "background agent" of round 5 was a
  background **fork of the round-5 session itself**, started from the CLI at 16:04 ("Started in the background: if I
  would choose the best model, even if my gpu …"), i.e. a side question typed into that session; no hook, cron job,
  systemd timer or daemon worker launches agents (repo hooks are graphify guards only; `~/.claude/settings.json` has
  no hooks; daemon 0 workers; no crontab binary; 0 user timers). Nothing changed.
- **Round 6, section 1 done: Granite R2 vetted.** Apache-2.0, ModernBERT built into transformers (no
  trust_remote_code), 384-d (97m) / 768-d (311m), **CLS pooling, no prefixes**, max length 32 768, de/en/fr/pt/sv in
  the 52 enhanced languages. Audit section added to `docs/lab/vane1-base-model-audit.md`: **passes** (MS MARCO
  excluded per the R2 paper; upstream Wikipedia/Stack Exchange CC-BY-SA recorded under decision 2). ONNX:
  `training/embed/vet_onnx.py` (export like Vane 1 + fastembed custom-model parity, CLS): fp32 1.0000, int8 0.9723
  (below the 0.99 bar: nAI should load fp32, 390 MB); our export equals IBM's ONNX files; fastembed loads it via
  `add_custom_model` (CLS). `verify_fastembed` now takes pooling and model file.
- **Round 6, section 2 done: granite 97m meets the switch criteria** (`evals/results/v1-dev-granite-2026-11-23.md`,
  PROVISIONAL, v1 dev): hybrid MRR 0.720 → 0.834, Hit@5 0.894 → 0.915; cross-language hybrid Hit@5 0.714 → 0.714,
  embedding-only 0.643 → 0.786; every language equal or better (sv MRR 0.58 → 0.76); offline embedding-only MRR
  0.444 → 0.854 (311m 0.938; the old pilot 0.613). NAS 2 CPU/4 GB: search 0.30 → 0.20 s median, RAM idle 812 →
  1 444 MiB, indexing 36 → 65 s for 27 files. nAI registers Granite as a custom fastembed model (CLS, fp32 ONNX);
  bench compose takes `NAI_EMBEDDINGS_MODEL`, per-model volumes; nas-sim overlay `NAS_SIM_DATA`. 311m hybrid in nAI
  stopped (CPU too slow, ~1.5 h); measured offline instead.
- **Round 6, section 3 done: granite 97m is nAI's default embedding model** (Unreleased → 0.7.0, no release): PR #7
  merged as `d824cb8`; PR CI and main CI (run 45235492227, incl. nai-bench with Granite) green. Upgrade from the old
  default keeps the old vectors and asks before re-indexing (`test_upgrade_from_the_old_default_model_asks_before_reindexing`).
- **Round 6 stopped here (context budget).** Sections 4 and 5 not started. Next commands, in order:
  - **4. Vane 1 pilot on Granite (`vane-1-rc1`):** re-check the reused dataset first:
    `apps/nai-core/.venv/bin/python training/embed/check_overlap.py training/data/vane1-pilot/pairs-clean.jsonl` (all
    nai-bench) and the training guard (`select_passages.read_training_rows` / `train.load_pairs`); copy
    `training/configs/vane1-pilot.json` to `training/configs/vane1-rc1-granite.json` with `--base-model
    ibm-granite/granite-embedding-97m-multilingual-r2 --release vane-1-rc1 --output-dir training/runs/vane1-rc1`
    (same seed 13, epochs 1, batch 64, lr 2e-5, max length 256, one hard negative, `--no-export`); record the command
    here, run it in the ROCm container with `timeout 3h` and a log file; then `dense_eval.py rank --model
    training/runs/vane1-rc1/model --name rc1` and `dense_eval.py score --names base,granite97,granite311,pilot,rc1`
    (rankings for base/granite97/granite311/pilot already exist in `training/runs/vane1-pilot/eval`). Note: the
    synthetic pilot documents are stylistically close to v1's fictional files, so a gain may be partly domain fit;
    plain granite 97m already reaches embedding-only MRR 0.854 offline, so the headroom is small.
  - **5. Reranker lineage audit:** `BAAI/bge-reranker-v2-m3` (and its int8 ONNX source) and `Qwen/Qwen3-Reranker-0.6B`
    (Loupe 1 teacher): model cards + papers, datasets and licenses, verdict per model, a section in
    `docs/lab/vane1-base-model-audit.md` (or a new reranker audit doc); if non-commercial data shows up, look for a
    clean multilingual alternative and test it with the reranker-on setup (`NAI_RERANKER=true NAI_RERANKER_MODEL=…`).
    Don't change nAI's reranker defaults.
- **Round 5 permissions (2026-11-23):** commit, push, open and merge PRs as the human (merge commits; no
  attribution trailers, no history rewrite, no force-push, never bypass branch protection); create and push the
  tag **v0.6.0 once** (never move/re-push a tag, no other tags); user-space installs, pulling Ollama models and
  Docker images (sudo → the human); start/stop the bench containers, the ROCm trainer container and the TrueNAS
  VM; ask before deleting anything (images, volumes, build cache, VM files, venvs). NithronOS read-only. Never
  load the nai-bench test split; no `--final-run` this round.
- **Round 5, section 1 done: 0.6.0 published.** Tag `v0.6.0` (annotated) on `06c29e0`, pushed once; release.yml
  run 45207761865 succeeded; GitHub Release v0.6.0 published; GHCR tags `0.6.0`, `0.6`, `sha-06c29e0` (plus the
  floating tags). Anonymous pull (empty Docker config) of `ghcr.io/nithron/nithronai/nai-core:0.6.0`: `/health`
  0.6.0; as `--user 568:568` with a throwaway data dir the embedding model downloaded, NLTK readable, 0
  permission errors, semantic-only query found the right file; test containers and data removed. NithronOS
  template here bumped to 0.6.0 (default + enum + catalog); the NithronOS-repo change is item 3 of the hand-over
  in `docs/KNOWN_ISSUES.md`.
- **Round 5, section 3 done: base-model audit** in `docs/lab/vane1-base-model-audit.md`. Verdict **needs the
  human's decision**: the base model is Apache-2.0, but its teacher (`paraphrase-MiniLM-L12-v2`) was trained on MS
  MARCO ("non-commercial research purposes only") and Flickr30k captions ("non-commercial research and/or
  educational purposes"), both verified on their primary pages, plus CC-BY-SA data (SNLI, Stack Exchange,
  WikiAtomicEdits, Wikipedia-derived sets, WikiMatrix) and TED2020 (TED usage policy). It applies to nAI's shipped
  default model too. Until decided: the pilot runs for learning, **nothing from it can ship**. Register updated
  (teacher `mistral-small3.1` approved, Q4_K_M; `phi4-mini` bench LLM; no-CC-BY-SA data rule; audit link).
- **Round 5, section 2 done: Stage 0 baselines on v1 dev (62 items, PROVISIONAL):**
  `evals/results/v1-dev-stage0-2026-11-23.md` (+ run files `v1-dev-baseline-r5`, `v1-dev-rerank`,
  `v1-dev-phi4-mini`). Hybrid MRR 0.720 → **0.911 with the reranker** (Hit@5 0.894 → 0.936; cross-language Hit@5
  0.714 → 0.786). Answers: phi4-mini correct 0.596 / refusal 0.533 / judge 0.790 vs qwen2.5:1.5b 0.489 / 0.267 /
  0.629; phi4-mini's language match is lower (0.541 vs 0.627).
- **Round 5, section 4.1 done: Vane 1 pilot dataset** (`training/data/vane1-pilot`, git-ignored, 18.9 MB, 126 files;
  manifest with checksums `training/manifests/vane1-pilot.json`): 16 public files (EU acts 2016/679 + 2019/770 in
  five languages, ProdHaftG, PAngV, two Swedish statutes, 16 CFR 303 and 1201; licenses EU reuse / public domain) and
  100 synthetic documents by mistral-small3.1 (CC0). 581 selected passages → overlap check → 570; 1 878 pairs (27 min
  of teacher time; 39 language-mismatched queries dropped) → overlap check → **1 875 pairs**, 46 % cross-language,
  queries en 506 / de 362 / sv 339 / pt 350 / fr 318. Training guard passes on passages and pairs. No CC-BY-SA.
- **Round 5, sections 4.2–4.3 done: Vane 1 pilot `vane-1-rc0`** (label rc0 = pilot; the naming rules only accept
  `vane-1[-rcN]`): command and config in `training/configs/vane1-pilot.json`; 24 steps, **20 s**, exit 0; checkpoint
  `training/runs/vane1-pilot/model` (466 MB, git-ignored, no ONNX export). v1 dev, embedding-only, offline harness
  (`evals/results/vane1-pilot-dev-2026-11-23.md`, PROVISIONAL): overall MRR 0.444 → **0.613**, Hit@5 0.532 →
  **0.766**; cross-language MRR 0.435 → **0.676**, Hit@5 0.571 → **0.857**; every category and language improves.
  **Nothing from it can ship** until the base-model audit is decided. (The first attempt with `--release
  vane-1-pilot` was refused by the naming check before training; rerun as rc0.)
- **Round 5 end state:** PR #6 merged as `bd987dc`, main CI green (run 45222520816). main = `bd987dc`; lab/stage-0 =
  main plus this HANDOFF-only commit, both pushed. Bench stack stopped (v1 index and Ollama models kept).
- **Round 5 next command:** none; next round starts with the human's decision on the base-model audit (then, if
  accepted: several pilot seeds, a larger corpus, ONNX export and a hybrid run in nAI on the dev split).
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
- **Round 4, section 4 done:** v1 questions 150 (v1-0101…0150 added, 10 per language, 2 per category per language):
  difficulty now 45 easy / 60 medium / 45 hard = 30/40/30 (was 19/57/24 of 100); dev 62 / test 88; all
  unreviewed, Claude-written, eval-only. Corpus unchanged at 100 files (the new items use files that had few or
  no questions; max 5 per file). The v1 dev baseline above was run on the first 43 dev items, before this batch.
- **Round 4, section 5 done: next-stage plan (written 2026-11-23; nothing started, no training run).**
- **Next stage plan: finish Stage 0's exit criteria in parallel with Stage 1 / Vane 1.** Full design:
  `docs/lab/stage1-embedding-finetune.md`; this is the order of work and what changed with the v1 numbers.
  - *Why Vane 1 first:* on the v1 dev split embedding search is the weak link (Hit@5 0.606 vs BM25 0.879) and
    cross-language questions trail (hybrid Hit@5 0.750 vs 1.000 same-language). The 0.3 cutoff is not the v1
    failure (no empty result lists); ranking is: long distractors (books, EU acts) outrank short household
    documents, also across languages. Vane 1 = fine-tune of `paraphrase-multilingual-MiniLM-L12-v2` (Apache-2.0,
    same 384-d drop-in, re-embed only).
  - *Training data and the data rules:* (1) a **synthetic NAS-like corpus** written by an approved open-weight
    teacher (`qwen2.5:7b` Apache-2.0, register "approved"; `qwen3:14b` if quality is low): fictional household /
    small-office documents in de/en/sv/fr/pt from a seed list of document types × countries × topics, including
    long noisy files and rendered scans OCR'd by nAI's own extractor; no user NAS data (rule 1), no Claude text
    (rule 3; `common.read_training_rows` refuses it). (2) **Public permissive texts not in nai-bench**: other
    EUR-Lex acts (reuse with attribution), German/Swedish statutes, US federal texts; each source gets a register
    row first (rule 2); `check_overlap.py` rejects anything overlapping nai-bench v0/v1 (the v1 corpus files are
    excluded by path and by 8-gram overlap). (3) **Queries** from the same teacher, 3–4 per passage, at least one
    cross-language, with the round-trip filter and a 200-pair spot check per language. Target 30–50k passages,
    100–150k pairs; every row `use: training` with teacher/passage author and license.
  - *ROCm trainer steps (AMD RX 7900 XTX):* `docker compose -f training/docker/compose.rocm.yaml build` → `run --rm
    trainer python3 training/docker/gpu_check.py` → corpus generation via Ollama (bench stack) → `make_passages.py`
    → `generate_pairs.py --resume` (pilot with `--limit 500` first) → `check_overlap.py --write-clean` →
    `train.py --dry-run` → `train.py` (1 epoch, lr 2e-5, batch 64 / cached loss 256, max length 256, bf16, seed 13,
    mined hard negatives excluding the positive's own file) → ONNX + int8 export with the fastembed parity check
    (min cosine ≥ 0.99) → `chown` the outputs back.
  - *Evaluation on the v1 dev split only:* small nAI change first: register a custom fastembed model behind
    `NAI_EMBEDDINGS_MODEL` (stage-1 doc §6). Then the bench stack with a separate data volume per model and
    `run_baseline.py --bench evals/nai-bench/v1/questions-dev.jsonl --methods bm25,embedding,hybrid` for the base
    model and each candidate (same judge, reranker off, then on). Compare embedding-only and hybrid MRR/Hit@5
    overall, per category, per language and cross-language vs same-language; add the planned bootstrap 95 %
    interval to `run_baseline.py`. Overfitting guard: stop if any dev category drops > 0.02 or same-language
    lookup drops. The release claim needs the **reviewed test split** with `--final-run`, which is the human's
    call; until then everything is a dev number.
  - *Stage 0 exit work alongside:* human review of v1 (150 items), v1 to ≥ 300 files / ≥ 300 questions (the
    plan's 625 later), baselines on v1 for hybrid + reranker and a second small LLM, and a one-command
    reproducible baseline.
- **Decisions needed from the human for Stage 1:** (1) approve `qwen2.5:7b` as the corpus and query teacher (or
  pick `qwen3:14b` / `mistral-small3.1`); (2) approve the public text sources for training (EUR-Lex beyond the
  bench acts, statutes, US federal texts) and whether CC-BY-SA material (e.g. Wikipedia) may be used for
  training at all (nai-bench excludes it); (3) accept training before the base-model training-data audit (MS
  MARCO-style terms) or audit first; the audit is required before any public release; (4) GPU time budget
  (pilot ~1 h, full run a few hours of generation plus < 1 h training) and permission to run the trainer and the
  bench stack unattended; (5) when to review v1 and how many `--final-run`s on the test split a model may have
  (each is logged in `evals/results/test-ledger.jsonl`); (6) Hugging Face org/name and license for the Vane 1
  release (`nithron/vane-1`, Apache-2.0 proposed) and whether the training dataset is released too; (7) Loupe 1
  in parallel or after Vane 1.
- **Round 4 end state:** PR #5 (sections 3–5) merged as `7a2d6d1`, main CI green (run 45193463920). main = `7a2d6d1`;
  lab/stage-0 = main plus this HANDOFF-only commit, both pushed. v0.6.0 is **not tagged**: the tag goes on
  `06c29e0` (the commit that was built and smoke-tested; see "Waiting on the human").
- **Round 4 next command:** none in this session; next round starts with the human's Stage 1 decisions above
  (and the v0.6.0 tag if wanted).
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

## History (rounds 1–3)

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
- **Round 8 (2026-11-23):** decisions and permissions recorded, implementation plan written; no code changed (context).
- **Round 7 (2026-11-23):** `.err` files deleted; Granite peak-RAM measurements and memory docs `5a982ef`, PR #8 merge `f671c7b`;
  sections 2–5 not started (context).
- **Round 6 (2026-11-23):** permissions/decisions + Granite vetting `ef1f971`; Granite vs MiniLM on v1 dev + NAS `7dd7a0e`;
  default switch `9d0f72d`, PR #7 merge `d824cb8`; closing HANDOFF commit. Sections 4–5 not started (context).
  Tests: 221 nai-core, 119 evals/training.
- **Round 5 (2026-11-23):** permissions/decisions `0c941ad`; **v0.6.0 tagged on `06c29e0` and published** (release
  run 45207761865); NithronOS template 0.6.0 `bbd8155`; audit `4966ff0`; Stage 0 baselines `5877b1b`; pilot tooling
  `a5970c5`; pilot dataset `e65d5c2`; pilot results `2a144c2`, PR #6 merge `bd987dc`, then this closing HANDOFF commit. Tests: 218 nai-core, 119
  evals/training.
- **Round 4 (2026-11-23):** PR #3 (lab/stage-0 → main, merge `3163618`; CI fix `41facf4`), PR #4 (0.6.0 prep, merge
  `06c29e0`), HANDOFF `3065eda`, v1 baseline tooling `22336af`, v1 dev baseline `09f6cd1`, v1 questions 125
  `3344685` and 150 `7f146be`, plan `b560d2b`, PR #5 merge `7a2d6d1`, then this closing HANDOFF commit. 0.6.0 smoke-tested from `06c29e0` (incl. `--user
  568:568`), **not tagged** (release switch). Tests: 218 nai-core, 106 evals/training.
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
