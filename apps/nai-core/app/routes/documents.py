"""
nAI Core Document Routes
Document management endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, Query

from ..config import Settings, get_config
from ..models.schemas import DocumentDeleteResponse, DocumentInfo, DocumentListResponse
from ..security import require_admin, require_auth
from ..services.embeddings import EmbeddingService, get_embedding_service
from ..services.indexer import IndexerService, get_indexer

router = APIRouter(prefix="/documents", tags=["Documents"], dependencies=[Depends(require_auth)])


@router.get("", response_model=DocumentListResponse)
def list_documents(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=200, description="Results per page"),
    indexer: IndexerService = Depends(get_indexer),
) -> DocumentListResponse:
    """List indexed documents (newest first), paginated."""
    all_docs = indexer.list_documents()
    start = (page - 1) * page_size
    return DocumentListResponse(
        documents=all_docs[start : start + page_size],
        total=len(all_docs),
        page=page,
        page_size=page_size,
    )


@router.get("/stats/summary")
def get_stats(indexer: IndexerService = Depends(get_indexer)) -> dict:
    """Summary statistics for the document index."""
    return indexer.get_stats()


@router.get("/{doc_id}", response_model=DocumentInfo)
def get_document(doc_id: str, indexer: IndexerService = Depends(get_indexer)) -> DocumentInfo:
    """Details for one document."""
    doc = indexer.get_document(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")
    return doc


@router.delete("/{doc_id}", response_model=DocumentDeleteResponse, dependencies=[Depends(require_admin)])
def delete_document(
    doc_id: str,
    settings: Settings = Depends(get_config),
    indexer: IndexerService = Depends(get_indexer),
    embeddings: EmbeddingService = Depends(get_embedding_service),
) -> DocumentDeleteResponse:
    """Delete a document, its chunks, its stored file and its vectors (admin only)."""
    success, chunks_removed = indexer.delete_document(doc_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")

    if settings.embeddings_enabled and embeddings.is_available():
        embeddings.delete_by_doc_id(doc_id)

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
    indexer: IndexerService = Depends(get_indexer),
) -> dict:
    """Chunks of one document (useful for inspecting chunking)."""
    if not indexer.document_exists(doc_id):
        raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")

    chunks = [
        {"chunk_id": c["chunk_id"], "text": c["text"], "created_at": c["created_at"]}
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
