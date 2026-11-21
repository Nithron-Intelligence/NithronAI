"""
nAI Core Services
Business logic layer. Every service is a lazily created singleton (``get_*``)
that routes receive through FastAPI ``Depends``.
"""

from .answerer import AnswererService, get_answerer
from .auth import AuthService, get_auth_service
from .conversations import ConversationStore, get_conversation_store
from .embeddings import EmbeddingService, get_embedding_service
from .indexer import IndexerService, get_indexer
from .llm import LLMService, get_llm_service
from .retriever import RetrieverService, get_retriever


def reset_services() -> None:
    """Drop all cached singletons (settings included). Used by tests and reconfiguration."""
    from ..config import get_settings
    from ..db import get_db

    for factory in (
        get_answerer,
        get_auth_service,
        get_conversation_store,
        get_embedding_service,
        get_indexer,
        get_llm_service,
        get_retriever,
        get_db,
        get_settings,
    ):
        factory.cache_clear()


__all__ = [
    "AnswererService",
    "AuthService",
    "ConversationStore",
    "EmbeddingService",
    "IndexerService",
    "LLMService",
    "RetrieverService",
    "get_answerer",
    "get_auth_service",
    "get_conversation_store",
    "get_embedding_service",
    "get_indexer",
    "get_llm_service",
    "get_retriever",
    "reset_services",
]
