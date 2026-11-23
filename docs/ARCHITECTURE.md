# nAI architecture

How nai-core works, for contributors. User-facing docs are in the [README](../README.md); decisions are in
[`docs/ADRs/`](ADRs/); the lab's models and benchmark are in [`docs/lab/`](lab/ROADMAP.md).

## Code map

```
apps/nai-core/                 FastAPI backend (Python ≥ 3.11; CI tests 3.11 and 3.13)
  app/main.py                  create_app() + lifespan (builds BM25, start_background()/stop_background()); serves the UI at /
  app/config.py                Settings (env NAI_*, .env); get_settings() is lru_cached; web_path finds apps/nai-docs/web
  app/db.py                    SQLite (WAL, one connection per operation), SCHEMA + MIGRATIONS
                               (v2: sources, embeddings, groups; v3: api_keys)
  app/security.py              get_current_user / require_auth / require_admin / get_scope (the user's AccessScope)
  app/hardware.py              CPU/RAM/GPU detection (nvidia-smi, /sys/class/drm), tier, choose_ollama_model, recommendations
  app/routes/                  health, ingest, ask (+ /ask/stream, /search), documents (+ /file), chat (+ /stream),
                               auth (+ groups, /auth/keys), sources (admin CRUD + scan), system (admin),
                               openai_compat (/v1), mcp (/mcp)
  app/services/                indexer, sources (SourceService + SourceManager threads), retriever (RRF), embeddings
                               (providers + SQLite vectors + worker), reranker, access, answerer (+ streaming), llm,
                               auth, conversations
  app/utils/                   extractors (sections with page/heading; PDF, DOCX, Markdown, HTML, text, images + OCR),
                               text (chunk_sections, context headers, tokenize/index_tokens + stopwords),
                               net (SSRF-safe fetch), sse, logging, timeutil
  tests/                       pytest; conftest provides `client`, `make_client(**env)`, `fake_embeddings`
                               (a synonym-aware fake provider) and `share`; no model downloads
apps/nai-docs/web/             vanilla JS UI: streaming ask/chat, citations with Open, Sources tab (admin), system panel
packaging/nithronos/           NithronOS catalog template (nai/compose.yaml, schema.json, catalog-entry.yaml, icon.svg)
infra/docker-compose.yml       nai-core (UI + API on :8000, shares at /shares:ro) + Ollama; no vector DB, no proxy
infra/compose.bench*.yaml      nai-bench / smoke-test stack (auth off, localhost only)
evals/                         nai-bench, retrieval and answer evals, results
training/                      lab training code (not a nai-core dependency)
```

The Docker build context is the **repository root**: `docker build -f apps/nai-core/Dockerfile .`
(see `.dockerignore`).

## Sources: NAS folders indexed in place

- A source is a folder that nAI indexes **where it is**; files are never copied. Its path must resolve
  (realpath) inside `NAI_SOURCES_ALLOWED_ROOTS` (default `/shares`), and sources may not overlap.
- The walk skips hidden folders, `.snapshots`, `@eaDir`, `#recycle` and symlinks that leave the source.
- Document id: `"s" + sha256("{source_id}:{rel_path}")[:15]`, so it stays stable when a file is edited.
- Incremental scans: unchanged mtime and size → skip; otherwise hash; same hash → only update the mtime.
  Files that yield no text keep a row with `total_chars = 0` (hidden from lists) so they aren't retried.
- Creating a source starts a background scan. `SourceManager` runs a `watchfiles` watcher (debounced,
  restarted when sources change) plus a periodic `scan_all` every 15 minutes.
- Documents from a source can't be deleted one by one (409). Deleting a source removes its index rows only,
  never files.

## Access control

- Admins (and the anonymous admin when auth is off) see everything. Uploaded documents are visible to every
  signed-in user.
- A source with `allowed_groups` is visible only to members of those groups (`user_groups` table,
  `PUT /auth/users/{id}/groups`).
- `AccessScope.mask()` filters BM25 scores and vector scores **before** top-k, so hidden documents never
  take a result slot. The same scope applies to the documents list/get/file/chunks endpoints and `/sources`.

## Chunks

Extractors return `Section(text, page, heading)`. `chunk_sections` never crosses a section boundary. Every
chunk gets a `context` header (`Document: path | Title | Section | Page N`) that BM25 and the embedding
model see but users don't; the embedding input is `"{context}\n{text}"`
(`EmbeddingService.chunk_input`).

## Search

`RetrieverService.search(query, top_k, method, scope)`:

1. **BM25** with positive IDF; `index_tokens` drops English/German/Portuguese stopwords and splits compounds
   (`car_insurance_2024` also yields its parts).
