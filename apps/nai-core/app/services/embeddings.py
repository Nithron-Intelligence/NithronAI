"""
nAI Core Embedding Service

Semantic search without an external vector database:
- An *embedding provider* turns text into vectors: fastembed (ONNX, CPU-friendly, no
  PyTorch; default), Ollama's /api/embed, or sentence-transformers.
- Vectors are stored in SQLite (``chunk_embeddings``) and searched in memory with numpy
  (brute-force cosine similarity; fast enough for hundreds of thousands of chunks).
- A background worker embeds chunks that have no vector for the current model, so new
  documents become semantically searchable shortly after indexing and switching models
  simply re-embeds in the background.
"""

import json
import threading
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Protocol

import numpy as np

from ..config import Settings, get_settings
from ..db import Database, get_db
from ..utils.logging import get_logger
from .access import UPLOADS_SOURCE, AccessScope

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------


class EmbeddingProvider(Protocol):
    name: str
    model: str

    def embed_documents(self, texts: list[str]) -> np.ndarray: ...

    def embed_query(self, text: str) -> np.ndarray: ...


class FastEmbedProvider:
    name = "fastembed"

    def __init__(self, settings: Settings):
        from fastembed import TextEmbedding

        self.model = settings.embeddings_model
        self._batch = settings.embeddings_batch_size
        logger.info(f"Loading fastembed model {self.model} (downloads on first use)")
        self._model = TextEmbedding(model_name=self.model, cache_dir=settings.models_path)

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        return np.asarray(list(self._model.embed(texts, batch_size=self._batch)), dtype=np.float32)

    def embed_query(self, text: str) -> np.ndarray:
        return np.asarray(next(iter(self._model.query_embed(text))), dtype=np.float32)


class OllamaEmbeddingProvider:
    name = "ollama"

    def __init__(self, settings: Settings):
        self.model = settings.embeddings_model
        self._url = (settings.llm_base_url or "http://localhost:11434").rstrip("/") + "/api/embed"
        self.embed_query("ping")  # fail fast if Ollama or the model is missing

    def _post(self, inputs: list[str]) -> np.ndarray:
        body = json.dumps({"model": self.model, "input": inputs}).encode()
        request = urllib.request.Request(self._url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=120) as response:
            data = json.load(response)
        return np.asarray(data["embeddings"], dtype=np.float32)

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        return self._post(texts)

    def embed_query(self, text: str) -> np.ndarray:
        return self._post([text])[0]


class SentenceTransformerProvider:
    name = "sentence-transformers"

    def __init__(self, settings: Settings):
        from sentence_transformers import SentenceTransformer

        self.model = settings.embeddings_model
        self._model = SentenceTransformer(self.model, cache_folder=settings.models_path)

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        return np.asarray(self._model.encode(texts, convert_to_numpy=True), dtype=np.float32)

    def embed_query(self, text: str) -> np.ndarray:
        return self.embed_documents([text])[0]


ProviderFactory = Callable[[Settings], EmbeddingProvider]

PROVIDERS: dict[str, ProviderFactory] = {
    "fastembed": FastEmbedProvider,
    "ollama": OllamaEmbeddingProvider,
    "sentence-transformers": SentenceTransformerProvider,
}
AUTO_ORDER = ["fastembed", "sentence-transformers", "ollama"]


def register_provider(name: str, factory: ProviderFactory) -> None:
    """Register an extra provider (also used by tests to inject a fake one)."""
    PROVIDERS[name] = factory


