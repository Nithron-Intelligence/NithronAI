"""
nAI Core Retriever Service
BM25 and hybrid search with caching
"""

import math
import threading
from functools import lru_cache
from typing import TYPE_CHECKING, Any, Literal, Optional

from rank_bm25 import BM25Okapi

from ..config import Settings, get_settings
from ..models.schemas import Citation, SearchResult
from ..utils.logging import get_logger
from ..utils.text import highlight_matches, tokenize

if TYPE_CHECKING:
    from .embeddings import EmbeddingService
    from .indexer import IndexerService

logger = get_logger(__name__)

SearchMethod = Literal["auto", "bm25", "embedding", "hybrid"]


class _PositiveIdfBM25(BM25Okapi):
    """
    BM25Okapi with the Lucene IDF, log(1 + (N - n + 0.5) / (n + 0.5)), which is always
    positive. The classic formula goes negative for terms present in more than half of the
    chunks, so small personal collections (a handful of documents) returned no results.
    """

    def _calc_idf(self, nd):
        for word, freq in nd.items():
            self.idf[word] = math.log(1 + (self.corpus_size - freq + 0.5) / (freq + 0.5))
        self.average_idf = sum(self.idf.values()) / len(self.idf) if self.idf else 0.0


class BM25Index:
    """
    Cached BM25 index with automatic invalidation.
    Thread-safe implementation.
    """

    def __init__(self):
        self._bm25: _PositiveIdfBM25 | None = None
        self._corpus: list[dict[str, Any]] = []
        self._tokenized: list[list[str]] = []
        self._lock = threading.RLock()
        self._version: int = 0

    def build(self, records: list[dict[str, Any]], k1: float = 1.5, b: float = 0.75) -> None:
        """Build BM25 index from records."""
        with self._lock:
            if not records:
                self._bm25 = None
                self._corpus = []
                self._tokenized = []
                return

            self._corpus = records
            self._tokenized = [tokenize(r.get("text", "")) for r in records]
            self._bm25 = _PositiveIdfBM25(self._tokenized, k1=k1, b=b)
            self._version += 1

            logger.debug(f"Built BM25 index: {len(records)} documents, version {self._version}")

    def search(self, query: str, top_k: int = 10) -> list[tuple[int, float]]:
        """
        Search the index.
        Returns list of (index, score) tuples.
        """
        with self._lock:
            if self._bm25 is None or not self._corpus:
                return []

            query_tokens = tokenize(query)
            if not query_tokens:
                return []

            scores = self._bm25.get_scores(query_tokens)

            # Get top-k results
            ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
            return [(idx, score) for idx, score in ranked[:top_k] if score > 0]

    def get_document(self, index: int) -> dict[str, Any] | None:
        """Get document by index."""
        with self._lock:
            if 0 <= index < len(self._corpus):
                return self._corpus[index]
            return None

    @property
    def size(self) -> int:
        """Number of documents in index."""
        with self._lock:
            return len(self._corpus)

    @property
    def version(self) -> int:
        """Index version for cache invalidation."""
        return self._version


