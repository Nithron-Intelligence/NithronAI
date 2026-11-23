"""
nAI Core Retriever Service

Hybrid retrieval:
1. BM25 keyword search (exact names, numbers, error strings)
2. Vector search (meaning, paraphrases, other languages), when embeddings are available
3. Reciprocal Rank Fusion of both ranked lists (no score calibration needed)
4. Optional cross-encoder reranking of the fused candidates

Access control is applied *before* ranking, so restricted users still get a full top-k.
"""

import math
import threading
from functools import lru_cache
from typing import TYPE_CHECKING, Any, Literal

import numpy as np
from rank_bm25 import BM25Okapi

from ..config import Settings, get_settings
from ..models.schemas import Citation, SearchResult
from ..utils.logging import get_logger
from ..utils.text import highlight_matches, index_tokens
from .access import UPLOADS_SOURCE, AccessScope

if TYPE_CHECKING:
    from .embeddings import EmbeddingService
    from .indexer import IndexerService
    from .reranker import RerankerService

logger = get_logger(__name__)

SearchMethod = Literal["auto", "bm25", "embedding", "hybrid"]


class _PositiveIdfBM25(BM25Okapi):
    """
    BM25Okapi with the Lucene IDF, log(1 + (N - n + 0.5) / (n + 0.5)), which is always
    positive. The classic formula goes negative for terms present in more than half of the
    chunks, so small personal collections (a handful of documents) returned no results.
    """

    def _calc_idf(self, nd: dict[str, int]) -> None:
        for word, freq in nd.items():
            self.idf[word] = math.log(1 + (self.corpus_size - freq + 0.5) / (freq + 0.5))
        self.average_idf = sum(self.idf.values()) / len(self.idf) if self.idf else 0.0


class BM25Index:
    """Thread-safe BM25 index over chunk records, with per-chunk source ids for filtering."""

    def __init__(self) -> None:
        self._bm25: _PositiveIdfBM25 | None = None
        self._corpus: list[dict[str, Any]] = []
        self._sources = np.zeros(0, dtype=np.int64)
        self._positions: dict[int, int] = {}
        self._lock = threading.RLock()
        self._version = 0

    def build(self, records: list[dict[str, Any]], k1: float = 1.5, b: float = 0.75) -> None:
        with self._lock:
            self._corpus = records
            self._sources = np.fromiter(
                (UPLOADS_SOURCE if r.get("source_id") is None else r["source_id"] for r in records),
                dtype=np.int64,
                count=len(records),
            )
            self._positions = {r["id"]: i for i, r in enumerate(records) if "id" in r}
            tokenized = [index_tokens(f"{r.get('context', '')} {r.get('text', '')}") for r in records]
            self._bm25 = _PositiveIdfBM25(tokenized, k1=k1, b=b) if records else None
            self._version += 1
            logger.debug(f"Built BM25 index: {len(records)} chunks, version {self._version}")

    def search(
        self, query: str, top_k: int = 10, scope: AccessScope | None = None
    ) -> list[tuple[int, float]]:
        """Returns (position, score) pairs, best first."""
        with self._lock:
            if self._bm25 is None or not self._corpus:
                return []
            query_tokens = index_tokens(query)
            if not query_tokens:
                return []
            scores = np.asarray(self._bm25.get_scores(query_tokens), dtype=np.float64)
            if scope is not None:
                mask = scope.mask(self._sources)
                if mask is not None:
                    scores = np.where(mask, scores, 0.0)
            n = min(top_k, scores.shape[0])
            top = np.argpartition(-scores, n - 1)[:n]
            top = top[np.argsort(-scores[top])]
            return [(int(i), float(scores[i])) for i in top if scores[i] > 0]

    def get_document(self, position: int) -> dict[str, Any] | None:
        with self._lock:
            return self._corpus[position] if 0 <= position < len(self._corpus) else None

    def position_of(self, chunk_rowid: int) -> int | None:
        with self._lock:
            return self._positions.get(chunk_rowid)

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._corpus)

    @property
    def version(self) -> int:
        return self._version


def reciprocal_rank_fusion(rankings: list[list[int]], k: int = 60) -> list[tuple[int, float]]:
    """Fuse ranked lists of ids: score(id) = sum over lists of 1 / (k + rank)."""
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda kv: kv[1], reverse=True)


def _to_result(record: dict[str, Any], score: float, query: str) -> SearchResult:
    metadata = record.get("metadata", {})
    return SearchResult(
        doc_id=record.get("doc_id", ""),
        doc_path=record.get("doc_path", ""),
        chunk_id=record.get("chunk_id", 0),
        text=record.get("text", ""),
        score=score,
        highlight=highlight_matches(record.get("text", ""), query),
        filename=record.get("filename") or metadata.get("original_filename"),
        page=record.get("page"),
        heading=metadata.get("heading"),
        source_id=record.get("source_id"),
        source_name=record.get("source_name"),
        metadata=metadata,
    )


