"""
nAI Core Configuration
Environment-based configuration using pydantic-settings
"""

import os
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings

DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"


class Settings(BaseSettings):
    """Application settings loaded from environment variables (prefix ``NAI_``)."""

    # Application
    app_name: str = "nAI Core"
    app_version: str = "0.3.0"
    debug: bool = Field(default=False, description="Enable debug mode")
    log_level: str = Field(default="INFO", description="Logging level")

    # Server
    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=8000, description="Server port")

    # CORS
    cors_origins: list[str] = Field(
        default=["http://localhost:5173", "http://127.0.0.1:5173"],
        description="Allowed CORS origins",
    )
    cors_allow_all: bool = Field(default=False, description="Allow all CORS origins (dev only)")

    # Paths
    data_dir: str = Field(default="data", description="Data directory path")
    docs_subdir: str = Field(default="docs", description="Documents subdirectory")
    index_subdir: str = Field(default="index", description="Index subdirectory")

    # Ingestion
    max_file_size_mb: int = Field(default=50, description="Maximum file size in MB")
    allowed_extensions: list[str] = Field(
        default=[".pdf", ".txt", ".md", ".markdown", ".rst", ".html", ".htm"],
        description="Allowed file extensions",
    )
    chunk_size: int = Field(default=1000, description="Default chunk size in characters")
    chunk_overlap: int = Field(default=150, description="Chunk overlap in characters")
    ingest_url_allow_private: bool = Field(
        default=False,
        description=(
            "Allow /ingest/url to fetch private, loopback and link-local addresses. "
            "Keep disabled unless you trust every user who can call the endpoint."
        ),
    )
    ingest_url_timeout_seconds: int = Field(default=30, description="Timeout for URL ingestion")

    # BM25 Search
    bm25_k1: float = Field(default=1.5, description="BM25 k1 parameter")
    bm25_b: float = Field(default=0.75, description="BM25 b parameter")
    default_top_k: int = Field(default=5, description="Default number of results")

    # Embeddings
    embeddings_enabled: bool = Field(default=False, description="Enable embedding-based search")
    embeddings_model: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2",
        description="Sentence transformer model for embeddings",
    )
    embeddings_dimension: int = Field(default=384, description="Embedding vector dimension")

    # Qdrant
    qdrant_enabled: bool = Field(default=False, description="Enable Qdrant vector store")
    qdrant_host: str = Field(default="localhost", description="Qdrant host")
    qdrant_port: int = Field(default=6333, description="Qdrant port")
    qdrant_collection: str = Field(default="nai_documents", description="Qdrant collection name")

    # LLM
    llm_enabled: bool = Field(default=False, description="Enable LLM for answer generation")
    llm_provider: str = Field(
        default="ollama",
        description=(
            "LiteLLM provider prefix: ollama, openai, anthropic, ... "
            "For OpenAI-compatible servers (vLLM, llama.cpp, LM Studio) use 'openai' + llm_base_url."
        ),
    )
    llm_model: str = Field(default="llama3.2", description="LLM model name")
    llm_base_url: str | None = Field(
        default=None,
        description=f"LLM API base URL (defaults to {DEFAULT_OLLAMA_BASE_URL} for ollama)",
    )
    llm_api_key: str | None = Field(default=None, description="LLM API key (if required)")
    llm_temperature: float = Field(default=0.1, description="LLM temperature")
    llm_max_tokens: int = Field(default=1024, description="Maximum tokens for LLM response")

    # Authentication
    auth_enabled: bool = Field(default=False, description="Enable authentication")
    auth_secret_key: str | None = Field(
        default=None,
        description=(
            "JWT signing secret. If unset, a random secret is generated on first start "
            "and stored in <data_dir>/.secret_key."
        ),
    )
    auth_algorithm: str = Field(default="HS256", description="JWT algorithm")
    auth_token_expire_minutes: int = Field(default=1440, description="Token expiration in minutes")
    auth_allow_registration: bool = Field(
        default=False,
        description=(
            "Allow anyone to self-register. When disabled, only the very first user "
            "(who becomes admin) can register; afterwards admins create accounts."
        ),
    )

    # Rate Limiting
    rate_limit_enabled: bool = Field(default=True, description="Enable rate limiting")
    rate_limit_requests: int = Field(default=100, description="Requests per window")
    rate_limit_window_seconds: int = Field(default=60, description="Rate limit window in seconds")
    trusted_proxies: list[str] = Field(
        default_factory=list,
        description=(
            "IPs/CIDRs of reverse proxies whose X-Forwarded-For header is trusted. "
            "Empty means X-Forwarded-For is ignored."
        ),
    )

    model_config = {
        "env_prefix": "NAI_",
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    @property
    def data_path(self) -> str:
        """Absolute data directory path (relative paths resolve against apps/nai-core/)."""
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base, self.data_dir)

    @property
    def docs_path(self) -> str:
        """Absolute documents directory path."""
        return os.path.join(self.data_path, self.docs_subdir)

    @property
    def index_path(self) -> str:
        """Absolute index directory path."""
        return os.path.join(self.data_path, self.index_subdir)

    @property
    def index_file(self) -> str:
        """Legacy JSONL index file (only read once, to migrate into SQLite)."""
        return os.path.join(self.index_path, "index.jsonl")

    @property
    def db_file(self) -> str:
        """SQLite database file."""
        return os.path.join(self.data_path, "nai.db")

    @property
    def max_file_size_bytes(self) -> int:
        """Maximum file size in bytes."""
        return self.max_file_size_mb * 1024 * 1024

    @property
    def llm_api_base(self) -> str | None:
        """Effective LLM base URL."""
        if self.llm_base_url:
            return self.llm_base_url
        if self.llm_provider == "ollama":
            return DEFAULT_OLLAMA_BASE_URL
        return None


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


def get_config() -> Settings:
    """Get settings for FastAPI dependency injection."""
    return get_settings()