class RetrieverService:
    """
    Service for document retrieval.
    Supports BM25, embeddings (when enabled), and hybrid search.
    """

    def __init__(
        self,
        settings: Settings,
        indexer: Optional["IndexerService"] = None,
        embeddings: Optional["EmbeddingService"] = None,
    ):
        self.settings = settings
        self.indexer = indexer
        self.embeddings = embeddings
        self._bm25_index = BM25Index()
        self._index_key: Any = None

    def ensure_index(self, records: list[dict[str, Any]], version: Any = None) -> None:
        """
        Ensure BM25 index is built and up-to-date.
        Rebuilds when ``version`` (the indexer revision) changes; without a version the
        identity and size of ``records`` are used.
        """
        new_key = ("rev", version) if version is not None else ("obj", id(records), len(records))

        if new_key != self._index_key:
            logger.info("Rebuilding BM25 index...")
            self._bm25_index.build(records, k1=self.settings.bm25_k1, b=self.settings.bm25_b)
            self._index_key = new_key

    def embeddings_available(self) -> bool:
        return bool(
            self.settings.embeddings_enabled
            and self.embeddings is not None
            and self.embeddings.is_available()
        )

    def search(
        self,
        query: str,
        top_k: int = 10,
        method: SearchMethod = "auto",
    ) -> tuple[list[SearchResult], str]:
        """
        Search the indexed documents.

        ``auto``/``hybrid`` use BM25 + embeddings when embeddings are available, BM25 otherwise.
        ``embedding`` raises ValueError when embeddings are unavailable.
        Returns (results, method_used).
        """
        if self.indexer is None:
            raise RuntimeError("RetrieverService.search requires an indexer")

        records = self.indexer.load_index()
        if not records:
            return [], "none"
        version = self.indexer.revision

        if method == "embedding":
            if not self.embeddings_available():
                raise ValueError("Embedding search is not enabled. Set NAI_EMBEDDINGS_ENABLED=true")
            assert self.embeddings is not None
            return self.embeddings.search(query, top_k=top_k), "embedding"

        if method in ("auto", "hybrid") and self.embeddings_available():
            assert self.embeddings is not None
            embedding_results = self.embeddings.search(query, top_k=top_k)
            results = self.search_hybrid(
                query, records, top_k=top_k, embedding_results=embedding_results, version=version
            )
            return results, "hybrid"

        return self.search_bm25(query, records, top_k=top_k, version=version), "bm25"

    def search_bm25(
        self,
        query: str,
        records: list[dict[str, Any]],
        top_k: int = 10,
        version: Any = None,
    ) -> list[SearchResult]:
        """
        Search using BM25.

        Args:
            query: Search query
            records: Index records (will build/update index if needed)
            top_k: Number of results

        Returns:
            List of SearchResult objects
        """
        # Ensure index is current
        self.ensure_index(records, version)

        # Search
        hits = self._bm25_index.search(query, top_k)

        # Convert to SearchResult
        results = []
        for idx, score in hits:
            doc = self._bm25_index.get_document(idx)
            if doc:
                results.append(
                    SearchResult(
                        doc_id=doc.get("doc_id") or doc.get("metadata", {}).get("doc_id", ""),
                        doc_path=doc.get("doc_path", ""),
                        chunk_id=doc.get("chunk_id", 0),
                        text=doc.get("text", ""),
                        score=score,
                        highlight=highlight_matches(doc.get("text", ""), query),
                        metadata=doc.get("metadata", {}),
                    )
                )

        return results

    def search_hybrid(
        self,
        query: str,
        records: list[dict[str, Any]],
        top_k: int = 10,
        bm25_weight: float = 0.5,
        embedding_results: list[SearchResult] | None = None,
        version: Any = None,
    ) -> list[SearchResult]:
        """
        Hybrid search combining BM25 and embedding results.

        Args:
            query: Search query
            records: Index records
            top_k: Number of final results
            bm25_weight: Weight for BM25 scores (1 - bm25_weight for embeddings)
            embedding_results: Pre-computed embedding search results

        Returns:
            List of SearchResult objects with combined scores
        """
        # Get BM25 results
        bm25_results = self.search_bm25(query, records, top_k=top_k * 2, version=version)

        if not embedding_results:
            return bm25_results[:top_k]

        # Normalize scores for each method (min-max normalization)
        def normalize_scores(results: list[SearchResult]) -> dict[str, float]:
            if not results:
                return {}
            scores = [r.score for r in results]
            min_score, max_score = min(scores), max(scores)
            score_range = max_score - min_score if max_score > min_score else 1.0
            return {f"{r.doc_path}:{r.chunk_id}": (r.score - min_score) / score_range for r in results}

        bm25_normalized = normalize_scores(bm25_results)
        embed_normalized = normalize_scores(embedding_results)

        # Combine scores
        combined: dict[str, tuple[SearchResult, float]] = {}
        embedding_weight = 1.0 - bm25_weight

        for result in bm25_results:
            key = f"{result.doc_path}:{result.chunk_id}"
            bm25_score = bm25_normalized.get(key, 0)
            embed_score = embed_normalized.get(key, 0)
            combined_score = bm25_weight * bm25_score + embedding_weight * embed_score
            combined[key] = (result, combined_score)

        for result in embedding_results:
            key = f"{result.doc_path}:{result.chunk_id}"
            if key not in combined:
                bm25_score = bm25_normalized.get(key, 0)
                embed_score = embed_normalized.get(key, 0)
                combined_score = bm25_weight * bm25_score + embedding_weight * embed_score
                combined[key] = (result, combined_score)

        # Sort by combined score
        sorted_results = sorted(combined.values(), key=lambda x: x[1], reverse=True)

        # Return top-k with updated scores
        return [
            SearchResult(
                doc_id=r.doc_id,
                doc_path=r.doc_path,
                chunk_id=r.chunk_id,
                text=r.text,
                score=score,
                highlight=r.highlight,
                metadata=r.metadata,
            )
            for r, score in sorted_results[:top_k]
        ]

    def results_to_citations(self, results: list[SearchResult]) -> list[Citation]:
        """Convert search results to citations."""
        return [
            Citation(
                doc_id=r.doc_id,
                doc_path=r.doc_path,
                chunk_id=r.chunk_id,
                text=r.text,
                score=r.score,
                metadata=r.metadata,
            )
            for r in results
        ]

    def get_stats(self) -> dict[str, Any]:
        """Get retriever statistics."""
        return {
            "bm25_index_size": self._bm25_index.size,
            "bm25_index_version": self._bm25_index.version,
            "bm25_k1": self.settings.bm25_k1,
            "bm25_b": self.settings.bm25_b,
            "embeddings_enabled": self.settings.embeddings_enabled,
        }


@lru_cache(maxsize=1)
def get_retriever() -> RetrieverService:
    """Get the retriever service singleton."""
    from .embeddings import get_embedding_service
    from .indexer import get_indexer

    return RetrieverService(get_settings(), get_indexer(), get_embedding_service())