def _normalize(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=-1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


@dataclass
class _VectorCache:
    key: tuple[int, int, str]
    rowids: np.ndarray  # chunk rowids, aligned with matrix rows
    sources: np.ndarray  # source id per row (UPLOADS_SOURCE for uploads)
    matrix: np.ndarray  # normalized float32 [n, dim]


class EmbeddingService:
    def __init__(self, settings: Settings, db: Database):
        self.settings = settings
        self.db = db
        self._provider: EmbeddingProvider | None = None
        self._provider_error: str | None = None
        self._loading_started = False
        self._provider_lock = threading.Lock()
        self._embed_lock = threading.Lock()
        self._cache: _VectorCache | None = None
        self._cache_lock = threading.Lock()

    # -- provider ----------------------------------------------------------

    def _load_provider(self) -> EmbeddingProvider | None:
        if not self.settings.embeddings_enabled:
            return None
        if self._provider is not None or self._provider_error is not None:
            return self._provider
        with self._provider_lock:
            if self._provider is not None or self._provider_error is not None:
                return self._provider
            wanted = self.settings.embeddings_provider
            candidates = AUTO_ORDER if wanted == "auto" else [wanted]
            errors = []
            for name in candidates:
                factory = PROVIDERS.get(name)
                if factory is None:
                    errors.append(f"{name}: unknown provider")
                    continue
                try:
                    self._provider = factory(self.settings)
                    logger.info(f"Embeddings: {name} / {self._provider.model}")
                    return self._provider
                except Exception as e:  # ImportError, download/network failure, ...
                    errors.append(f"{name}: {e}")
            self._provider_error = "; ".join(errors) or "no provider"
            logger.warning(f"Semantic search unavailable, using keyword search only ({self._provider_error})")
            return None

    def is_available(self) -> bool:
        """Load the provider if needed (may block for a model download) and report success."""
        return self._load_provider() is not None

    def is_ready(self) -> bool:
        """Non-blocking: True once the model is loaded. Starts loading in the background."""
        if self._provider is not None:
            return True
        self.ensure_loading()
        return False

    def ensure_loading(self) -> None:
        """Load the provider in a background thread (first start downloads the model)."""
        if not self.settings.embeddings_enabled or self._loading_started:
            return
        with self._provider_lock:
            if self._loading_started:
                return
            self._loading_started = True
        threading.Thread(target=self._load_provider, name="nai-embeddings-load", daemon=True).start()

    @property
    def state(self) -> str:
        """disabled | loading | ready | error (never blocks)."""
        if not self.settings.embeddings_enabled:
            return "disabled"
        if self._provider is not None:
            return "ready"
        if self._provider_error is not None:
            return "error"
        return "loading"

    @property
    def model_key(self) -> str | None:
        provider = self._load_provider()
        return f"{provider.name}:{provider.model}" if provider else None

    # -- embedding ---------------------------------------------------------

    @staticmethod
    def chunk_input(context: str, text: str) -> str:
        return f"{context}\n{text}" if context else text

    def pending_count(self) -> int:
        key = self.model_key
        if key is None:
            return 0
        with self.db.connect() as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM chunks c LEFT JOIN chunk_embeddings e "
                "ON e.chunk_rowid = c.id AND e.model = ? WHERE e.chunk_rowid IS NULL",
                (key,),
            ).fetchone()[0]

    def embed_pending(self, max_batches: int | None = None) -> int:
        """Embed chunks lacking a vector for the current model. Returns the number embedded."""
        provider = self._load_provider()
        if provider is None:
            return 0
        key = f"{provider.name}:{provider.model}"
        done = 0
        batches = 0
        with self._embed_lock:
            while max_batches is None or batches < max_batches:
                with self.db.connect() as conn:
                    rows = conn.execute(
                        "SELECT c.id, c.context, c.text FROM chunks c LEFT JOIN chunk_embeddings e "
                        "ON e.chunk_rowid = c.id AND e.model = ? WHERE e.chunk_rowid IS NULL "
                        "ORDER BY c.id LIMIT ?",
                        (key, self.settings.embeddings_batch_size),
                    ).fetchall()
                if not rows:
                    break
                vectors = provider.embed_documents([self.chunk_input(r["context"], r["text"]) for r in rows])
                vectors = _normalize(np.asarray(vectors, dtype=np.float32))
                with self.db.connect() as conn:
                    conn.executemany(
                        "INSERT OR REPLACE INTO chunk_embeddings(chunk_rowid, model, dim, vector) VALUES (?, ?, ?, ?)",
                        [
                            (r["id"], key, int(v.shape[0]), v.astype(np.float32).tobytes())
                            for r, v in zip(rows, vectors, strict=True)
                        ],
                    )
                    # Old-model vectors for these chunks are no longer needed
                    conn.execute("DELETE FROM chunk_embeddings WHERE model != ?", (key,))
                    Database.bump_counter(conn, "embedding_revision")
                done += len(rows)
                batches += 1
        if done:
            logger.info(f"Embedded {done} chunks")
        return done

    # -- search ------------------------------------------------------------

    def _vectors(self) -> _VectorCache | None:
        key_model = self.model_key
        if key_model is None:
            return None
        key = (self.db.get_index_revision(), self.db.get_counter("embedding_revision"), key_model)
        with self._cache_lock:
            if self._cache is not None and self._cache.key == key:
                return self._cache
            with self.db.connect() as conn:
                rows = conn.execute(
                    "SELECT e.chunk_rowid, e.dim, e.vector, d.source_id FROM chunk_embeddings e "
                    "JOIN chunks c ON c.id = e.chunk_rowid JOIN documents d ON d.doc_id = c.doc_id "
                    "WHERE e.model = ? ORDER BY e.chunk_rowid",
                    (key_model,),
                ).fetchall()
            if rows:
                dim = rows[0]["dim"]
                matrix = np.frombuffer(b"".join(r["vector"] for r in rows), dtype=np.float32).reshape(-1, dim)
            else:
                matrix = np.zeros((0, 1), dtype=np.float32)
            self._cache = _VectorCache(
                key=key,
                rowids=np.fromiter((r["chunk_rowid"] for r in rows), dtype=np.int64, count=len(rows)),
                sources=np.fromiter(
                    (UPLOADS_SOURCE if r["source_id"] is None else r["source_id"] for r in rows),
                    dtype=np.int64,
                    count=len(rows),
                ),
                matrix=matrix,
            )
            return self._cache

    def search(self, query: str, top_n: int, scope: AccessScope | None = None) -> list[tuple[int, float]]:
        """Top chunks by cosine similarity: list of (chunk_rowid, score)."""
        cache = self._vectors()
        provider = self._load_provider()
        if cache is None or provider is None or cache.matrix.shape[0] == 0:
            return []
        q = _normalize(np.asarray(provider.embed_query(query), dtype=np.float32))
        if q.shape[0] != cache.matrix.shape[1]:
            return []
        scores = cache.matrix @ q
        if scope is not None:
            mask = scope.mask(cache.sources)
            if mask is not None:
                scores = np.where(mask, scores, -np.inf)
        n = min(top_n, scores.shape[0])
        top = np.argpartition(-scores, n - 1)[:n]
        top = top[np.argsort(-scores[top])]
        # Absolute floor plus a cutoff relative to the best hit: a vector search always
        # returns *something*, and near-misses would otherwise pad every answer.
        threshold = self.settings.embeddings_min_score
        if top.size and np.isfinite(scores[top[0]]) and self.settings.embeddings_relative_cutoff > 0:
            threshold = max(threshold, float(scores[top[0]]) * self.settings.embeddings_relative_cutoff)
        return [(int(cache.rowids[i]), float(scores[i])) for i in top if scores[i] >= threshold]

    def stats(self) -> dict[str, Any]:
        """Status for /system and /health/detailed (never blocks on a model download)."""
        provider = self._provider
        with self.db.connect() as conn:
            stored = conn.execute("SELECT COUNT(*) FROM chunk_embeddings").fetchone()[0]
        return {
            "enabled": self.settings.embeddings_enabled,
            "state": self.state,
            "available": provider is not None,
            "provider": provider.name if provider else None,
            "model": provider.model if provider else self.settings.embeddings_model,
            "error": self._provider_error,
            "vectors": stored,
            "pending": self.pending_count() if provider else None,
        }


# ---------------------------------------------------------------------------
# Background worker
# ---------------------------------------------------------------------------


class EmbeddingWorker:
    """Embeds pending chunks in a background thread; ``kick()`` wakes it up early."""

    IDLE_SECONDS = 60

    def __init__(self, service: EmbeddingService):
        self.service = service
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        settings = self.service.settings
        if self._thread is None and settings.embeddings_enabled and settings.embeddings_background:
            self._thread = threading.Thread(target=self._run, name="nai-embeddings", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=10)
            self._thread = None

    def kick(self) -> None:
        self._wake.set()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                while not self._stop.is_set() and self.service.embed_pending(max_batches=8):
                    pass
            except Exception as e:
                logger.error(f"Embedding worker error: {e}")
            self._wake.wait(self.IDLE_SECONDS)
            self._wake.clear()


@lru_cache(maxsize=1)
def get_embedding_service() -> EmbeddingService:
    return EmbeddingService(get_settings(), get_db())


@lru_cache(maxsize=1)
def get_embedding_worker() -> EmbeddingWorker:
    return EmbeddingWorker(get_embedding_service())
