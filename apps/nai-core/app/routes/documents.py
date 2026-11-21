"""
nAI Core Document Routes
Document management endpoints (filtered by what the user may access)
"""

import mimetypes
import os

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from ..models.schemas import DocumentDeleteResponse, DocumentInfo, DocumentListResponse
from ..security import get_scope, require_admin, require_auth
from ..services.access import AccessScope
from ..services.indexer import IndexerService, get_indexer

router = APIRouter(prefix="/documents", tags=["Documents"], dependencies=[Depends(require_auth)])


@router.get("", response_model=DocumentListResponse)
def list_documents(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=200, description="Results per page"),
    source_id: int | None = Query(None, description="Only documents from this source"),
    uploads_only: bool = Query(False, description="Only uploaded documents"),
    scope: AccessScope = Depends(get_scope),
    indexer: IndexerService = Depends(get_indexer),
) -> DocumentListResponse:
    """List documents you can access (newest first), paginated."""
    docs = indexer.list_documents(scope)
    if uploads_only:
        docs = [d for d in docs if d.source_id is None]
    elif source_id is not None:
        docs = [d for d in docs if d.source_id == source_id]
    start = (page - 1) * page_size
    return DocumentListResponse(
        documents=docs[start : start + page_size], total=len(docs), page=page, page_size=page_size
    )


@router.get("/stats/summary")
def get_stats(indexer: IndexerService = Depends(get_indexer)) -> dict:
    """Summary statistics for the index."""
    return indexer.get_stats()


@router.get("/{doc_id}", response_model=DocumentInfo)
def get_document(
    doc_id: str,
    scope: AccessScope = Depends(get_scope),
    indexer: IndexerService = Depends(get_indexer),
) -> DocumentInfo:
    """Details for one document."""
    doc = indexer.get_document(doc_id, scope)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")
    return doc


@router.get("/{doc_id}/file")
def download_document(
    doc_id: str,
    scope: AccessScope = Depends(get_scope),
    indexer: IndexerService = Depends(get_indexer),
) -> FileResponse:
    """The original file (for opening a cited document)."""
    path = indexer.document_file_path(doc_id, scope)
    if path is None:
        raise HTTPException(status_code=404, detail=f"File not available: {doc_id}")
    media_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
    return FileResponse(
        path, media_type=media_type, filename=os.path.basename(path), content_disposition_type="inline"
    )


@router.delete("/{doc_id}", response_model=DocumentDeleteResponse, dependencies=[Depends(require_admin)])
def delete_document(doc_id: str, indexer: IndexerService = Depends(get_indexer)) -> DocumentDeleteResponse:
    """Delete an uploaded document, its chunks and stored file (admin only)."""
    try:
        success, chunks_removed = indexer.delete_document(doc_id)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    if not success:
        raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")
    return DocumentDeleteResponse(
        success=True,
        doc_id=doc_id,
        chunks_removed=chunks_removed,
        message=f"Successfully deleted document and {chunks_removed} chunks",
    )


@router.get("/{doc_id}/chunks")
def get_document_chunks(
    doc_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    scope: AccessScope = Depends(get_scope),
    indexer: IndexerService = Depends(get_indexer),
) -> dict:
    """Chunks of one document (useful for inspecting chunking)."""
    if indexer.get_document(doc_id, scope) is None:
        raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")
    chunks = [
        {
            "chunk_id": c["chunk_id"],
            "text": c["text"],
            "context": c["context"],
            "page": c["page"],
            "created_at": c["created_at"],
        }
        for c in indexer.get_chunks(doc_id)
    ]
    start = (page - 1) * page_size
    return {
        "doc_id": doc_id,
        "chunks": chunks[start : start + page_size],
        "total": len(chunks),
        "page": page,
        "page_size": page_size,
    }
