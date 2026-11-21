# nAI (Nithron AI) — Local-first, Open-core AI Stack

[![License: NCL v1.0](https://img.shields.io/badge/License-NithronOS_Community_License-blue.svg)](./LICENSE)
[![Backend](https://img.shields.io/badge/Backend-FastAPI-informational.svg)](apps/nai-core)
[![Status](https://img.shields.io/badge/status-beta-green.svg)](#)
[![Release](https://img.shields.io/badge/nAI-v0.3.0-blue)](https://github.com/Nithron/NithronAI/releases)
[![Built by Nithron](https://img.shields.io/badge/built_by-Nithron-0b8fe0.svg)](https://nithron.com/projects/)

**nAI** is a local-first AI document Q&A system, built to become the built-in AI of
[NithronOS](https://github.com/Nithron/NithronOS): search and ask questions about the files on your NAS,
privately, on your own hardware.

- 📄 **Ingest** PDFs, Markdown, TXT, HTML, RST
- 🔍 **Search** with BM25 + optional semantic embeddings (Qdrant)
- 💬 **Ask** questions → get **answers with citations**
- 🤖 **Optional LLM** integration (Ollama, OpenAI, Anthropic via LiteLLM)
- 🔐 **JWT Authentication** and rate limiting
- 🎨 **Modern Web UI** with dark theme

> Privacy by default. Open-core by design. Runs great on a homelab.

---

## 🚀 Features

| Feature | Description |
|---------|-------------|
| **Document Ingestion** | PDF, Markdown, TXT, HTML, RST (upload or URL) |
| **BM25 Search** | Fast full-text search with caching |
| **Semantic Search** | Embedding-based search via Qdrant (optional) |
| **LLM Answers** | Generate answers with Ollama/OpenAI/Anthropic |
| **Multi-turn Chat** | Persistent, per-user conversation history with context retrieval |
| **Document Management** | List, view, delete indexed documents |
| **Authentication** | JWT auth on every data endpoint; first account becomes admin |
| **Rate Limiting** | Configurable request throttling (proxy-aware) |
| **Storage** | Single SQLite file — no database server needed |
| **Modern API** | OpenAPI docs, structured responses |
| **Docker Ready** | Full stack with Qdrant + Ollama |

---

## 📦 Quick Start

### Option 1: Docker Compose (Recommended)

```bash
cd infra
docker-compose up -d
```

This starts:
- **nai-core** on `http://localhost:8000` (API)
- **nai-web** on `http://localhost:5173` (Web UI)
- **qdrant** on `http://localhost:6333` (Vector DB)
- **ollama** on `http://localhost:11434` (Local LLM)

### Option 2: Local Development

```bash
# Backend
cd apps/nai-core
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Web UI (separate terminal)
cd apps/nai-docs/web
python -m http.server 5173
```

Open: http://localhost:5173

---

## 🔧 Configuration

Configure via environment variables (prefix `NAI_`):

```bash
# Core
NAI_DEBUG=false
NAI_LOG_LEVEL=INFO

# LLM (Ollama example)
NAI_LLM_ENABLED=true
NAI_LLM_PROVIDER=ollama
NAI_LLM_MODEL=llama3.2
NAI_LLM_BASE_URL=http://localhost:11434

# Embeddings + Qdrant
NAI_EMBEDDINGS_ENABLED=true
NAI_QDRANT_ENABLED=true
NAI_QDRANT_HOST=localhost

# Authentication (secret key is generated and stored in data/.secret_key if unset)
NAI_AUTH_ENABLED=true
NAI_AUTH_ALLOW_REGISTRATION=false   # only admins create accounts after the first one

# Behind a reverse proxy: trust its X-Forwarded-For for rate limiting
NAI_TRUSTED_PROXIES='["10.0.0.0/8"]'

# Allow /ingest/url to fetch LAN addresses (off by default: SSRF protection)
NAI_INGEST_URL_ALLOW_PRIVATE=false
```

### Authentication

With `NAI_AUTH_ENABLED=true`, every data endpoint requires a bearer token. On a fresh install the
web UI asks you to create the **first account, which becomes admin**; after that, registration is
closed and admins create accounts (`POST /auth/register` with an admin token). With auth disabled,
the API runs as a single local admin, which is fine on a trusted machine but not on a shared network.

See [`apps/nai-core/app/config.py`](apps/nai-core/app/config.py) for all options.

---

## 📡 API Endpoints

### Core Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check (public) |
| `/health/detailed` | GET | Config and stats (admin) |
| `/ingest` | POST | Upload and index documents |
| `/ingest/url` | POST | Fetch a URL and index it |
| `/ask` | POST | Ask a question |
| `/search` | POST | Raw search (no answer) |
| `/documents` | GET | List indexed documents |
| `/documents/{id}` | GET / DELETE | Document details / delete (admin) |
| `/documents/{id}/chunks` | GET | Inspect a document's chunks |
| `/chat` | POST / GET | Send a message (pass `conversation_id` to continue) / list conversations |
| `/chat/{id}` | GET / DELETE | Conversation history / delete |

### Authentication (when enabled)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/auth/status` | GET | Is auth enabled / is first-time setup pending (public) |
| `/auth/register` | POST | First user (becomes admin), or admin creating a user |
| `/auth/login` | POST | Get JWT token |
| `/auth/me` | GET | Get current user |
| `/auth/users` | GET | List users (admin) |

### Example: Ask a Question

```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What is machine learning?", "top_k": 5}'
```

Response:
```json
{
  "answer": "Based on your documents...",
  "citations": [
    {"doc_path": "ml_intro.pdf", "chunk_id": 3, "score": 8.5, "text": "..."}
  ],
  "method": "llm",
  "model": "ollama/llama3.2"
}
```

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
│       └── web/           # Static frontend
├── packages/
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
pip install pytest pytest-asyncio httpx ruff==0.17.6
pytest tests/ -v
ruff check app tests && ruff format --check app tests
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
- [ ] **Phase 1 — "Ask your NAS" MVP**: watch NAS shares and index them incrementally, permission-aware
      results, better parsing (Docling, OCR), hybrid search with RRF + reranking, embedded vector store,
      streaming answers, hardware-aware model selection, NithronOS catalog app
- [ ] **Phase 2 — Assistant**: MCP server for NithronOS (read-only first, then confirmed actions),
      tool use, OpenAI-compatible API
- [ ] **Phase 3 — Everywhere**: NithronOS desktop/mobile clients, photo search, eval suite from real questions

---

## 📜 License

nAI is source-available under the **NithronOS Community License (NCL) v1.0**, the same license as
NithronOS: free for non-commercial use; commercial use, hosting and binary redistribution need a
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
