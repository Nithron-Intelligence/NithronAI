# Changelog

All notable changes to nAI. Versions follow [semantic versioning](https://semver.org/); dates are release
(tag) dates. How to cut a release: [docs/RELEASING.md](docs/RELEASING.md).

## [Unreleased]

### Added
- **nOS template: share access through `nos-app-nai`.** The container joins the group nOS passes as
  `NOS_APP_GID`, so it reads exactly the shares the admin opened to nAI (read-only; needs nOS phase 5). Without
  the variable it falls back to GID 1000, the current PGID, so older nOS behaves as before.

### Changed
- **`NAI_RERANKER=auto` no longer turns the reranker on by itself.** The lineage audit found MS MARCO
  (non-commercial) in the training data of `bge-reranker-v2-m3`, the default model, and of Qwen3-Reranker; the
  same reason MiniLM stopped being the default embedding model in 0.7.0. `auto` now also needs a model whose
  training data is cleared (none yet), so it means off on every machine; `NAI_RERANKER=on` still runs any model,
  and `/system` says why. On v1 dev (PROVISIONAL) reranking added MRR 0.834 → 0.896, within the ±0.09 noise
  band. Only fast machines (8+ cores, 8+ GB RAM) ran it by default; NAS templates already ship `off`.
- **Project and repository renamed to nAI:** the GitHub repository moved to `Nithron-Intelligence` (2026-11-24) and is
  now `Nithron-Intelligence/nAI` (2026-11-26; old URLs redirect). The license texts (EULA, commercial terms,
  trademark policy, NOTICE) name the product nAI. Releases from 0.8.0 publish to
  `ghcr.io/nithron-intelligence/nai/nai-core`; 0.4.0–0.7.0 stay at `ghcr.io/nithron/nithronai/nai-core`.

## [0.7.0] – 2026-11-23

A new default embedding model without non-commercial data in its lineage (IBM Granite Embedding R2), and a
keyword-only mode so small NAS boxes keep working.

### Added
- **Keyword-only mode for small boxes:** `NAI_EMBEDDINGS=auto|on|off` (default `auto`). Below 2.5 GB of effective
  memory (container limit, capped by the NAS's RAM) nAI doesn't load the embedding model and searches with keywords
  (BM25) only: ~150 MB RAM at a 2g limit, search ~2 ms on the nai-bench corpus. On nai-bench v1 dev (PROVISIONAL)
  keyword-only scores MRR 0.842 / Hit@5 0.894 (hybrid with Granite 0.834 / 0.915); questions in another language
  than the file drop to Hit@5 0.643 (0.714). The system panel says why and how to turn semantic search on;
  `/system` reports `features.embeddings.mode` (`on`, `off`, `auto-on`, `auto-off`) and `reason`. Upgrading a
  2 GB box from 0.6.0 keeps the old vectors and shows no re-index prompt. `NAI_EMBEDDINGS_ENABLED=false` still
  turns semantic search off everywhere.

### Changed
- **New default embedding model: `ibm-granite/granite-embedding-97m-multilingual-r2`** (IBM Granite Embedding R2, Apache-2.0, trained without MS MARCO or other
  non-commercial data). The old default, `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, was distilled from a teacher trained on
  non-commercial data. On nai-bench v1 dev (PROVISIONAL) hybrid MRR rises from
  0.720 to 0.834 and every language holds or improves (Swedish most); on a 2-CPU / 4-GB NAS profile search gets
  faster (0.2 s) at about 0.6 GB more RAM and slower indexing. nAI loads it as a custom fastembed ONNX model (CLS
  pooling, no prefix, fp32).
- **One-time re-index on upgrade:** existing indexes were built with the old model. nAI keeps the old vectors, pauses
  semantic search (keyword search keeps working) and asks an admin to start re-indexing; with
  `NAI_EMBEDDINGS_AUTO_REINDEX=true` it re-embeds without asking. To stay on the old model, set
  `NAI_EMBEDDINGS_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`.
- **Higher RAM need:** with the new model nai-core peaks at about 1.8 GB (was about 1.0 GB) on a 2-CPU / 4-GB NAS
  profile, about 3.3 GB with the reranker forced on. Minimum: 3g container limit, 4 GB NAS RAM; recommended 8 GB.
  The shipped templates already use 3g (NithronOS) and 4g (TrueNAS); their texts now state these numbers. A 2 GB NAS
  (or a limit below 2.5g) runs keyword-only (see Added).

## [0.6.0] – 2026-11-23

Lab Stage 0 continues: TrueNAS support tested on a real TrueNAS, nai-bench v1 started, and the image now works
when it runs as another user.

### Fixed
- **Image runs as any user:** started as another uid (TrueNAS Apps run it as `apps`, 568; also
  `docker run --user`), nAI couldn't download its embedding model (Hugging Face's cache defaulted to
  `/.cache`) or read the bundled NLTK data (`/home/nai` is private), and fell back to keyword search.
  `HF_HOME` is now `/app/data/.cache/huggingface` and the NLTK data lives in `/opt/nltk_data`. Found in the
  TrueNAS custom-app test.

### Changed
- **Reranker policy:** `NAI_RERANKER` now takes `auto` (default), `on` or `off` (`true`/`false` still work).
  `auto` reranks the top 10 (`NAI_RERANKER_CANDIDATES=10`, was 30) only on machines with 8+ effective cores
  and 8+ GB RAM (~0.7 s per question on 8 cores) and stays off on NAS-class CPUs (~2 s on 2 cores). The
  default model is now the multilingual `BAAI/bge-reranker-v2-m3-int8` (0.57 GB download, ~1-1.5 GB RAM),
  replacing the English-only `Xenova/ms-marco-MiniLM-L-6-v2`. `/system` shows the effective state and the
  reason. `infra/docker-compose.yml` uses `auto`; the NithronOS template uses `off`.
- Hardware detection honours container limits (cgroup CPU quota and memory limit, CPU affinity) and counts
  physical cores, so a `docker --cpus=2 --memory=4g` container is no longer reported as the whole host.
- **Changing the embedding model no longer re-embeds silently.** nAI keeps the old vectors, pauses semantic
  search (keyword search keeps working) and asks an admin to confirm in the system panel or with
  `POST /system/embeddings/reindex`. Set `NAI_EMBEDDINGS_AUTO_REINDEX=true` for the old automatic re-embed.
- **Reranking is off by default** in `infra/docker-compose.yml` and the NithronOS template (it was `auto`):
  the bundled reranker is English-only and didn't help on the multilingual nai-bench. Multilingual
  alternative: `NAI_RERANKER=true` with `NAI_RERANKER_MODEL=BAAI/bge-reranker-v2-m3-int8` (MRR 0.793 → 0.918
  on nai-bench v0, but about 2–4 s per question on a 2-core CPU).
- nAI is described as a product for any NAS OS, with NithronOS as the reference platform (ADR-0004).

### Added
- **TrueNAS adapter, step 1** (`NAI_NAS_PLATFORM=truenas`): read-only share discovery through the TrueNAS
  JSON-RPC WebSocket API (`NAI_TRUENAS_URL`, `NAI_TRUENAS_API_KEY`, optional `NAI_TRUENAS_CA_FILE`; wss://
  with certificate verification only, key never logged) and a custom-app compose file with install guide in
  `packaging/truenas/`. `/sources/discover` now also reports the platform status and shares that exist on the
  NAS but aren't mounted into nAI. Tested against TrueNAS Community Edition 25.10.8 in a VM, both the adapter
  (read-only key, CA file, allow-list) and nAI as a TrueNAS custom app (`scripts/truenas-vm/`); API errors now
  show TrueNAS's reason, and the client no longer uses websockets 17's deprecated direct `connect()`.
- NAS adapter layer (`app/nas/`, `NAI_NAS_PLATFORM`: `generic` or `nithronos`) and
  `GET /sources/discover` (admin): folders under the allowed roots that could become sources.
- `/system` reports which Nithron answering model (Tern or Nox) fits the machine; `/health/detailed`
  reports the reranker model. Model names and IDs live in `app/nithron_models.py`.
- **nai-bench v0**: a multilingual NAS-style benchmark (27 files, 56 questions) with retrieval and
  answer-quality evals, a human review workflow (`evals/nai-bench/review.py`), baselines, a reranker
  comparison and simulated-NAS measurements in `evals/results/`, and CI runs with OCR.
- **nai-bench v1, first round:** 100 corpus files (EU acts in five languages, German and Swedish statutes,
  US federal rules, public-domain books, fictional documents and scans; license and SHA-256 per file) and
  100 questions in `evals/nai-bench/v1/`, split into dev and test by a hash of the item id. Every loader refuses
  the test split without `--final-run` and logs final runs to `evals/results/test-ledger.jsonl`. Training
  inputs refuse eval-only, Claude-written and nai-bench rows; `review.py` shows progress, stops cleanly and
  resumes. All v1 items are unreviewed.
- `infra/compose.bench.yaml` and `evals/smoke_ollama.sh`: an nAI + Ollama end-to-end smoke test.
- Docs: `docs/ARCHITECTURE.md`, `CONTRIBUTING.md`, `docs/KNOWN_ISSUES.md`, ADR-0003 (product scope),
  ADR-0004 (NAS adapters), lab roadmap, license register, model naming, Stage 1 plan, product and
  licensing draft; `training/` (Stage 1 skeleton, ROCm training container).

### Removed
- `packages/rag-kit`, `packages/toolpacks`, `packages/model-router` (unused by nai-core).

## [0.5.0] – 2026-11-23

Phase 2a: nAI works with other AI apps.

### Added
- **API keys** (`/auth/keys`): `nai_…` tokens, stored hashed, accepted wherever a JWT is; they act as
  their user and are deleted with the user. Managed in the web UI.
- **OpenAI-compatible API** under `/v1`: `GET /v1/models` (`nai` and `nai/<source-slug>`),
  `POST /v1/chat/completions` with streaming; answers carry extra `citations` and `nai_method` fields.
  Works with Open WebUI, LibreChat and the `openai` SDK.
- **MCP server** at `/mcp` (stateless Streamable HTTP) with read-only tools `search_files`,
  `read_document` and `list_sources`, scoped to the caller's access. Works with Claude Code and other MCP
  clients that accept a bearer token.
- CI smoke tests for `/v1` and `/mcp`.

### Changed
- Renaming a source rewrites its chunks' context headers and re-embeds them.
- NithronOS template: service named `app`, absolute data path, explicit memory limit, trusted proxy range.
- License renamed to **Nithron Community License (NCL) v1.0** (same terms as the NithronOS Community
  License). `LICENSE` synced byte-for-byte with NithronOS (adds the product name Niro to the trademark
  list); `NOTICE` lists Niro too.
- The release workflow creates GitHub Releases; GitHub Actions updated to their Node 24 versions.

### Fixed
- `app.__version__` said 0.3.0; it now matches the app version.

## [0.4.0] – 2026-11-22

Phase 1: "Ask your NAS".

### Added
- **Sources**: NAS folders indexed in place (never copied) under `NAI_SOURCES_ALLOWED_ROOTS`, kept in sync
  by a file watcher and a periodic incremental rescan; per-group access to sources.
- Page- and heading-aware extraction for PDF, DOCX, Markdown, HTML and text; **OCR** for scanned PDFs and
  images (Tesseract, `eng+deu` in the image).
- **Hybrid search**: BM25 + multilingual semantic search (fastembed, vectors in SQLite) fused with
  Reciprocal Rank Fusion, optional cross-encoder reranker, contextual chunk headers.
- **Streaming answers** (`/ask/stream`, `/chat/stream`) with citations (file, page, section) that open the
  original file.
- Hardware detection and automatic Ollama model choice (`NAI_LLM_MODEL=auto`).
- NithronOS catalog template (`packaging/nithronos/`); image `ghcr.io/nithron/nithronai/nai-core:0.4.0`.

## [0.3.0] – 2026-11-21 (not tagged)

Phase 0: foundation.

### Changed
- Authentication on every endpoint, SQLite storage, persistent chat, SSRF-safe URL ingestion, green CI.
- Relicensed from AGPL-3.0-only to the NithronOS Community License (versions up to `66fa142` remain
  AGPL-3.0-only; see `NOTICE`).

[Unreleased]: https://github.com/Nithron-Intelligence/nAI/compare/v0.7.0...HEAD
[0.7.0]: https://github.com/Nithron-Intelligence/nAI/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/Nithron-Intelligence/nAI/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/Nithron-Intelligence/nAI/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/Nithron-Intelligence/nAI/releases/tag/v0.4.0