class RetrieverService:
    def __init__(
        self,
        settings: Settings,
        indexer: "IndexerService | None" = None,
        embeddings: "EmbeddingService | None" = None,
        reranker: "RerankerService | None" = None,
    ):
        self.settings = settings
        self.indexer = indexer
        self.embeddings = embeddings
        self.reranker = reranker
        self._bm25_index = BM25Index()
        self._index_key: Any = None

    def ensure_index(self, records: list[dict[str, Any]], version: Any = None) -> None:
        """(Re)build BM25 when the indexer revision (or, without one, the record list) changes."""
        new_key = ("rev", version) if version is not None else ("obj", id(records), len(records))
        if new_key != self._index_key:
            logger.info("Rebuilding BM25 index...")
            self._bm25_index.build(records, k1=self.settings.bm25_k1, b=self.settings.bm25_b)
            self._index_key = new_key

    def embeddings_available(self, wait: bool = False) -> bool:
        """
        Whether vector search can run. By default this never blocks: while the model is
        still loading (first start downloads it) searches use BM25 only. ``wait=True``
        loads it synchronously (used when a client explicitly asks for embedding search).
        """
        if not (self.settings.embeddings_enabled and self.embeddings):
            return False
        ready = self.embeddings.is_available() if wait else self.embeddings.is_ready()
        # After an embedding-model change, semantic search waits for the admin to confirm a re-index;
        # searches fall back to keyword-only instead of mixing vectors from two models.
        return ready and not self.embeddings.reindex_required

    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        top_k: int = 10,
        method: SearchMethod = "auto",
        scope: AccessScope | None = None,
    ) -> tuple[list[SearchResult], str]:
        """
        Search the index. Returns (results, method_used) where method_used is one of
        none | bm25 | embedding | hybrid (with "+rerank" when the reranker ran).
        """
        if self.indexer is None:
            raise RuntimeError("RetrieverService.search requires an indexer")

        records = self.indexer.load_index()
        if not records:
            return [], "none"
        self.ensure_index(records, self.indexer.revision)

        if method == "embedding" and not self.embeddings_available(wait=True):
            if self.embeddings is not None and self.embeddings.reindex_required:
                raise ValueError(
                    "Embedding search is paused: the embedding model changed and an admin must confirm "
                    "a re-index (POST /system/embeddings/reindex)"
                )
            raise ValueError("Embedding search is not available (see /system for details)")

        candidates = max(self.settings.retrieval_candidates, top_k)
        rankings: list[list[int]] = []
        used: list[str] = []

        if method in ("auto", "bm25", "hybrid"):
            rankings.append([pos for pos, _ in self._bm25_index.search(query, candidates, scope)])
            used.append("bm25")

        if method in ("auto", "hybrid", "embedding") and self.embeddings_available():
            assert self.embeddings is not None
            vector_hits = self.embeddings.search(query, candidates, scope)
            positions = [self._bm25_index.position_of(rowid) for rowid, _ in vector_hits]
            rankings.append([p for p in positions if p is not None])
            used.append("embedding")

        if len(rankings) == 1:
            fused = [(pos, 1.0 / (self.settings.rrf_k + rank)) for rank, pos in enumerate(rankings[0], 1)]
        else:
            fused = reciprocal_rank_fusion(rankings, k=self.settings.rrf_k)

        method_used = "hybrid" if len(used) == 2 else used[0]

        # Optional cross-encoder reranking of the best fused candidates
        if self.reranker is not None and fused:
            head = fused[: max(self.settings.reranker_candidates, top_k)]
            docs = [self._bm25_index.get_document(pos) or {} for pos, _ in head]
            scores = self.reranker.rerank(query, [d.get("text", "") for d in docs])
            if scores is not None:
                fused = sorted(
                    zip([p for p, _ in head], scores, strict=True), key=lambda x: x[1], reverse=True
                )
                method_used += "+rerank"

        results = []
        for pos, score in fused[:top_k]:
            record = self._bm25_index.get_document(pos)
            if record is not None:
                results.append(_to_result(record, score, query))
        return results, method_used

    def search_bm25(
        self,
        query: str,
        records: list[dict[str, Any]],
        top_k: int = 10,
        version: Any = None,
    ) -> list[SearchResult]:
        """Plain BM25 over an explicit record list (used by tests and tools)."""
        self.ensure_index(records, version)
        return [
            _to_result(doc, score, query)
            for pos, score in self._bm25_index.search(query, top_k)
            if (doc := self._bm25_index.get_document(pos)) is not None
        ]

    @staticmethod
    def results_to_citations(results: list[SearchResult]) -> list[Citation]:
        return [
            Citation(
                doc_id=r.doc_id,
                doc_path=r.doc_path,
                chunk_id=r.chunk_id,
                text=r.text,
                score=r.score,
                filename=r.filename,
                page=r.page,
                heading=r.heading,
                source_id=r.source_id,
                source_name=r.source_name,
                metadata=r.metadata,
            )
            for r in results
        ]

    def get_stats(self) -> dict[str, Any]:
        return {
            "bm25_index_size": self._bm25_index.size,
            "bm25_index_version": self._bm25_index.version,
            "rrf_k": self.settings.rrf_k,
            "embeddings_available": self.embeddings_available(),
            "reranker": self.reranker.stats() if self.reranker else None,
        }


@lru_cache(maxsize=1)
def get_retriever() -> RetrieverService:
    from .embeddings import get_embedding_service
    from .indexer import get_indexer
    from .reranker import get_reranker

    return RetrieverService(get_settings(), get_indexer(), get_embedding_service(), get_reranker())
