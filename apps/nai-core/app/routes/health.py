"""
nAI Core Health Routes
Health check and system status endpoints
"""

from typing import Any

from fastapi import APIRouter, Depends

from ..config import Settings, get_config
from ..models.schemas import HealthResponse
from ..security import require_admin
from ..services.answerer import AnswererService, get_answerer
from ..services.embeddings import EmbeddingService, get_embedding_service
from ..services.indexer import IndexerService, get_indexer
from ..services.retriever import RetrieverService, get_retriever
from ..utils.timeutil import utc_now_iso

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse)
def health_check(
    settings: Settings = Depends(get_config),
    indexer: IndexerService = Depends(get_indexer),
    embeddings: EmbeddingService = Depends(get_embedding_service),
    answerer: AnswererService = Depends(get_answerer),
) -> HealthResponse:
    """Public health check: overall status and component health."""
    components: dict[str, bool] = {}

    try:
        _ = indexer.revision
        components["index"] = True
    except Exception:
        components["index"] = False

    if settings.embeddings_enabled:
        # "loading" counts as healthy: the model may still be downloading on first start
        embeddings.ensure_loading()
        components["embeddings"] = embeddings.state != "error"
    if settings.llm_enabled:
        components["llm"] = answerer.is_llm_available()

    return HealthResponse(
        status="degraded" if False in components.values() else "ok",
        time=utc_now_iso(),
        version=settings.app_version,
        components=components,
    )


@router.get("/health/detailed", dependencies=[Depends(require_admin)])
def detailed_health(
    settings: Settings = Depends(get_config),
    indexer: IndexerService = Depends(get_indexer),
    retriever: RetrieverService = Depends(get_retriever),
    embeddings: EmbeddingService = Depends(get_embedding_service),
) -> dict[str, Any]:
    """Configuration and statistics (admin only)."""
    return {
        "status": "ok",
        "time": utc_now_iso(),
        "version": settings.app_version,
        "config": {
            "debug": settings.debug,
            "embeddings_enabled": settings.embeddings_enabled,
            "embeddings_provider": settings.embeddings_provider,
            "reranker": settings.reranker,
            "llm_enabled": settings.llm_enabled,
            "llm_provider": settings.llm_provider if settings.llm_enabled else None,
            "auth_enabled": settings.auth_enabled,
        },
        "index": indexer.get_stats(),
        "retriever": retriever.get_stats(),
        "embeddings": embeddings.stats() if settings.embeddings_enabled else None,
    }
