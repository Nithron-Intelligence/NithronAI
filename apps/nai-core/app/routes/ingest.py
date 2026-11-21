"""
nAI Core Ingest Routes
Upload documents (or fetch one from a URL) and index them.

Embeddings are not computed here: the indexer notifies the background embedding worker,
which vectorizes new chunks shortly afterwards. Until then a document is found by
keyword search only.
"""

import os
import re
from urllib.parse import unquote, urlparse

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool

from ..config import Settings, get_config
from ..models.schemas import IngestFileResult, IngestResponse, User
from ..security import require_auth
from ..services.indexer import IndexerService, get_indexer
from ..utils.logging import get_logger
from ..utils.net import FetchError, UnsafeURLError, fetch_url

router = APIRouter(prefix="/ingest", tags=["Ingestion"])
logger = get_logger(__name__)

CONTENT_TYPE_EXTENSIONS = {
    "text/html": ".html",
    "application/xhtml+xml": ".html",
    "application/pdf": ".pdf",
    "text/markdown": ".md",
    "text/x-markdown": ".md",
    "text/plain": ".txt",
}


def _build_response(results: list[IngestFileResult]) -> IngestResponse:
    return IngestResponse(
        added=results,
        total_chunks=sum(r.chunks for r in results if r.status == "success"),
        total_files=sum(1 for r in results if r.status == "success"),
        errors=[f"{r.filename}: {r.message}" for r in results if r.status == "error"],
    )


@router.post("", response_model=IngestResponse)
async def ingest_documents(
    files: list[UploadFile] = File(..., description="Files to ingest"),
    user: User = Depends(require_auth),
    indexer: IndexerService = Depends(get_indexer),
) -> IngestResponse:
    """
    Upload one or more documents (PDF, DOCX, Markdown, HTML, text, code; images with OCR).

    Files are extracted, chunked and indexed. Per-file problems are reported in the
    response (status ``error`` or ``skipped``) rather than failing the whole request.
    Uploaded documents are visible to every signed-in user.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    results: list[IngestFileResult] = []
    for file in files:
        content = await file.read()
        # Extraction and chunking are CPU/disk bound: keep them off the event loop.
        result = await run_in_threadpool(
            indexer.ingest_bytes, content, file.filename or "unknown", None, user.id
        )
        results.append(result)

    return _build_response(results)


def _filename_for_url(url: str, content_type: str, allowed: list[str]) -> str:
    parsed = urlparse(url)
    basename = os.path.basename(unquote(parsed.path))
    if basename and os.path.splitext(basename)[1].lower() in allowed:
        return basename
    mime = content_type.split(";", 1)[0].strip().lower()
    ext = CONTENT_TYPE_EXTENSIONS.get(mime, ".txt")
    host = re.sub(r"[^A-Za-z0-9]+", "_", parsed.hostname or "url")
    return f"url_{host}{ext}"


@router.post("/url", response_model=IngestResponse)
async def ingest_from_url(
    url: str = Query(..., description="http(s) URL to fetch and ingest"),
    user: User = Depends(require_auth),
    settings: Settings = Depends(get_config),
    indexer: IndexerService = Depends(get_indexer),
) -> IngestResponse:
    """
    Fetch a document from a URL and ingest it (HTML, PDF, Markdown or plain text).

    Private, loopback and link-local addresses are refused unless
    ``NAI_INGEST_URL_ALLOW_PRIVATE=true``.
    """
    try:
        fetched = await fetch_url(
            url,
            max_bytes=settings.max_file_size_bytes,
            timeout_seconds=settings.ingest_url_timeout_seconds,
            allow_private=settings.ingest_url_allow_private,
        )
    except UnsafeURLError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except FetchError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    filename = _filename_for_url(fetched.final_url, fetched.content_type, settings.allowed_extensions)
    result = await run_in_threadpool(
        indexer.ingest_bytes, fetched.content, filename, {"source_url": fetched.final_url}, user.id
    )
    return _build_response([result])
