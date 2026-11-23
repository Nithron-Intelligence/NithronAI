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
    app_version: str = "0.5.0"
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
    web_dir: str | None = Field(
        default=None,
        description=(
            "Directory with the web UI, served at '/'. Unset: use apps/nai-docs/web from the "
            "source tree if present. Empty string: don't serve the UI."
        ),
    )
    docs_subdir: str = Field(default="docs", description="Documents subdirectory")
    index_subdir: str = Field(default="index", description="Index subdirectory")

    # Ingestion
    max_file_size_mb: int = Field(default=50, description="Maximum file size in MB")
    allowed_extensions: list[str] = Field(
        default=[
            # documents
            ".pdf",
            ".docx",
            ".txt",
            ".md",
            ".markdown",
            ".rst",
            ".html",
            ".htm",
            # data / config
            ".csv",
            ".json",
            ".yaml",
            ".yml",
            ".xml",
            ".toml",
            ".ini",
            ".log",
            # code
            ".py",
            ".js",
            ".ts",
            ".go",
            ".rs",
            ".java",
            ".c",
            ".h",
            ".cpp",
            ".sh",
            ".sql",
            # images (indexed only when OCR is available)
            ".png",
            ".jpg",
            ".jpeg",
            ".tif",
            ".tiff",
            ".webp",
        ],
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
    ocr_enabled: bool = Field(
        default=True,
        description="OCR scanned PDFs and images when pytesseract + the tesseract binary are available",
    )
    ocr_languages: str = Field(default="eng+deu", description="Tesseract language codes, '+'-separated")

    # NAS platform adapter (docs/architecture/nas-adapters.md); set by packaging
    nas_platform: str = Field(default="generic", description="NAS adapter: generic | nithronos")

    # Sources (folders on the NAS that are indexed in place and kept in sync)
    sources_allowed_roots: list[str] = Field(
        default=["/shares"],
        description="Sources must live under one of these directories (realpath-checked)",
    )
    sources_background: bool = Field(
        default=True,
        description="Run the periodic rescan and file watcher in the background",
    )
    sources_scan_interval_seconds: int = Field(
        default=900, description="Full incremental rescan interval (catches changes the watcher misses)"
    )
    sources_watch: bool = Field(
        default=True, description="React to file changes immediately (inotify via watchfiles)"
    )

    # BM25 Search
    bm25_k1: float = Field(default=1.5, description="BM25 k1 parameter")
    bm25_b: float = Field(default=0.75, description="BM25 b parameter")
    default_top_k: int = Field(default=5, description="Default number of results")

    # Embeddings (semantic search). Vectors are stored in SQLite and searched in memory.
    embeddings_enabled: bool = Field(default=True, description="Enable semantic (vector) search")
    embeddings_provider: str = Field(
        default="auto",
        description="auto | fastembed | ollama | sentence-transformers",
    )
    embeddings_model: str = Field(
        default="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        description="Embedding model (multilingual by default). For ollama e.g. 'nomic-embed-text'",
    )
    embeddings_batch_size: int = Field(default=32, description="Chunks embedded per batch")
    embeddings_auto_reindex: bool = Field(
        default=False,
        description=(
            "Re-embed everything automatically when the embedding model changes. Off: nAI keeps the old "
            "vectors, pauses semantic search and asks an admin to confirm the re-index (POST "
            "/system/embeddings/reindex), so vectors from two models are never mixed"
        ),
    )
    embeddings_background: bool = Field(
        default=True, description="Embed new chunks in a background thread (disable only for testing)"
    )
    embeddings_min_score: float = Field(
        default=0.3,
        description=(
            "Minimum cosine similarity for a vector hit (filters unrelated chunks). "
            "Model dependent: 0.3 suits the default MiniLM model; raise it for models with higher baselines."
        ),
    )
    embeddings_relative_cutoff: float = Field(
        default=0.5,
        description="Drop vector hits scoring below this fraction of the best hit (0 disables)",
    )
    models_dir: str = Field(default="models", description="Model cache directory (relative to data_dir)")

    # Retrieval
    rrf_k: int = Field(default=60, description="Reciprocal Rank Fusion constant")
    retrieval_candidates: int = Field(default=50, description="Candidates per retriever before fusion")
    # Off by default: the default model below is English-only (trained on MS MARCO) and did not improve
    # the multilingual nai-bench (evals/results/rerankers-*.md). Turn it on only with a multilingual model.
    reranker: str = Field(
        default="false",
        description="Cross-encoder reranking: true | false | auto (off by default; the default model is English-only)",
    )
    reranker_model: str = Field(
        default="Xenova/ms-marco-MiniLM-L-6-v2",
        description="fastembed cross-encoder (multilingual option: BAAI/bge-reranker-v2-m3-int8)",
    )
    reranker_candidates: int = Field(default=30, description="Fused candidates passed to the reranker")

    # LLM
    llm_enabled: bool = Field(default=False, description="Enable LLM for answer generation")
    llm_provider: str = Field(
        default="ollama",
        description=(
            "LiteLLM provider prefix: ollama, openai, anthropic, ... "
            "For OpenAI-compatible servers (vLLM, llama.cpp, LM Studio) use 'openai' + llm_base_url."
        ),
    )
    llm_model: str = Field(
        default="llama3.2",
        description="LLM model name, or 'auto' to pick the largest installed Ollama model that fits",
    )
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
    def web_path(self) -> str | None:
        """Web UI directory to serve, or None."""
        if self.web_dir == "":
            return None
        if self.web_dir:
            return self.web_dir if os.path.isdir(self.web_dir) else None
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # apps/nai-core
        candidate = os.path.join(os.path.dirname(base), "nai-docs", "web")
        return candidate if os.path.isdir(candidate) else None

    @property
    def models_path(self) -> str:
        """Model cache directory."""
        return os.path.join(self.data_path, self.models_dir)

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
