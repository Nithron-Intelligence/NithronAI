"""
nAI Core OpenAI-compatible API
Lets OpenAI-style clients (Open WebUI, LibreChat, scripts using the openai SDK, ...) use nAI
as a "model" that answers from your files.

- ``GET /v1/models``: ``nai`` (everything you can access) plus ``nai/<source>`` per source.
- ``POST /v1/chat/completions``: retrieval over the recent user turns, then nAI's answerer
  (LLM when configured, extractive quotes otherwise). Supports ``stream: true``.

Authenticate with ``Authorization: Bearer <API key>`` (create one under /auth/keys).
"""

import json
import re
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from ..config import Settings, get_config
from ..models.schemas import ChatMessage, User
from ..security import get_scope, require_auth
from ..services.access import AccessScope
from ..services.answerer import AnswererService, get_answerer
from ..services.retriever import RetrieverService, get_retriever
from ..services.sources import SourceService, get_source_service
from ..utils.sse import SSE_HEADERS

router = APIRouter(prefix="/v1", tags=["OpenAI-compatible"])

BASE_MODEL = "nai"
HISTORY_LIMIT = 20
CONTEXT_TURNS = 3


class OAIMessage(BaseModel):
    model_config = ConfigDict(extra="allow")

    role: str
    # Plain text, or the newer list-of-parts format ([{"type": "text", "text": ...}, ...])
    content: str | list[dict[str, Any]] | None = None


class OAIChatRequest(BaseModel):
    model_config = ConfigDict(extra="allow")  # temperature, max_tokens, ... are accepted and ignored

    model: str = BASE_MODEL
    messages: list[OAIMessage] = Field(..., min_length=1)
    stream: bool = False


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "source"


def _text(message: OAIMessage) -> str:
    if isinstance(message.content, str):
        return message.content
    if isinstance(message.content, list):
        return "\n".join(p.get("text", "") for p in message.content if p.get("type") == "text")
    return ""


def _visible_sources(service: SourceService, scope: AccessScope) -> list[tuple[str, int]]:
    """(model id, source id) for every source the user can search."""
    return [
        (f"{BASE_MODEL}/{_slug(s.name)}", s.id)
        for s in service.list_sources(include_paths=False)
        if scope.allows(s.id)
    ]


def _resolve_scope(model: str, scope: AccessScope, service: SourceService) -> AccessScope:
    if model in (BASE_MODEL, ""):
        return scope
    for model_id, source_id in _visible_sources(service, scope):
        if model_id == model:
            return scope.narrow([source_id], include_uploads=False)
    raise HTTPException(
        status_code=404,
        detail=f"Unknown model '{model}'. Use '{BASE_MODEL}' or one listed by GET /v1/models.",
    )


@router.get("/models")
def list_models(
    scope: AccessScope = Depends(get_scope),
    service: SourceService = Depends(get_source_service),
) -> dict:
    """``nai`` searches everything you can access; ``nai/<source>`` only that folder."""
    created = int(time.time())
    ids = [BASE_MODEL] + [model_id for model_id, _ in _visible_sources(service, scope)]
    return {
        "object": "list",
        "data": [{"id": i, "object": "model", "created": created, "owned_by": "nithron"} for i in ids],
    }


@router.post("/chat/completions", response_model=None)
async def chat_completions(
    request: OAIChatRequest,
    _user: User = Depends(require_auth),
    scope: AccessScope = Depends(get_scope),
    settings: Settings = Depends(get_config),
    sources: SourceService = Depends(get_source_service),
    retriever: RetrieverService = Depends(get_retriever),
    answerer: AnswererService = Depends(get_answerer),
) -> dict | StreamingResponse:
    """Answer the conversation from your files (OpenAI chat-completions format)."""
    narrowed = _resolve_scope(request.model, scope, sources)

    history = [
        ChatMessage(role=m.role, content=_text(m))  # type: ignore[arg-type]
        for m in request.messages
        if m.role in ("user", "assistant") and _text(m).strip()
    ][-HISTORY_LIMIT:]
    user_turns = [m.content for m in history if m.role == "user"]
    if not user_turns:
        raise HTTPException(status_code=400, detail="No user message found")

    query = " ".join(user_turns[-CONTEXT_TURNS:])
    results, _ = await run_in_threadpool(retriever.search, query, settings.default_top_k, "auto", narrowed)
    citations = retriever.results_to_citations(results)
    footer = answerer.sources_footer(citations)

    completion_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    created = int(time.time())
    citation_data = [c.model_dump() for c in citations]

    if not request.stream:
        reply, method = await answerer.chat(history, citations)
        return {
            "id": completion_id,
            "object": "chat.completion",
            "created": created,
            "model": request.model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": reply + footer},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            # Non-standard extras: OpenAI clients ignore them, nAI-aware clients can use them
            "citations": citation_data,
            "nai_method": method,
        }

    def chunk(delta: dict[str, Any], finish_reason: str | None = None) -> str:
        body = {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": request.model,
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
        }
        return f"data: {json.dumps(body, ensure_ascii=False)}\n\n"

    async def events() -> AsyncIterator[str]:
        yield chunk({"role": "assistant", "content": ""})
        async for event in answerer.stream_chat(history, citations):
            if event["type"] == "token":
                yield chunk({"content": event["text"]})
            elif event["type"] == "error":
                yield chunk({"content": f"\n\n[{event['message']}]"})
        if footer:
            yield chunk({"content": footer})
        yield chunk({}, finish_reason="stop")
        yield "data: [DONE]\n\n"

    return StreamingResponse(events(), media_type="text/event-stream", headers=SSE_HEADERS)
