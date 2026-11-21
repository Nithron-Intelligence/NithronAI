"""
nAI Core Chat Routes
Multi-turn conversation endpoints (history persisted per user), plain and streaming
"""

from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse

from ..models.schemas import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    Citation,
    ConversationSummary,
    User,
)
from ..security import get_scope, require_auth
from ..services.access import AccessScope
from ..services.answerer import AnswererService, get_answerer
from ..services.conversations import ConversationStore, get_conversation_store
from ..services.retriever import RetrieverService, get_retriever
from ..utils.sse import SSE_HEADERS, sse_event

router = APIRouter(prefix="/chat", tags=["Chat"])

HISTORY_LIMIT = 20  # messages sent to the LLM
CONTEXT_TURNS = 3  # recent user turns used to build the retrieval query


async def _prepare(
    request: ChatRequest,
    conversation_id: str | None,
    user: User,
    scope: AccessScope,
    store: ConversationStore,
    retriever: RetrieverService,
) -> tuple[str, list[ChatMessage], list[Citation]]:
    """Validate, store the new user message(s), load history and retrieve context."""
    new_messages = [m for m in request.messages if m.role != "system"]
    if not any(m.role == "user" for m in new_messages):
        raise HTTPException(status_code=400, detail="No user message found")

    conv_id = request.conversation_id or conversation_id
    if conv_id:
        if not store.exists(conv_id, user.id):
            raise HTTPException(status_code=404, detail="Conversation not found")
    else:
        first_user_text = next(m.content for m in new_messages if m.role == "user")
        conv_id = store.create(user.id, title=first_user_text.strip().splitlines()[0])

    for message in new_messages:
        store.add_message(conv_id, message)
    history = store.get_messages(conv_id, limit=HISTORY_LIMIT)

    citations: list[Citation] = []
    if request.use_context:
        recent_user_turns = [m.content for m in history if m.role == "user"][-CONTEXT_TURNS:]
        narrowed = scope.narrow(request.source_ids, request.include_uploads)
        results, _ = await run_in_threadpool(
            retriever.search, " ".join(recent_user_turns), request.top_k, "auto", narrowed
        )
        citations = retriever.results_to_citations(results)
    return conv_id, history, citations


@router.post("", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    conversation_id: str | None = None,
    user: User = Depends(require_auth),
    scope: AccessScope = Depends(get_scope),
    store: ConversationStore = Depends(get_conversation_store),
    retriever: RetrieverService = Depends(get_retriever),
    answerer: AnswererService = Depends(get_answerer),
) -> ChatResponse:
    """
    Send message(s) to a conversation and get the assistant's reply.

    Pass ``conversation_id`` (body, or query parameter for older clients) to continue a
    conversation; omit it to start a new one.
    """
    conv_id, history, citations = await _prepare(request, conversation_id, user, scope, store, retriever)
    reply, method = await answerer.chat(history, citations)
    saved = store.add_message(conv_id, ChatMessage(role="assistant", content=reply), citations)
    return ChatResponse(message=saved, citations=citations, conversation_id=conv_id, method=method)


@router.post("/stream")
async def chat_stream(
    request: ChatRequest,
    user: User = Depends(require_auth),
    scope: AccessScope = Depends(get_scope),
    store: ConversationStore = Depends(get_conversation_store),
    retriever: RetrieverService = Depends(get_retriever),
    answerer: AnswererService = Depends(get_answerer),
) -> StreamingResponse:
    """
    Like ``POST /chat`` but streams Server-Sent Events: ``conversation`` (id),
    ``citations``, ``token`` deltas, optional ``error``, then ``done``.
    The full reply is saved to the conversation when the stream finishes.
    """
    conv_id, history, citations = await _prepare(request, None, user, scope, store, retriever)

    async def events() -> AsyncIterator[str]:
        yield sse_event("conversation", {"conversation_id": conv_id})
        yield sse_event("citations", [c.model_dump() for c in citations])
        async for event in answerer.stream_chat(history, citations):
            kind = event.pop("type")
            if kind == "done":
                answer = event.pop("answer", "")
                store.add_message(conv_id, ChatMessage(role="assistant", content=answer), citations)
                event["conversation_id"] = conv_id
            yield sse_event(kind, event)

    return StreamingResponse(events(), media_type="text/event-stream", headers=SSE_HEADERS)


@router.get("", response_model=list[ConversationSummary])
def list_conversations(
    user: User = Depends(require_auth),
    store: ConversationStore = Depends(get_conversation_store),
) -> list[ConversationSummary]:
    """The current user's conversations, most recently active first."""
    return store.list_for_user(user.id)


@router.get("/{conversation_id}")
def get_conversation(
    conversation_id: str,
    user: User = Depends(require_auth),
    store: ConversationStore = Depends(get_conversation_store),
) -> dict:
    """Full message history of one conversation."""
    if not store.exists(conversation_id, user.id):
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {
        "conversation_id": conversation_id,
        "messages": [m.model_dump() for m in store.get_messages(conversation_id)],
    }


@router.delete("/{conversation_id}")
def delete_conversation(
    conversation_id: str,
    user: User = Depends(require_auth),
    store: ConversationStore = Depends(get_conversation_store),
) -> dict:
    """Delete a conversation."""
    if not store.delete(conversation_id, user.id):
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"success": True, "message": "Conversation deleted"}
