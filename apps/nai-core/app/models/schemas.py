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
    source_id: int | None = Field(None, description="Source folder id (None for uploads)")
    source_name: str | None = Field(None, description="Source folder name")
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
    source_ids: list[int] | None = Field(
        default=None, description="Only search these sources (default: every source you can access)"
    )
    include_uploads: bool = Field(default=True, description="Include uploaded documents")

    @field_validator("question")
    @classmethod
    def clean_question(cls, v: str) -> str:
        return v.strip()


class SearchRequest(BaseModel):
    """Request for raw search (no answer generation)."""

    query: str = Field(..., min_length=1, max_length=2000)
    top_k: int = Field(default=10, ge=1, le=100)
    method: Literal["auto", "bm25", "embedding", "hybrid"] = Field(default="auto")
    source_ids: list[int] | None = Field(
        default=None, description="Only search these sources (default: every source you can access)"
    )
    include_uploads: bool = Field(default=True, description="Include uploaded documents")


class Citation(BaseModel):
    """A citation/source reference."""

    doc_id: str
    doc_path: str
    chunk_id: int
    text: str
    score: float
    filename: str | None = None
    page: int | None = None
    heading: str | None = None
    source_id: int | None = None
    source_name: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchResult(BaseModel):
    """A single search result."""

    doc_id: str
    doc_path: str
    chunk_id: int
    text: str
    score: float
    highlight: str | None = None
    filename: str | None = None
    page: int | None = None
    heading: str | None = None
    source_id: int | None = None
    source_name: str | None = None
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
    source_ids: list[int] | None = Field(
        default=None, description="Only search these sources (default: every source you can access)"
    )
    include_uploads: bool = Field(default=True, description="Include uploaded documents")


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
    groups: list[str] = Field(default_factory=list)


class UserGroupsUpdate(BaseModel):
    """Replace a user's groups."""

    groups: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("groups")
    @classmethod
    def clean_groups(cls, v: list[str]) -> list[str]:
        cleaned = sorted({g.strip() for g in v if g.strip()})
        if any(len(g) > 64 for g in cleaned):
            raise ValueError("Group names must be at most 64 characters")
        return cleaned


class ApiKeyCreate(BaseModel):
    """Create an API key."""

    name: str = Field(..., min_length=1, max_length=80, description="What the key is for, e.g. 'Open WebUI'")


class ApiKeyInfo(BaseModel):
    """An API key (the secret itself is only shown once, at creation)."""

    id: str
    name: str
    prefix: str = Field(..., description="First characters of the key, to recognise it")
    created_at: str
    last_used_at: str | None = None


class ApiKeyCreated(ApiKeyInfo):
    key: str = Field(..., description="The API key. Store it now: it cannot be shown again.")


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


# ============================================================================
# Sources (NAS folders indexed in place)
# ============================================================================


class SourceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    path: str = Field(..., min_length=1, description="Absolute folder path on the server")
    recursive: bool = True
    exclude_patterns: list[str] = Field(
        default_factory=list, description="Glob patterns on relative paths to skip, e.g. '*.tmp', 'Archive/*'"
    )
    allowed_groups: list[str] = Field(
        default_factory=list, description="Groups that may see this source (empty: every user)"
    )
    enabled: bool = True


class SourceUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=80)
    recursive: bool | None = None
    exclude_patterns: list[str] | None = None
    allowed_groups: list[str] | None = None
    enabled: bool | None = None


class SourceInfo(BaseModel):
    id: int
    name: str
    path: str | None = Field(None, description="Only shown to admins")
    recursive: bool = True
    exclude_patterns: list[str] = Field(default_factory=list)
    allowed_groups: list[str] = Field(default_factory=list)
    enabled: bool = True
    created_at: str
    last_scan_started: str | None = None
    last_scan_finished: str | None = None
    last_scan_status: str = "never"
    last_error: str | None = None
    document_count: int = 0
    scanning: bool = False


class ShareCandidateInfo(BaseModel):
    name: str
    path: str
    source: str = "mount"
    already_added: bool = False
    mounted: bool = True


class ShareDiscovery(BaseModel):
    platform: str
    platform_name: str
    capabilities: dict[str, bool]
    status: dict[str, Any] = Field(default_factory=dict)
    shares: list[ShareCandidateInfo]


class ScanResult(BaseModel):
    source_id: int
    indexed: int = 0
    unchanged: int = 0
    removed: int = 0
    skipped: int = 0
    errors: int = 0
    seconds: float = 0.0


__all__ = [
    "HealthResponse",
    "ChunkRecord",
    "DocumentInfo",
    "DocumentListResponse",
    "DocumentDeleteResponse",
    "IngestFileResult",
    "IngestResponse",
    "AskRequest",
    "SearchRequest",
    "Citation",
    "SearchResult",
    "AskResponse",
    "SearchResponse",
    "ChatMessage",
    "ChatRequest",
    "ChatResponse",
    "ConversationSummary",
    "UserCreate",
    "UserLogin",
    "User",
    "UserGroupsUpdate",
    "ApiKeyCreate",
    "ApiKeyInfo",
    "ApiKeyCreated",
    "Token",
    "TokenData",
    "SourceCreate",
    "SourceUpdate",
    "SourceInfo",
    "ScanResult",
    "ShareCandidateInfo",
    "ShareDiscovery",
]
