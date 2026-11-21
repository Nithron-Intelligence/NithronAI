"""
nAI Core Ask Routes
Question answering and search endpoints
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool

from ..models.schemas import AskRequest, AskResponse, SearchRequest, SearchResponse
from ..security import require_auth
from ..services.answerer import AnswererService, get_answerer
from ..services.retriever import RetrieverService, get_retriever

router = APIRouter(tags=["Search & Ask"], dependencies=[Depends(require_auth)])

NO_DOCUMENTS_MESSAGE = (
    "No documents have been indexed yet. Please upload some documents first using the /ingest endpoint."
)


@router.post("/ask", response_model=AskResponse)
async def ask_question(
    request: AskRequest,
    retriever: RetrieverService = Depends(get_retriever),
    answerer: AnswererService = Depends(get_answerer),
) -> AskResponse:
    """
    Ask a question about your indexed documents.

    1. Retrieves relevant passages (BM25, plus embeddings when enabled)
    2. Generates an answer with the LLM (when enabled) or returns extractive excerpts
    3. Returns the answer with citations
    """
    results, method = await run_in_threadpool(retriever.search, request.question, request.top_k)
    if method == "none":
        return AskResponse(answer=NO_DOCUMENTS_MESSAGE, citations=[], method="none")

    citations = retriever.results_to_citations(results)
    return await answerer.answer(request.question, citations, use_llm=request.use_llm)


@router.post("/search", response_model=SearchResponse)
async def search_documents(
    request: SearchRequest,
    retriever: RetrieverService = Depends(get_retriever),
) -> SearchResponse:
    """Search indexed documents without generating an answer."""
    try:
        results, method = await run_in_threadpool(
            retriever.search, request.query, request.top_k, request.method
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return SearchResponse(results=results, total=len(results), method=method, query=request.query)
