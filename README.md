# nAI (Nithron AI) — Local-first, Open-core AI Stack

[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](./LICENSE)
[![Backend](https://img.shields.io/badge/Backend-FastAPI-informational.svg)](apps/nai-core)
[![Status](https://img.shields.io/badge/status-beta-green.svg)](#)
[![Release](https://img.shields.io/badge/nAI-v0.2.0-blue)](https://github.com/Nithronverse/nAI/releases)
[![Built by Nithron](https://img.shields.io/badge/built_by-Nithron-0b8fe0.svg)](https://nithron.com/projects/)

**nAI** is a local-first AI document Q&A system for NithronOS & Niro:

- 📄 **Ingest** PDFs, Markdown, TXT, HTML, code files
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
| **Document Ingestion** | PDF (with OCR), Markdown, TXT, HTML, code files |
| **BM25 Search** | Fast full-text search with caching |
| **Semantic Search** | Embedding-based search via Qdrant (optional) |
| **LLM Answers** | Generate answers with Ollama/OpenAI/Anthropic |
| **Multi-turn Chat** | Conversation history with context retrieval |
| **Document Management** | List, view, delete indexed documents |
| **Authentication** | JWT-based auth with user management |
| **Rate Limiting** | Configurable request throttling |
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

# Authentication
NAI_AUTH_ENABLED=true
NAI_AUTH_SECRET_KEY=your-secret-key-here
```

See [`apps/nai-core/app/config.py`](apps/nai-core/app/config.py) for all options.

---

## 📡 API Endpoints

### Core Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/ingest` | POST | Upload and index documents |
| `/ask` | POST | Ask a question |
| `/search` | POST | Raw search (no answer) |
| `/documents` | GET | List indexed documents |
| `/documents/{id}` | DELETE | Delete a document |
| `/chat` | POST | Multi-turn conversation |

### Authentication (when enabled)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/auth/register` | POST | Create new user |
| `/auth/login` | POST | Get JWT token |
| `/auth/me` | GET | Get current user |

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
pip install pytest pytest-asyncio httpx
pytest tests/ -v
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

- [x] Modular architecture
- [x] BM25 search with caching
- [x] LLM integration (LiteLLM)
- [x] Embedding search (Qdrant)
- [x] JWT authentication
- [x] Modern web UI
- [x] CI/CD pipeline
- [x] RAG Kit package
- [x] Toolpacks (PDF OCR, web, email, code)
- [ ] Streaming responses
- [ ] Multi-workspace support
- [ ] Plugin system
- [ ] Knowledge graphs

---

## 📜 License

Core is **AGPL-3.0-only**. Commercial add-ons and support available—see [COMMERCIAL.md](COMMERCIAL.md).

---

## 🤝 Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing`)
5. Open a Pull Request

---

## 📞 Support

- 📖 [Documentation](docs/)
- 🐛 [Issue Tracker](https://github.com/Nithronverse/nAI/issues)
- 💬 [Discussions](https://github.com/Nithronverse/nAI/discussions)

---

<p align="center">
  Built with ❤️ by the Nithron team
</p>
