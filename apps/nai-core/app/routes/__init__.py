"""
nAI Core API Routes
"""

from .ask import router as ask_router
from .auth import router as auth_router
from .chat import router as chat_router
from .documents import router as documents_router
from .health import router as health_router
from .ingest import router as ingest_router
from .mcp import router as mcp_router
from .openai_compat import router as openai_router
from .sources import router as sources_router
from .system import router as system_router

__all__ = [
    "ask_router",
    "auth_router",
    "chat_router",
    "documents_router",
    "health_router",
    "ingest_router",
    "mcp_router",
    "openai_router",
    "sources_router",
    "system_router",
]
