# Changelog

All notable changes to nAI. Versions follow [semantic versioning](https://semver.org/); dates are release
(tag) dates. How to cut a release: [docs/RELEASING.md](docs/RELEASING.md).

## [Unreleased]

Nothing yet.

## [0.5.0] – not tagged yet

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
  License).
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

[Unreleased]: https://github.com/Nithron/NithronAI/compare/v0.4.0...HEAD
[0.5.0]: https://github.com/Nithron/NithronAI/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/Nithron/NithronAI/releases/tag/v0.4.0
