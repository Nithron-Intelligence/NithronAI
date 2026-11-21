"""
nAI Core Ask Routes
Question answering (plain and streaming) and search endpoints
"""

from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse

from ..models.schemas import AskRequest, AskResponse, SearchRequest, SearchResponse
from ..security import get_scope
from ..services.access import AccessScope
from ..services.answerer import AnswererService, get_answerer
from ..services.retriever import RetrieverService, get_retriever
from ..utils.sse import SSE_HEADERS, sse_event

router = APIRouter(tags=["Search & Ask"])

NO_DOCUMENTS_MESSAGE = "No documents have been indexed yet. Upload documents or add a source folder first."


@router.post("/ask", response_model=AskResponse)
async def ask_question(
    request: AskRequest,
    scope: AccessScope = Depends(get_scope),
    retriever: RetrieverService = Depends(get_retriever),
    answerer: AnswererService = Depends(get_answerer),
) -> AskResponse:
    """
    Ask a question about your documents.

    1. Retrieves relevant passages (BM25 + semantic search, fused with RRF)
    2. Generates an answer with the LLM (when enabled) or returns extractive excerpts
    3. Returns the answer with citations (file, page, section)
    """
    narrowed = scope.narrow(request.source_ids, request.include_uploads)
    results, method = await run_in_threadpool(
        retriever.search, request.question, request.top_k, "auto", narrowed
    )
    if method == "none":
        return AskResponse(answer=NO_DOCUMENTS_MESSAGE, citations=[], method="none")

    citations = retriever.results_to_citations(results)
    return await answerer.answer(request.question, citations, use_llm=request.use_llm)


@router.post("/ask/stream")
async def ask_question_stream(
    request: AskRequest,
    scope: AccessScope = Depends(get_scope),
    retriever: RetrieverService = Depends(get_retriever),
    answerer: AnswererService = Depends(get_answerer),
) -> StreamingResponse:
    """
    Like ``/ask`` but streams Server-Sent Events:
    ``citations`` (once), ``token`` (text deltas), optional ``error``, then ``done``.
    """
    narrowed = scope.narrow(request.source_ids, request.include_uploads)
    results, method = await run_in_threadpool(
        retriever.search, request.question, request.top_k, "auto", narrowed
    )
    citations = retriever.results_to_citations(results)

    async def events() -> AsyncIterator[str]:
        yield sse_event("citations", [c.model_dump() for c in citations])
        if method == "none":
            yield sse_event("token", {"text": NO_DOCUMENTS_MESSAGE})
            yield sse_event("done", {"method": "none", "model": None})
            return
        async for event in answerer.stream_answer(request.question, citations, use_llm=request.use_llm):
            kind = event.pop("type")
            if kind == "done":
                event.pop("answer", None)
                event["retrieval"] = method
            yield sse_event(kind, event)

    return StreamingResponse(events(), media_type="text/event-stream", headers=SSE_HEADERS)


@router.post("/search", response_model=SearchResponse)
async def search_documents(
    request: SearchRequest,
    scope: AccessScope = Depends(get_scope),
    retriever: RetrieverService = Depends(get_retriever),
) -> SearchResponse:
    """Search documents without generating an answer."""
    narrowed = scope.narrow(request.source_ids, request.include_uploads)
    try:
        results, method = await run_in_threadpool(
            retriever.search, request.query, request.top_k, request.method, narrowed
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return SearchResponse(results=results, total=len(results), method=method, query=request.query)
