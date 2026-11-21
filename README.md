# nAI (Nithron AI) — the AI that knows your NAS

[![License: NCL v1.0](https://img.shields.io/badge/License-Nithron_Community_License-blue.svg)](./LICENSE)
[![Backend](https://img.shields.io/badge/Backend-FastAPI-informational.svg)](apps/nai-core)
[![Status](https://img.shields.io/badge/status-beta-green.svg)](#)
[![Release](https://img.shields.io/badge/nAI-v0.5.0-blue)](https://github.com/Nithron/NithronAI/releases)
[![Built by Nithron](https://img.shields.io/badge/built_by-Nithron-0b8fe0.svg)](https://nithron.com/projects/)

**nAI** lets you search and ask questions about the files on your NAS, privately, on your own
hardware. It is built to become the built-in AI of [NithronOS](https://github.com/Nithron/NithronOS).

Ask *"the insurance contract for the car"* and get `scan_0042.pdf`, page 2, even though the file
name says nothing and the contract is in German.

- 📂 **Indexes NAS folders in place** and keeps them in sync (file watcher + incremental rescans); uploads work too
- 🔍 **Hybrid search**: keyword (BM25) + multilingual semantic search, fused with Reciprocal Rank Fusion, optional reranker
- 📄 **Reads** PDF, Word, Markdown, HTML, text, data and code files; **OCR** for scans and photos of documents
- 💬 **Answers with citations** (file, page, section) that open the original file; streamed as they're written
- 🤖 **Bring your own model**: Ollama on the NAS or on a PC with a GPU, any OpenAI-compatible server, or a cloud API. Without one, nAI answers with exact quotes
- 🔌 **Works with other AI apps**: OpenAI-compatible API (Open WebUI, LibreChat, scripts) and an MCP server
  (Claude Code and other MCP clients), with per-user API keys
- 🔐 **Per-group access** to folders, JWT auth, rate limiting
- 🪶 **Runs on a CPU-only NAS**: no PyTorch, no vector database; one container, one SQLite file

> Privacy by default: nothing leaves your network unless you configure a cloud model.

---

## 📦 Quick Start

### Option 1: Docker Compose (Recommended)

```bash
cd infra
NAI_SHARES_DIR=/path/to/your/shares docker compose up -d
docker exec nai-ollama ollama pull qwen3:8b   # optional: a model for generated answers
```

Open **http://localhost:8000**, create the first account (it becomes admin), then add folders under
**Sources** (paths under `/shares`). The search model (~0.5 GB) downloads on first start; until it is
ready, search is keyword-only.

This starts:
- **nai-core** on `http://localhost:8000` (web UI + API)
- **ollama** on `http://localhost:11434` (optional local LLM)

### Option 2: NithronOS

A catalog template lives in [`packaging/nithronos/`](packaging/nithronos/). It mounts the NithronOS
shares (`/srv/shares`) read-only.

### Option 3: Local Development

```bash
cd apps/nai-core
uv venv -p 3.11 .venv && source .venv/bin/activate
pip install -r requirements-full.txt   # or requirements.txt without LLM/OCR
python -c "import nltk; nltk.download('punkt'); nltk.download('punkt_tab')"
NAI_SOURCES_ALLOWED_ROOTS='["/home/me/Documents"]' uvicorn app.main:app --reload --port 8000
```

Open http://localhost:8000 (the UI is served by the backend). OCR additionally needs the
`tesseract` binary and language packs.

---

## 🔧 Configuration

Configure via environment variables (prefix `NAI_`):

```bash
# Sources: NAS folders indexed in place (paths must be inside these roots)
NAI_SOURCES_ALLOWED_ROOTS='["/shares"]'
NAI_SOURCES_WATCH=true                    # apply file changes within seconds (inotify)
NAI_SOURCES_SCAN_INTERVAL_SECONDS=900     # full incremental rescan (catches what the watcher misses)

# Semantic search (vectors live in SQLite; no vector database)
NAI_EMBEDDINGS_ENABLED=true
NAI_EMBEDDINGS_PROVIDER=auto              # fastembed (ONNX, CPU) | ollama | sentence-transformers
NAI_EMBEDDINGS_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
NAI_RERANKER=false                        # true | false | auto (on when the hardware can afford it)

# OCR for scanned PDFs and images (needs pytesseract + tesseract)
NAI_OCR_ENABLED=true
NAI_OCR_LANGUAGES=eng+deu

# LLM answers (any LiteLLM provider). "auto" picks the largest installed Ollama model that fits.
NAI_LLM_ENABLED=true
NAI_LLM_PROVIDER=ollama                   # or openai (+ base URL for vLLM/llama.cpp/LM Studio), anthropic, ...
NAI_LLM_MODEL=auto
NAI_LLM_BASE_URL=http://192.168.1.50:11434   # e.g. Ollama on a gaming PC

# Authentication (secret key is generated and stored in data/.secret_key if unset)
NAI_AUTH_ENABLED=true
NAI_AUTH_ALLOW_REGISTRATION=false         # only admins create accounts after the first one

# Behind a reverse proxy: trust its X-Forwarded-For for rate limiting
NAI_TRUSTED_PROXIES='["10.0.0.0/8"]'
```

See [`apps/nai-core/app/config.py`](apps/nai-core/app/config.py) for all options. `GET /system`
(admin) shows the detected hardware, which features are active, and recommendations.

### Access control

With `NAI_AUTH_ENABLED=true`, every data endpoint requires a bearer token. The first account becomes
admin; after that, admins create accounts. Admins see everything. Uploaded documents are visible to
every signed-in user. A source with `allowed_groups` is visible only to members of those groups
(`PUT /auth/users/{id}/groups`); access is applied before ranking, so restricted files never appear
in results, citations, document lists or downloads. With auth disabled, the API runs as a single local
admin, which is fine on a trusted machine but not on a shared network.

---

## 📡 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check (public) |
| `/ask` | POST | Ask a question; answer + citations |
| `/ask/stream` | POST | Same, streamed as Server-Sent Events (`citations`, `token`…, `done`) |
| `/search` | POST | Search without an answer (`method`: auto, bm25, embedding, hybrid) |
| `/chat`, `/chat/stream` | POST | Multi-turn chat (pass `conversation_id` to continue) |
| `/chat` | GET | Your conversations |
| `/chat/{id}` | GET / DELETE | Conversation history / delete |
| `/documents` | GET | Documents you can access (`source_id`, `uploads_only` filters) |
| `/documents/{id}` | GET / DELETE | Details / delete an upload (admin) |
| `/documents/{id}/file` | GET | The original file (to open a citation) |
| `/documents/{id}/chunks` | GET | Inspect chunks (with page and context header) |
| `/ingest`, `/ingest/url` | POST | Upload files / fetch a URL |
| `/sources` | GET / POST | Sources you can search / add a folder (admin) |
| `/sources/{id}` | PATCH / DELETE | Change / remove a source (admin; files are never touched) |
| `/sources/{id}/scan` | POST | Rescan now (admin) |
| `/system` | GET | Hardware, active features, recommendations (admin) |
| `/auth/keys` | GET / POST | Your API keys / create one (shown once) |
| `/auth/keys/{id}` | DELETE | Revoke an API key |
| `/v1/models`, `/v1/chat/completions` | GET / POST | OpenAI-compatible API (streaming supported) |
| `/mcp` | POST | MCP server (Streamable HTTP): `search_files`, `read_document`, `list_sources` |
| `/auth/status`, `/auth/register`, `/auth/login`, `/auth/me` | | Authentication |
| `/auth/users`, `/auth/users/{id}/groups` | GET / PUT | User management (admin) |

`/ask`, `/search` and `/chat` accept `source_ids` and `include_uploads` to narrow the search.

### Example: Ask a Question

```bash
curl -X POST http://localhost:8000/ask \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"question": "When is the car insurance due?"}'
```

```json
{
  "answer": "The premium of 612 EUR is due on 1 March each year.\n\n**Sources:**\n- [1] Documents/Insurance/scan_0042.pdf, page 2\n",
  "citations": [
    {"doc_id": "s09436dac6d6b3a6", "source_name": "Documents", "doc_path": "Insurance/scan_0042.pdf",
     "page": 2, "heading": null, "text": "Die Jahresprämie beträgt 612 Euro ...", "score": 0.033}
  ],
  "method": "llm",
  "model": "ollama/qwen3:8b"
}
```

---

## 🔌 Use nAI from other apps

Create an API key in the web UI (**Settings → Connect other apps**) or with `POST /auth/keys`. A key acts
as its user: it sees exactly the folders that user can see.

**OpenAI-compatible clients** (Open WebUI, LibreChat, the `openai` SDK, ...): base URL
`http://<nas>:8000/v1`, the API key as the key. Model `nai` searches everything you can access;
`nai/<source>` (e.g. `nai/finance`) searches one folder.

```python
from openai import OpenAI
client = OpenAI(base_url="http://nas.local:8000/v1", api_key="nai_...")
reply = client.chat.completions.create(model="nai", messages=[{"role": "user", "content": "When is the car insurance due?"}])
```

**MCP clients** (Streamable HTTP with a bearer header), e.g. Claude Code:

```bash
claude mcp add --transport http nai http://nas.local:8000/mcp --header "Authorization: Bearer nai_..."
```

The assistant gets three read-only tools: `search_files` (hybrid, multilingual search with file, page
and `doc_id`), `read_document` (full text or one page) and `list_sources`.

---

## 📁 Project Structure

```
nAI/
├── apps/
│   ├── nai-core/          # FastAPI backend
│   │   ├── app/
│   │   │   ├── config.py      # Configuration
│   │   │   ├── main.py        # App factory
│   │   │   ├── routes/        # API endpoints
│   │   │   ├── services/      # Business logic
│   │   │   ├── models/        # Pydantic schemas
│   │   │   └── utils/         # Utilities
│   │   └── tests/         # API tests
│   └── nai-docs/          # Web UI
│       └── web/           # Static frontend (served by nai-core at /)
├── packaging/
│   └── nithronos/         # NithronOS app catalog template
├── packages/              # Standalone libraries, not used by nai-core
│   ├── rag-kit/           # Chunkers, rerankers, evaluators
│   └── toolpacks/         # PDF OCR, web, email, code extractors
├── evals/
│   └── retrieval/         # Evaluation framework
├── infra/
│   └── docker-compose.yml # Full stack deployment
└── docs/
    └── ADRs/              # Architecture decisions
```

---

## 🧩 Packages

These are standalone libraries kept in the repo; nai-core does not import them.

### RAG Kit (`packages/rag-kit`)

Reusable components for RAG systems:

```python
from rag_kit import SentenceChunker, CrossEncoderReranker, RetrievalMetrics

# Semantic chunking
chunker = SentenceChunker(max_chunk_size=1000)
chunks = chunker.chunk(document_text)

# Reranking
reranker = CrossEncoderReranker()
reranked = reranker.rerank(query, documents, top_k=5)

# Evaluation
metrics = RetrievalMetrics()
results = metrics.evaluate_single(retrieved_docs, relevant_docs)
print(f"Recall@5: {results.recall_at_k[5]:.3f}")
```

### Toolpacks (`packages/toolpacks`)

Specialized extractors:

```python
from toolpacks import PDFExtractor, WebScraper, EmailParser, CodeExtractor

# PDF with OCR
pdf = PDFExtractor(enable_ocr=True)
doc = pdf.extract("scanned.pdf")

# Web scraping
scraper = WebScraper()
content = scraper.scrape("https://example.com")

# Email parsing
parser = EmailParser()
emails = parser.parse_mbox("mailbox.mbox")

# Code analysis
extractor = CodeExtractor()
code = extractor.extract("main.py")
print(code.summary)
```

---

## 🧪 Testing

```bash
cd apps/nai-core
pip install pytest pytest-asyncio httpx ruff==0.17.6 mypy
pytest tests/ -v
ruff check app tests && ruff format --check app tests && mypy app
```

---

## 📊 Evaluation

Run retrieval evaluation:

```bash
python evals/retrieval/eval_retrieval.py \
  --test-file evals/retrieval/test_cases.json \
  --api-url http://localhost:8000 \
  --output results.json
```

---

## 🛣️ Roadmap

The goal: nAI as **the AI that knows your NAS**, shipped as a NithronOS app.

- [x] **Phase 0 — Foundation** (v0.3): auth on every endpoint, SQLite storage, persistent chat,
      SSRF-safe URL ingestion, green CI
- [x] **Phase 1 — "Ask your NAS" MVP** (v0.4): NAS folders indexed in place with a file watcher and
      incremental rescans; per-group access; page/heading-aware parsing for PDF, DOCX, Markdown, HTML,
      plus OCR; hybrid search (BM25 + multilingual vectors in SQLite, RRF, optional reranker) with
      contextual chunk headers; streaming answers; hardware-aware model choice; NithronOS catalog template
  - Still open: publish the v0.4.0 image and add the template to the NithronOS catalog; map NithronOS
    share permissions to nAI groups automatically; Docling for complex layouts (tables in PDFs)
- [ ] **Phase 2 — Assistant**: done so far (v0.5): API keys, OpenAI-compatible API, MCP server for nAI's
      own documents. Next: MCP server for the NithronOS API (read-only first, then confirmed actions),
      tool use, NithronOS sign-in, share permissions → nAI groups
- [ ] **Phase 3 — Everywhere**: NithronOS desktop/mobile clients, photo search, eval suite from real questions

---

## 📜 License

nAI is source-available under the **Nithron Community License (NCL) v1.0**, the license shared by all
Nithron software (including NithronOS): free for non-commercial use; commercial use, hosting and binary redistribution need a
commercial agreement. See [LICENSE](LICENSE), [COMMERCIAL.md](COMMERCIAL.md),
[TRADEMARK_POLICY.md](TRADEMARK_POLICY.md) and [BINARIES-EULA.md](BINARIES-EULA.md).

Versions up to and including commit `66fa142` were released under AGPL-3.0-only (see [NOTICE](NOTICE)).

---

## 🤝 Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing`)
5. Open a Pull Request

By contributing you agree to license your contribution under the NCL, including Nithron's right to
relicense it (LICENSE, section 4).

---

## 📞 Support

- 📖 [Documentation](docs/)
- 🐛 [Issue Tracker](https://github.com/Nithron/NithronAI/issues)

---

<p align="center">
  Built with ❤️ by the Nithron team
</p>
