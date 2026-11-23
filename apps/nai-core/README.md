# nAI Core (FastAPI Backend)

The core backend service for nAI - a local-first document Q&A system.

## Features

- **Document Ingestion** (`/ingest`) — Upload PDF, TXT, MD, HTML files
- **Question Answering** (`/ask`) — Get answers with citations
- **Raw Search** (`/search`) — BM25 and semantic search
- **Document Management** (`/documents`) — List, view, delete
- **Multi-turn Chat** (`/chat`) — Conversation with context
- **Authentication** (`/auth`) — JWT-based user management

## Architecture

```
app/
├── config.py          # Environment configuration
├── main.py            # FastAPI app factory
├── middleware.py      # Request logging, rate limiting
├── routes/            # API endpoints
│   ├── health.py
│   ├── ingest.py
│   ├── ask.py
│   ├── documents.py
│   ├── chat.py
│   ├── sources.py     # NAS folders (admin)
│   ├── system.py      # Hardware + features (admin)
│   └── auth.py
├── services/          # Business logic
│   ├── indexer.py     # Extraction, chunking, storage (uploads + source files in place)
│   ├── sources.py     # Folder sync: incremental scans, file watcher
│   ├── retriever.py   # BM25 + vectors, RRF fusion, reranking, access filtering
│   ├── embeddings.py  # Embedding providers, vectors in SQLite, background worker
│   ├── reranker.py    # Optional cross-encoder
│   ├── access.py      # Which sources a user may see
│   ├── answerer.py    # LLM / extractive answers (plain and streaming)
│   ├── llm.py         # LiteLLM wrapper, model auto-selection
│   ├── conversations.py
│   └── auth.py        # Authentication + groups
├── hardware.py        # CPU/RAM/GPU detection, model recommendations
├── models/            # Pydantic schemas
│   └── schemas.py
└── utils/             # Utilities
    ├── text.py        # Chunking, contextual headers, tokenization
    ├── extractors.py  # Sections (page/heading) from PDF, DOCX, MD, HTML, text; OCR
    └── logging.py     # Structured logging
```

## Quick Start

### Local Development

```bash
uv venv -p 3.11 .venv && source .venv/bin/activate
pip install -r requirements-full.txt   # requirements.txt: without LLM and OCR
python -c "import nltk; nltk.download('punkt'); nltk.download('punkt_tab')"
uvicorn app.main:app --reload --port 8000   # UI + API on http://localhost:8000
```

### Docker

```bash
# from the repository root (the image includes the web UI)
docker build -f apps/nai-core/Dockerfile -t nai-core .
docker run -p 8000:8000 -v nai-data:/app/data -v /path/to/shares:/shares:ro nai-core
```

### With Full Stack

```bash
cd ../../infra
docker-compose up -d
```

## Configuration

All configuration via environment variables with `NAI_` prefix:

```bash
# Core
NAI_DEBUG=true
NAI_LOG_LEVEL=DEBUG

# LLM
NAI_LLM_ENABLED=true
NAI_LLM_PROVIDER=ollama
NAI_LLM_MODEL=llama3.2
NAI_LLM_BASE_URL=http://localhost:11434

# Sources (NAS folders indexed in place)
NAI_SOURCES_ALLOWED_ROOTS='["/shares"]'

# Semantic search (vectors stored in SQLite, model downloaded on first start)
NAI_EMBEDDINGS_ENABLED=true
NAI_EMBEDDINGS_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
NAI_EMBEDDINGS_AUTO_REINDEX=false   # true: re-embed automatically when the model changes
NAI_RERANKER=auto                   # auto | on | off (auto: only on 8+ effective cores and 8+ GB RAM)
NAI_RERANKER_MODEL=BAAI/bge-reranker-v2-m3-int8
NAI_RERANKER_CANDIDATES=10          # top-k the reranker re-scores

# Authentication (secret generated into data/.secret_key when unset)
NAI_AUTH_ENABLED=true
```

## API Usage

### Ingest Documents

```bash
curl -X POST http://localhost:8000/ingest \
  -F "files=@document.pdf"
```

### Ask a Question

```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What is this about?", "top_k": 5}'
```

### Search

```bash
curl -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{"query": "machine learning", "method": "hybrid"}'
```

### List Documents

```bash
curl http://localhost:8000/documents
```

### Chat

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Hello"}]}'
```

## Testing

```bash
pip install pytest pytest-asyncio httpx
pytest tests/ -v
```

## API Documentation

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- OpenAPI JSON: http://localhost:8000/openapi.json
