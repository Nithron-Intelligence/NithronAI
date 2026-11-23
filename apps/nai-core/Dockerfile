# nAI Core Dockerfile
# ====================
# Multi-stage build. No PyTorch: embeddings and reranking run on ONNX (fastembed),
# so the image works on CPU-only NAS boxes (amd64 and arm64).
#
#   INSTALL_FULL=true  (default) adds LiteLLM (LLM answers) and pytesseract (OCR)
#   INSTALL_FULL=false            search + extractive answers only (smaller image)
#
# Build from the repository root (the image also serves the web UI):
#   docker build -f apps/nai-core/Dockerfile -t nai-core .

# Stage 1: Builder
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY apps/nai-core/requirements.txt apps/nai-core/requirements-full.txt ./
ARG INSTALL_FULL=true
RUN pip install --no-cache-dir --upgrade pip && \
    if [ "$INSTALL_FULL" = "true" ]; then \
        pip install --no-cache-dir -r requirements-full.txt; \
    else \
        pip install --no-cache-dir -r requirements.txt; \
    fi

RUN python -c "import nltk; nltk.download('punkt', quiet=True); nltk.download('punkt_tab', quiet=True)"

# Stage 2: Runtime
FROM python:3.11-slim AS runtime

WORKDIR /app

# tesseract: OCR for scanned PDFs and images (English + German language packs;
# add more with tesseract-ocr-<lang> and NAI_OCR_LANGUAGES)
ARG INSTALL_FULL=true
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && if [ "$INSTALL_FULL" = "true" ]; then \
        apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng tesseract-ocr-deu; \
    fi \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash --uid 1000 nai

COPY --from=builder /opt/venv /opt/venv
# Readable by any user: TrueNAS Apps and `docker run --user` start the image as another uid (568 on
# TrueNAS), whose HOME is "/" and who can't enter /home/nai (mode 0700).
COPY --from=builder /root/nltk_data /opt/nltk_data

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    NLTK_DATA=/opt/nltk_data \
    HF_HOME=/app/data/.cache/huggingface \
    HF_HUB_DISABLE_TELEMETRY=1 \
    NAI_DATA_DIR=/app/data \
    NAI_WEB_DIR=/app/web \
    NAI_SOURCES_ALLOWED_ROOTS='["/shares"]'

COPY --chown=nai:nai apps/nai-core/app ./app
COPY --chown=nai:nai apps/nai-docs/web ./web

# /app/data: database, uploads and downloaded models (mount a volume here)
# /shares:   NAS folders to index (mount read-only)
RUN mkdir -p /app/data /shares && chown -R nai:nai /app/data

USER nai

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
