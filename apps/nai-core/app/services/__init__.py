"""
nAI Core Services
Business logic layer. Every service is a lazily created singleton (``get_*``)
that routes receive through FastAPI ``Depends``.
"""

from .answerer import AnswererService, get_answerer
from .auth import AuthService, get_auth_service
from .conversations import ConversationStore, get_conversation_store
from .embeddings import EmbeddingService, EmbeddingWorker, get_embedding_service, get_embedding_worker
from .indexer import IndexerService, get_indexer
from .llm import LLMService, get_llm_service
from .reranker import RerankerService, get_reranker
from .retriever import RetrieverService, get_retriever
from .sources import SourceManager, SourceService, get_source_manager, get_source_service


def reset_services() -> None:
    """Drop all cached singletons (settings included). Used by tests and reconfiguration."""
    from ..config import get_settings
    from ..db import get_db
    from ..hardware import detect_hardware

    get_source_manager.cache_clear()
    get_embedding_worker.cache_clear()
    for factory in (
        get_answerer,
        get_auth_service,
        get_conversation_store,
        get_embedding_service,
        get_indexer,
        get_llm_service,
        get_reranker,
        get_retriever,
        get_source_service,
        get_db,
        get_settings,
        detect_hardware,
    ):
        factory.cache_clear()


def start_background() -> None:
    """Wire change notifications and start background workers (embeddings, source sync)."""
    worker = get_embedding_worker()
    get_indexer().add_listener(worker.kick)
    worker.start()
    get_source_manager().start()


def stop_background() -> None:
    get_source_manager().stop()
    get_embedding_worker().stop()


__all__ = [
    "AnswererService",
    "AuthService",
    "ConversationStore",
    "EmbeddingService",
    "EmbeddingWorker",
    "IndexerService",
    "LLMService",
    "RerankerService",
    "RetrieverService",
    "SourceManager",
    "SourceService",
    "get_answerer",
    "get_auth_service",
    "get_conversation_store",
    "get_embedding_service",
    "get_embedding_worker",
    "get_indexer",
    "get_llm_service",
    "get_reranker",
    "get_retriever",
    "get_source_manager",
    "get_source_service",
    "reset_services",
    "start_background",
    "stop_background",
]
