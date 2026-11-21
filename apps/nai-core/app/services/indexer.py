"""
nAI Core Indexer Service
Document storage, text extraction, chunking and index management (SQLite-backed).
"""

import hashlib
import json
import os
import threading
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import UploadFile

from ..config import Settings, get_settings
from ..db import Database, get_db
from ..models.schemas import DocumentInfo, IngestFileResult
from ..utils.extractors import extract_text
from ..utils.logging import get_logger
from ..utils.text import chunk_text_semantic, normalize_text
from ..utils.timeutil import utc_now, utc_now_iso

logger = get_logger(__name__)


def compute_doc_id(content: bytes) -> str:
    """Document id: first 16 hex chars of the sha256 of the file content."""
    return hashlib.sha256(content).hexdigest()[:16]


def _safe_filename(name: str) -> str:
    base = os.path.basename(name.replace("\\", "/")) or "unknown"
    return "".join(c if c.isalnum() or c in ".-_" else "_" for c in base)


class IndexerService:
    """
    Handles file storage, text extraction, chunking, and the chunk index.

    Chunks are stored in SQLite. ``load_index()`` returns them as a list of dicts
    (doc_id, doc_path, chunk_id, text, metadata, created_at), cached in memory and
    refreshed whenever the database's index revision changes.
    """

    def __init__(self, settings: Settings, db: Database):
        self.settings = settings
        self.db = db
        os.makedirs(self.settings.docs_path, exist_ok=True)
        self._cache: list[dict[str, Any]] | None = None
        self._cache_revision: int = -1
        self._cache_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------

    async def ingest_file(self, file: UploadFile) -> IngestFileResult:
        """Ingest an uploaded file."""
        content = await file.read()
        return self.ingest_bytes(content, file.filename or "unknown")

    def ingest_bytes(
        self,
        content: bytes,
        filename: str,
        extra_metadata: dict[str, Any] | None = None,
    ) -> IngestFileResult:
        """
        Validate, store, extract, chunk and index one document.
        Never raises for per-file problems; returns a result with status error/skipped.
        """
        original_name = filename or "unknown"

        def result(status: str, message: str | None = None, **kw: Any) -> IngestFileResult:
            return IngestFileResult(
                filename=original_name,
                doc_id=kw.get("doc_id", ""),
                chunks=kw.get("chunks", 0),
                chars=kw.get("chars", 0),
                status=status,
                message=message,
            )

        if len(content) > self.settings.max_file_size_bytes:
            return result(
                "error",
                f"File too large: {len(content)} bytes (max: {self.settings.max_file_size_mb}MB)",
            )

        ext = Path(original_name).suffix.lower()
        if ext not in self.settings.allowed_extensions:
            return result(
                "error",
                f"Unsupported file type: {ext or '(none)'}. "
                f"Allowed: {', '.join(self.settings.allowed_extensions)}",
            )

        doc_id = compute_doc_id(content)
        if self.document_exists(doc_id):
            logger.info(f"Skipping duplicate: {original_name}")
            return result("skipped", "Document already indexed", doc_id=doc_id)

        saved_name = f"{utc_now().strftime('%Y%m%dT%H%M%S')}_{doc_id}_{_safe_filename(original_name)}"
        saved_path = os.path.join(self.settings.docs_path, saved_name)

        try:
            with open(saved_path, "wb") as f:
                f.write(content)

            text, metadata = extract_text(saved_path)
            text = normalize_text(text)
            if not text.strip():
                os.remove(saved_path)
                return result("skipped", "No text content extracted", doc_id=doc_id)

            chunks = chunk_text_semantic(text, max_chars=self.settings.chunk_size, overlap_sentences=1)

            doc_metadata = {
                **{k: v for k, v in metadata.items() if k != "error"},
                **(extra_metadata or {}),
            }
            self._store_document(
                doc_id=doc_id,
                filename=original_name,
                path=saved_name,
                file_type=ext,
                file_size=len(content),
                total_chars=len(text),
                metadata=doc_metadata,
                chunks=chunks,
            )
        except Exception as e:
            logger.error(f"Ingestion error for {original_name}: {e}")
            if os.path.exists(saved_path):
                try:
                    os.remove(saved_path)
                except OSError:
                    pass
            return result("error", f"Processing error: {e}", doc_id=doc_id)

        logger.info(f"Indexed: {original_name} -> {len(chunks)} chunks")
        return result("success", doc_id=doc_id, chunks=len(chunks), chars=len(text))

    def _store_document(
        self,
        *,
        doc_id: str,
        filename: str,
        path: str,
        file_type: str,
        file_size: int,
        total_chars: int,
        metadata: dict[str, Any],
        chunks: list[str],
    ) -> None:
        now = utc_now_iso()
        chunk_metadata = json.dumps({"original_filename": filename}, ensure_ascii=False)
        with self.db.connect() as conn:
            conn.execute(
                "INSERT INTO documents"
                "(doc_id, filename, path, file_type, file_size, total_chars, metadata, indexed_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    doc_id,
                    filename,
                    path,
                    file_type,
                    file_size,
                    total_chars,
                    json.dumps(metadata, ensure_ascii=False, default=str),
                    now,
                ),
            )
            conn.executemany(
                "INSERT INTO chunks(doc_id, chunk_id, text, metadata, created_at) VALUES (?, ?, ?, ?, ?)",
                [(doc_id, i, text, chunk_metadata, now) for i, text in enumerate(chunks)],
            )
            Database.bump_index_revision(conn)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    @property
    def revision(self) -> int:
        """Current index revision (changes whenever documents are added or removed)."""
        return self.db.get_index_revision()

    def document_exists(self, doc_id: str) -> bool:
        with self.db.connect() as conn:
            row = conn.execute("SELECT 1 FROM documents WHERE doc_id = ?", (doc_id,)).fetchone()
            return row is not None

    def load_index(self, force_reload: bool = False) -> list[dict[str, Any]]:
        """All chunks as dicts, cached until the index revision changes."""
        revision = self.revision
        with self._cache_lock:
            if not force_reload and self._cache is not None and revision == self._cache_revision:
                return self._cache

            with self.db.connect() as conn:
                rows = conn.execute(
                    "SELECT c.doc_id, d.path AS doc_path, c.chunk_id, c.text, c.metadata, c.created_at "
                    "FROM chunks c JOIN documents d ON d.doc_id = c.doc_id "
                    "ORDER BY c.id"
                ).fetchall()

            records = []
            for r in rows:
                metadata = json.loads(r["metadata"] or "{}")
                metadata["doc_id"] = r["doc_id"]
                records.append(
                    {
                        "doc_id": r["doc_id"],
                        "doc_path": r["doc_path"],
                        "chunk_id": r["chunk_id"],
                        "text": r["text"],
                        "metadata": metadata,
                        "created_at": r["created_at"],
                    }
                )
            self._cache = records
            self._cache_revision = revision
            logger.debug(f"Loaded index: {len(records)} chunks (revision {revision})")
            return records

    def get_chunks(self, doc_id: str) -> list[dict[str, Any]]:
        """Chunks of one document, ordered by chunk_id."""
        return sorted(
            (r for r in self.load_index() if r["doc_id"] == doc_id),
            key=lambda r: r["chunk_id"],
        )

    def invalidate_cache(self) -> None:
        with self._cache_lock:
            self._cache = None

    @staticmethod
    def _row_to_document(row: Any) -> DocumentInfo:
        return DocumentInfo(
            doc_id=row["doc_id"],
            filename=row["filename"],
            path=row["path"],
            chunk_count=row["chunk_count"],
            total_chars=row["total_chars"],
            file_size=row["file_size"],
            file_type=row["file_type"],
            indexed_at=row["indexed_at"],
            metadata=json.loads(row["metadata"] or "{}"),
        )

    _DOC_QUERY = (
        "SELECT d.*, (SELECT COUNT(*) FROM chunks c WHERE c.doc_id = d.doc_id) AS chunk_count "
        "FROM documents d"
    )

    def list_documents(self) -> list[DocumentInfo]:
        """All documents, newest first."""
        with self.db.connect() as conn:
            rows = conn.execute(f"{self._DOC_QUERY} ORDER BY d.indexed_at DESC").fetchall()
        return [self._row_to_document(r) for r in rows]

    def get_document(self, doc_id: str) -> DocumentInfo | None:
        with self.db.connect() as conn:
            row = conn.execute(f"{self._DOC_QUERY} WHERE d.doc_id = ?", (doc_id,)).fetchone()
        return self._row_to_document(row) if row else None

    def delete_document(self, doc_id: str) -> tuple[bool, int]:
        """Delete a document, its chunks and its stored file. Returns (found, chunks_removed)."""
        with self.db.connect() as conn:
            row = conn.execute("SELECT path FROM documents WHERE doc_id = ?", (doc_id,)).fetchone()
            if row is None:
                return False, 0
            chunks_removed = conn.execute(
                "SELECT COUNT(*) FROM chunks WHERE doc_id = ?", (doc_id,)
            ).fetchone()[0]
            conn.execute("DELETE FROM documents WHERE doc_id = ?", (doc_id,))
            Database.bump_index_revision(conn)
            stored_path = row["path"]

        full_path = os.path.realpath(os.path.join(self.settings.docs_path, stored_path))
        docs_root = os.path.realpath(self.settings.docs_path)
        if full_path.startswith(docs_root + os.sep) and os.path.exists(full_path):
            try:
                os.remove(full_path)
                logger.info(f"Deleted source file: {stored_path}")
            except OSError as e:
                logger.warning(f"Could not delete source file: {e}")

        logger.info(f"Deleted document {doc_id}: {chunks_removed} chunks")
        return True, chunks_removed

    def get_stats(self) -> dict[str, Any]:
        with self.db.connect() as conn:
            docs = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
            chunks, chars = conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(LENGTH(text)), 0) FROM chunks"
            ).fetchone()
        return {
            "total_documents": docs,
            "total_chunks": chunks,
            "total_characters": chars,
            "index_revision": self.revision,
        }


@lru_cache(maxsize=1)
def get_indexer() -> IndexerService:
    """Get the indexer service singleton."""
    return IndexerService(get_settings(), get_db())
