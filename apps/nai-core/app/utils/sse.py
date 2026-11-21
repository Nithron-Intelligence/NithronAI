"""
Server-Sent Events helpers
"""

import json
from typing import Any

SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


def sse_event(event: str, data: Any) -> str:
    """Format one SSE message (data is JSON-encoded)."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
