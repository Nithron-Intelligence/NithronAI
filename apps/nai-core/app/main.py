"""
nAI Core - Local-first AI Document Q&A System

"The AI that knows your NAS": search and ask questions about the files on your NAS.

Features:
- Sources: NAS folders indexed in place and kept in sync (file watcher + incremental rescans)
- Uploads: PDF, DOCX, Markdown, HTML, text, code; OCR for scans and images when available
- Hybrid search: BM25 + semantic vectors (stored in SQLite) fused with RRF, optional reranker
- Answers with citations (file, page, section) from a local or remote LLM, or extractive
- Streaming (Server-Sent Events), persistent multi-turn chat
- Per-group access to sources, JWT authentication
- RESTful API with OpenAPI documentation

For configuration, set environment variables with NAI_ prefix.
See config.py for all available options.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .middleware import setup_middleware
from .routes import (
    ask_router,
    auth_router,
    chat_router,
    documents_router,
    health_router,
    ingest_router,
    mcp_router,
    openai_router,
    sources_router,
    system_router,
)
from .utils.logging import get_logger, setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown."""
    settings = get_settings()
    logger = get_logger(__name__)

    # Startup
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")
    logger.info(f"Debug mode: {settings.debug}")
    logger.info(f"Embeddings enabled: {settings.embeddings_enabled} ({settings.embeddings_provider})")
    logger.info(f"LLM enabled: {settings.llm_enabled}")
    logger.info(f"Auth enabled: {settings.auth_enabled}")

    # Warm up singletons: opens/migrates the database and builds the BM25 index
    from .services import get_indexer, get_retriever, start_background, stop_background

    indexer = get_indexer()
    retriever = get_retriever()
    records = indexer.load_index()
    logger.info(f"Loaded {len(records)} chunks from index")
    retriever.ensure_index(records, indexer.revision)

    # Embedding worker (vectors for new chunks) and source sync (watcher + rescans)
    start_background()

    if settings.auth_enabled:
        from .services import get_auth_service

        if get_auth_service().count_users() == 0:
            logger.warning(
                "Authentication is enabled but no users exist yet: "
                "the first account registered via /auth/register becomes admin."
            )

    yield

    # Shutdown
    logger.info("Shutting down nAI Core")
    stop_background()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    # Setup logging
    setup_logging(
        level=settings.log_level,
        json_format=not settings.debug,
    )

    # Create app
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=__doc__,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # CORS middleware
    origins = ["*"] if settings.cors_allow_all else settings.cors_origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,  # bearer tokens, no cookies
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "X-Response-Time", "X-RateLimit-Limit", "X-RateLimit-Remaining"],
    )

    # Custom middleware
    setup_middleware(app)

    # Register routers
    app.include_router(health_router)
    app.include_router(ingest_router)
    app.include_router(ask_router)
    app.include_router(documents_router)
    app.include_router(chat_router)
    app.include_router(auth_router)
    app.include_router(sources_router)
    app.include_router(system_router)
    app.include_router(openai_router)
    app.include_router(mcp_router)

    # Web UI on the same origin (mounted last so API routes take precedence)
    web_path = settings.web_path
    if web_path:
        app.mount("/", StaticFiles(directory=web_path, html=True), name="web")

    return app


# Create the application instance
app = create_app()


# For running directly with: python -m app.main
if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
