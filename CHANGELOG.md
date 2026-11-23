# Changelog

All notable changes to nAI. Versions follow [semantic versioning](https://semver.org/); dates are release
(tag) dates. How to cut a release: [docs/RELEASING.md](docs/RELEASING.md).

## [Unreleased]

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
- NAS adapter layer (`app/nas/`, `NAI_NAS_PLATFORM`: `generic` or `nithronos`) and
  `GET /sources/discover` (admin): folders under the allowed roots that could become sources.
- `/system` reports which Nithron answering model (Tern or Nox) fits the machine; `/health/detailed`
  reports the reranker model. Model names and IDs live in `app/nithron_models.py`.
- **nai-bench v0**: a multilingual NAS-style benchmark (27 files, 56 questions) with retrieval and
  answer-quality evals, a human review workflow (`evals/nai-bench/review.py`), baselines, a reranker
  comparison and simulated-NAS measurements in `evals/results/`, and CI runs with OCR.
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

[Unreleased]: https://github.com/Nithron/NithronAI/compare/v0.5.0...HEAD
[0.5.0]: https://github.com/Nithron/NithronAI/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/Nithron/NithronAI/releases/tag/v0.4.0
