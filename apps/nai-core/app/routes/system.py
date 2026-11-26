"""
nAI Core System Routes
Hardware, active features and recommendations (admin)
"""

from typing import Any

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool

from ..config import Settings, get_config
from ..hardware import detect_hardware, nithron_answering_model, ollama_models, recommendations
from ..security import require_admin
from ..services.embeddings import EmbeddingService, get_embedding_service, get_embedding_worker
from ..services.llm import LLMService, get_llm_service
from ..services.reranker import RerankerService, get_reranker
from ..utils.extractors import ocr_available

router = APIRouter(prefix="/system", tags=["System"], dependencies=[Depends(require_admin)])


@router.get("")
async def system_info(
    settings: Settings = Depends(get_config),
    embeddings: EmbeddingService = Depends(get_embedding_service),
    llm: LLMService = Depends(get_llm_service),
    reranker: RerankerService = Depends(get_reranker),
) -> dict:
    """What this machine is, what nAI is using, and what it recommends."""
    hw = detect_hardware()
    llm_info: dict = {"enabled": settings.llm_enabled, "provider": settings.llm_provider}
    if settings.llm_enabled:
        llm_info["configured_model"] = settings.llm_model
        llm_info["active_model"] = await run_in_threadpool(lambda: llm.resolved_model)
        if settings.llm_provider == "ollama":
            models = await run_in_threadpool(ollama_models, settings.llm_api_base or "")
            llm_info["ollama_models"] = [
                {"name": m.get("name"), "size_gb": round(m.get("size", 0) / 1024**3, 1)} for m in models
            ]
    return {
        "version": settings.app_version,
        "hardware": hw.to_dict(),
        "features": {
            "embeddings": await run_in_threadpool(embeddings.stats),
            "reranker": reranker.stats(),
            "ocr": settings.ocr_enabled and ocr_available(),
            "llm": llm_info,
        },
        "sources": {
            "allowed_roots": settings.sources_allowed_roots,
            "watch": settings.sources_watch,
            "scan_interval_seconds": settings.sources_scan_interval_seconds,
        },
        "recommendations": recommendations(hw, settings.reranker_model),
        # Which Nithron model nAI would pick here once released (docs/lab/MODEL_NAMING.md)
        "nithron_model": nithron_answering_model(hw),
    }


@router.post("/embeddings/reindex")
async def reindex_embeddings(embeddings: EmbeddingService = Depends(get_embedding_service)) -> dict[str, Any]:
    """Confirm a re-index after the embedding model changed: drop the old vectors and re-embed."""
    if not await run_in_threadpool(lambda: embeddings.reindex_required):
        return {
            "reindexing": False,
            "removed_vectors": 0,
            "pending": await run_in_threadpool(embeddings.pending_count),
        }
    removed = await run_in_threadpool(embeddings.confirm_reindex)
    get_embedding_worker().kick()
    return {
        "reindexing": True,
        "removed_vectors": removed,
        "pending": await run_in_threadpool(embeddings.pending_count),
    }
