"""
nAI Core Models
Pydantic schemas and data models
"""

from .schemas import (
    # Search & Ask
    AskRequest,
    AskResponse,
    # Chat
    ChatMessage,
    ChatRequest,
    ChatResponse,
    ChunkRecord,
    Citation,
    ConversationSummary,
    DocumentDeleteResponse,
    # Documents
    DocumentInfo,
    DocumentListResponse,
    # Health
    HealthResponse,
    # Ingestion
    IngestFileResult,
    IngestResponse,
    SearchRequest,
    SearchResponse,
    SearchResult,
    Token,
    TokenData,
    User,
    # Auth
    UserCreate,
    UserLogin,
)

__all__ = [
    "AskRequest",
    "AskResponse",
    "ChatMessage",
    "ChatRequest",
    "ChatResponse",
    "ChunkRecord",
    "Citation",
    "ConversationSummary",
    "DocumentDeleteResponse",
    "DocumentInfo",
    "DocumentListResponse",
    "HealthResponse",
    "IngestFileResult",
    "IngestResponse",
    "SearchRequest",
    "SearchResponse",
    "SearchResult",
    "Token",
    "TokenData",
    "User",
    "UserCreate",
    "UserLogin",
]