2. **Vectors** (below).
3. **Reciprocal Rank Fusion** (k = 60) of both lists.
4. Optional **reranker**: fastembed cross-encoder (`BAAI/bge-reranker-v2-m3-int8`, multilingual) over the top
   `reranker_candidates` (10). `NAI_RERANKER=auto` (default) turns it on only when
   `hardware.reranker_auto_decision` says the machine fits the ~1 s budget: 8+ effective cores (physical
   cores, capped by the container's CPU quota), 8+ GB RAM, 2+ GB free, AVX2 on x86. A GPU doesn't count
   (CPU onnxruntime). `/system` shows the effective state and reason. Hardware detection reads the cgroup CPU
   quota and memory limit, so `docker --cpus=2 --memory=4g` is seen as a 2-CPU, 4 GB machine.

`method_used` is `bm25`, `embedding` or `hybrid` (+ `+rerank`); returned scores are RRF scores.

## Embeddings

- Providers: fastembed (default, ONNX on CPU), Ollama, sentence-transformers. Default model (from 0.7.0)
  `ibm-granite/granite-embedding-97m-multilingual-r2` (384-d, CLS pooling, no prefix), loaded as a custom fastembed ONNX model
  (`embeddings.CUSTOM_FASTEMBED_MODELS`, fp32: int8 drifts to cosine 0.972); until 0.6.0 the default was
  `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (its training lineage has non-commercial data, see `docs/lab/vane1-base-model-audit.md`).
  Changing the model ID triggers the "ask before re-indexing" flow. The 0.3 `embeddings_min_score` below was tuned
  for MiniLM; Granite passed nai-bench v1 dev with it, but re-check it when tuning.
- Vectors are float32 blobs in the `chunk_embeddings` table, searched with numpy in memory (no vector
  database).
- Filters: `embeddings_min_score` 0.3 **and** a relative cutoff of 0.5 × the best score. These were tuned
  on real data: relevant hits scored about 0.47–0.63, noise about 0.20–0.34.
- An `EmbeddingWorker` thread embeds pending chunks; the indexer notifies it. The model loads in the
  background: `/health` and `auto` search never block (`is_ready()`, `state`); only `method=embedding` waits
  (`is_available()`).
- **Changing the embedding model.** Vectors are stored with their model key (`provider:model`), and search
  only ever uses the current model's vectors, so two models are never mixed. When nAI starts with a model
  that differs from the stored vectors, `reindex_required` becomes true (cached per model key): embedding
  pauses, `auto`/`hybrid` search falls back to keyword-only, an explicit embedding search returns 400, and
  the system panel asks an admin to confirm. `POST /system/embeddings/reindex` (admin) drops the old vectors
  and the worker re-embeds everything. `NAI_EMBEDDINGS_AUTO_REINDEX=true` skips the question and re-embeds
  straight away.

## LLM answers

- `LLMService.model_name` is always `provider/model` unless already prefixed (needed for
  OpenAI-compatible servers). `NAI_LLM_MODEL=auto` picks the largest installed Ollama model that fits
  VRAM × 0.9 or RAM × 0.5.
- `stream()` yields text deltas. Answer streaming falls back to extractive quotes if the LLM fails before
  the first token, and emits an `error` event if it fails mid-stream.
- Without an LLM, answers are extractive: the best passages, quoted with their sources.

## Streaming (SSE)

- `/ask/stream`: `citations`, `token`…, optional `error`, then `done {method, model, retrieval}`.
- `/chat/stream`: `conversation`, `citations`, `token`…, `done`; the reply is saved to the conversation
  at the end.

## API keys

Schema v3 `api_keys`: `nai_` + `token_urlsafe(32)`, stored as SHA-256 with a visible prefix. Accepted
wherever a JWT is (`AuthService.get_current_user` branches on the prefix); a key acts as its user and is
deleted with them; `last_used_at` is written at most every 5 minutes. Endpoints under `/auth/keys` (auth
must be on).

## OpenAI-compatible API

`routes/openai_compat.py`: `/v1/models` (`nai` and `nai/<source-slug>`), `/v1/chat/completions` with
`stream` (OpenAI chunk format, `data: [DONE]`). Content-part messages are accepted and system messages
ignored; responses carry extra `citations` and `nai_method` fields. Tested with the official `openai` SDK.

## MCP server

`routes/mcp.py`: hand-written, stateless Streamable HTTP with JSON responses only (GET/DELETE → 405,
notifications → 202). Protocol versions 2025-06-18, 2025-03-26 and 2024-11-05 (an unknown requested
version gets 2025-06-18); batches accepted; Origin check (CORS origins or same host); a bad
`MCP-Protocol-Version` header → 400. Tools: `search_files`, `read_document` (chunks joined per page,
`max_chars`), `list_sources`; tool failures return `isError: true`. Tested with the official `mcp` SDK 2.3
client.

## Other parts

Auth (JWT, bcrypt), rate limiting, SSRF-safe URL ingestion and chat persistence date from Phase 0; see the
code in `app/services/auth.py`, `app/utils/net.py` and `app/services/conversations.py`.

## Background threads

Background work runs in daemon threads started in the app lifespan (source watcher and periodic scans,
embedding worker). Sync DB/CPU work called from async routes goes through `run_in_threadpool`.
