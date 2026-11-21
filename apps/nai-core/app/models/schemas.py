"""
nAI Core Pydantic Schemas
Request/Response models for API endpoints
"""

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from ..utils.timeutil import utc_now_iso

# ============================================================================
# Health
# ============================================================================


class HealthResponse(BaseModel):
    """Health check response."""

    status: Literal["ok", "degraded", "error"] = "ok"
    time: str
    version: str
    components: dict[str, bool] = Field(default_factory=dict)


# ============================================================================
# Documents
# ============================================================================


class ChunkRecord(BaseModel):
    """A single chunk in the index."""

    doc_id: str = Field(..., description="Document identifier (sha256 of content, 16 hex chars)")
    doc_path: str = Field(..., description="Relative path to document")
    chunk_id: int = Field(..., description="Chunk index within document")
    text: str = Field(..., description="Chunk text content")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    created_at: str = Field(default_factory=utc_now_iso)


class DocumentInfo(BaseModel):
    """Information about an indexed document."""

    doc_id: str = Field(..., description="Unique document identifier")
    filename: str = Field(..., description="Original filename")
    path: str = Field(..., description="Relative path in storage")
    chunk_count: int = Field(..., description="Number of chunks")
    total_chars: int = Field(..., description="Total character count")
    file_size: int = Field(0, description="File size in bytes")
    file_type: str = Field(..., description="File extension/type")
    indexed_at: str = Field(..., description="Indexing timestamp")
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentListResponse(BaseModel):
    """Response for listing documents."""

    documents: list[DocumentInfo]
    total: int
    page: int = 1
    page_size: int = 50


class DocumentDeleteResponse(BaseModel):
    """Response for document deletion."""

    success: bool
    doc_id: str
    chunks_removed: int
    message: str


# ============================================================================
# Ingestion
# ============================================================================


class IngestFileResult(BaseModel):
    """Result for a single ingested file."""

    filename: str
    doc_id: str
    chunks: int
    chars: int
    status: Literal["success", "skipped", "error"]
    message: str | None = None


class IngestResponse(BaseModel):
    """Response for document ingestion."""

    added: list[IngestFileResult]
    total_chunks: int
    total_files: int
    errors: list[str] = Field(default_factory=list)


# ============================================================================
# Search & Ask
# ============================================================================


class AskRequest(BaseModel):
    """Request for asking a question."""

    question: str = Field(..., min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=50)
    use_llm: bool = Field(default=True, description="Use LLM for answer generation if available")
    include_sources: bool = Field(default=True, description="Include source chunks in response")
    filters: dict[str, Any] | None = Field(default=None, description="Optional filters")

    @field_validator("question")
    @classmethod
    def clean_question(cls, v: str) -> str:
        return v.strip()


class SearchRequest(BaseModel):
    """Request for raw search (no answer generation)."""

    query: str = Field(..., min_length=1, max_length=2000)
    top_k: int = Field(default=10, ge=1, le=100)
    method: Literal["bm25", "embedding", "hybrid"] = Field(default="bm25")
    filters: dict[str, Any] | None = Field(default=None)


class Citation(BaseModel):
    """A citation/source reference."""

    doc_id: str
    doc_path: str
    chunk_id: int
    text: str
    score: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchResult(BaseModel):
    """A single search result."""

    doc_id: str
    doc_path: str
    chunk_id: int
    text: str
    score: float
    highlight: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AskResponse(BaseModel):
    """Response for a question."""

    answer: str
    citations: list[Citation]
    method: str = Field(default="extractive", description="Answer generation method")
    model: str | None = Field(default=None, description="LLM model used if applicable")
    confidence: float | None = Field(default=None, ge=0, le=1)
    tokens_used: int | None = Field(default=None)


class SearchResponse(BaseModel):
    """Response for raw search."""

    results: list[SearchResult]
    total: int
    method: str
    query: str


# ============================================================================
# Chat (Multi-turn conversation)
# ============================================================================


class ChatMessage(BaseModel):
    """A single chat message."""

    role: Literal["user", "assistant", "system"]
    content: str
    timestamp: str | None = None


class ChatRequest(BaseModel):
    """Request for chat endpoint."""

    messages: list[ChatMessage]
    top_k: int = Field(default=5, ge=1, le=20)
    use_context: bool = Field(default=True, description="Include document context")
    conversation_id: str | None = Field(
        default=None, description="Continue an existing conversation (omit to start a new one)"
    )
    stream: bool = Field(default=False, description="Stream response (not implemented yet)")


class ChatResponse(BaseModel):
    """Response for chat endpoint."""

    message: ChatMessage
    citations: list[Citation] = Field(default_factory=list)
    conversation_id: str | None = None
    method: str = Field(default="extractive", description="llm | extractive")


class ConversationSummary(BaseModel):
    """A conversation in the user's list."""

    conversation_id: str
    title: str
    created_at: str
    updated_at: str
    message_count: int = 0


# ============================================================================
# Authentication
# ============================================================================


def _check_password_bytes(v: str) -> str:
    # bcrypt only uses the first 72 bytes; reject longer passwords instead of truncating silently
    if len(v.encode("utf-8")) > 72:
        raise ValueError("Password must be at most 72 bytes (UTF-8)")
    return v


class UserCreate(BaseModel):
    """User creation request."""

    username: str = Field(..., min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_.-]+$")
    email: str = Field(..., min_length=5, max_length=100, pattern=r"^[^@\s]+@[^@\s]+$")
    password: str = Field(..., min_length=8, max_length=72)

    @field_validator("password")
    @classmethod
    def password_bytes(cls, v: str) -> str:
        return _check_password_bytes(v)


class UserLogin(BaseModel):
    """User login request."""

    username: str
    password: str


class User(BaseModel):
    """User information (public)."""

    id: str
    username: str
    email: str
    is_active: bool = True
    is_admin: bool = False
    created_at: str


class Token(BaseModel):
    """JWT token response."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int


class TokenData(BaseModel):
    """Token payload data."""

    user_id: str | None = None
    username: str | None = None
    exp: int | None = None
