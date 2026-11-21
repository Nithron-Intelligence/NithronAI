"""
nAI Core Utilities
Text processing, extraction, and helper functions
"""

from .extractors import (
    extract_html,
    extract_markdown,
    extract_pdf,
    extract_text,
    extract_text_file,
    get_file_hash,
)
from .logging import (
    get_logger,
    log_request,
    setup_logging,
)
from .text import (
    chunk_text,
    chunk_text_semantic,
    extract_sentences,
    highlight_matches,
    normalize_text,
    tokenize,
)

__all__ = [
    # Text
    "normalize_text",
    "chunk_text",
    "chunk_text_semantic",
    "extract_sentences",
    "tokenize",
    "highlight_matches",
    # Extractors
    "extract_text",
    "extract_pdf",
    "extract_markdown",
    "extract_html",
    "extract_text_file",
    "get_file_hash",
    # Logging
    "setup_logging",
    "get_logger",
    "log_request",
]
