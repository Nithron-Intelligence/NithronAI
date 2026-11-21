"""
nAI Core Indexer Service

Extracts, chunks and stores documents in SQLite. Two kinds of documents:
- **Uploads**: bytes are copied to ``<data>/docs`` (doc_id = content hash).
- **Source files**: files inside a configured source folder, indexed *in place*
  (never copied). doc_id is derived from (source, relative path), so it stays stable
  when the file changes; ``content_hash`` + ``mtime`` drive incremental re-indexing.
"""

import hashlib
import json
import os
import threading
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from fastapi import UploadFile

from ..config import Settings, get_settings
from ..db import Database, get_db
from ..models.schemas import DocumentInfo, IngestFileResult
from ..utils.extractors import extract, supported_extensions
from ..utils.logging import get_logger
from ..utils.text import chunk_sections, normalize_text
from ..utils.timeutil import utc_now, utc_now_iso
from .access import FULL_ACCESS, AccessScope

logger = get_logger(__name__)

IngestStatus = Literal["success", "skipped", "error"]


def compute_doc_id(content: bytes) -> str:
    """Upload document id: first 16 hex chars of the sha256 of the content."""
    return hashlib.sha256(content).hexdigest()[:16]


def source_doc_id(source_id: int, rel_path: str) -> str:
    """Source document id: stable per (source, path)."""
    return "s" + hashlib.sha256(f"{source_id}:{rel_path}".encode()).hexdigest()[:15]


def _safe_filename(name: str) -> str:
    base = os.path.basename(name.replace("\\", "/")) or "unknown"
    return "".join(c if c.isalnum() or c in ".-_" else "_" for c in base)


@dataclass
class SourceFileState:
    doc_id: str
    mtime: float | None
    size: int
    content_hash: str


class IndexerService:
    def __init__(self, settings: Settings, db: Database):
        self.settings = settings
        self.db = db
        os.makedirs(self.settings.docs_path, exist_ok=True)
        self._cache: list[dict[str, Any]] | None = None
        self._cache_revision: int = -1
        self._cache_lock = threading.Lock()
        self._listeners: list[Callable[[], None]] = []

    # ------------------------------------------------------------------
    # Change notification (e.g. the embedding worker subscribes)
    # ------------------------------------------------------------------

    def add_listener(self, callback: Callable[[], None]) -> None:
        if callback not in self._listeners:
            self._listeners.append(callback)

    def notify_changed(self) -> None:
        """Tell listeners (e.g. the embedding worker) that chunks changed outside the indexer."""
        self._notify()

    def _notify(self) -> None:
        for callback in self._listeners:
            try:
                callback()
            except Exception as e:
                logger.warning(f"Index listener failed: {e}")

    @property
    def extensions(self) -> set[str]:
        return supported_extensions(self.settings.allowed_extensions, self.settings.ocr_enabled)

    # ------------------------------------------------------------------
    # Core: extract + chunk + store
    # ------------------------------------------------------------------

    def _extract_and_store(
        self,
        file_path: str,
        *,
        doc_id: str,
        filename: str,
        stored_path: str,
        display_path: str,
        file_type: str,
        file_size: int,
        content_hash: str,
        source_id: int | None = None,
        mtime: float | None = None,
        owner_id: str | None = None,
        extra_metadata: dict[str, Any] | None = None,
    ) -> tuple[int, int, str | None]:
        """Returns (chunks, chars, skip_reason). Replaces any existing rows for doc_id."""
        extracted = extract(
            file_path, ocr=self.settings.ocr_enabled, ocr_languages=self.settings.ocr_languages
        )
        for section in extracted.sections:
            section.text = normalize_text(section.text)
        extracted.sections = [s for s in extracted.sections if s.text]

        if not extracted.sections:
            reason = extracted.metadata.get("error") or "No text content extracted"
            return 0, 0, str(reason)

        drafts = chunk_sections(
            extracted.sections,
            display_path=display_path,
            title=extracted.metadata.get("title"),
            max_chars=self.settings.chunk_size,
        )
        total_chars = sum(len(s.text) for s in extracted.sections)
        metadata = {
            **{k: v for k, v in extracted.metadata.items() if k != "error"},
            **(extra_metadata or {}),
        }
        now = utc_now_iso()
        with self.db.connect() as conn:
            conn.execute("DELETE FROM documents WHERE doc_id = ?", (doc_id,))
            conn.execute(
                "INSERT INTO documents(doc_id, filename, path, file_type, file_size, total_chars, metadata, "
                "indexed_at, source_id, mtime, content_hash, owner_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    doc_id,
                    filename,
                    stored_path,
                    file_type,
                    file_size,
                    total_chars,
                    json.dumps(metadata, ensure_ascii=False, default=str),
                    now,
                    source_id,
                    mtime,
                    content_hash,
                    owner_id,
                ),
            )
            conn.executemany(
                "INSERT INTO chunks(doc_id, chunk_id, text, metadata, created_at, context, page) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        doc_id,
                        i,
                        d.text,
                        json.dumps({"heading": d.heading} if d.heading else {}, ensure_ascii=False),
                        now,
                        d.context,
                        d.page,
                    )
                    for i, d in enumerate(drafts)
                ],
            )
            Database.bump_index_revision(conn)
        self._notify()
        return len(drafts), total_chars, None

    # ------------------------------------------------------------------
    # Uploads
    # ------------------------------------------------------------------

    async def ingest_file(self, file: UploadFile, owner_id: str | None = None) -> IngestFileResult:
        content = await file.read()
        return self.ingest_bytes(content, file.filename or "unknown", owner_id=owner_id)

    def ingest_bytes(
        self,
        content: bytes,
        filename: str,
        extra_metadata: dict[str, Any] | None = None,
        owner_id: str | None = None,
    ) -> IngestFileResult:
        """Validate, store, extract, chunk and index an uploaded document."""
        original_name = filename or "unknown"

        def result(status: IngestStatus, message: str | None = None, **kw: Any) -> IngestFileResult:
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
        if ext not in self.extensions:
            return result(
                "error",
                f"Unsupported file type: {ext or '(none)'}. Allowed: {', '.join(sorted(self.extensions))}",
            )

        doc_id = compute_doc_id(content)
        if self.document_exists(doc_id):
            return result("skipped", "Document already indexed", doc_id=doc_id)

        saved_name = f"{utc_now().strftime('%Y%m%dT%H%M%S')}_{doc_id}_{_safe_filename(original_name)}"
        saved_path = os.path.join(self.settings.docs_path, saved_name)
        try:
            with open(saved_path, "wb") as f:
                f.write(content)
            chunks, chars, skip_reason = self._extract_and_store(
                saved_path,
                doc_id=doc_id,
                filename=original_name,
                stored_path=saved_name,
                display_path=original_name,
                file_type=ext,
                file_size=len(content),
                content_hash=hashlib.sha256(content).hexdigest(),
                owner_id=owner_id,
                extra_metadata={"original_filename": original_name, **(extra_metadata or {})},
            )
        except Exception as e:
            logger.error(f"Ingestion error for {original_name}: {e}")
            self._remove_quietly(saved_path)
            return result("error", f"Processing error: {e}", doc_id=doc_id)

        if skip_reason:
            self._remove_quietly(saved_path)
            return result("skipped", skip_reason, doc_id=doc_id)

        logger.info(f"Indexed upload: {original_name} -> {chunks} chunks")
        return result("success", doc_id=doc_id, chunks=chunks, chars=chars)

    @staticmethod
    def _remove_quietly(path: str) -> None:
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            pass

    # ------------------------------------------------------------------
    # Source files (indexed in place)
    # ------------------------------------------------------------------

    def source_file_states(self, source_id: int) -> dict[str, SourceFileState]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT doc_id, path, mtime, file_size, content_hash FROM documents WHERE source_id = ?",
                (source_id,),
            ).fetchall()
        return {
            r["path"]: SourceFileState(r["doc_id"], r["mtime"], r["file_size"], r["content_hash"])
            for r in rows
        }

    def index_source_file(
        self,
        source_id: int,
        source_name: str,
        root: str,
        rel_path: str,
        known: SourceFileState | None = None,
    ) -> str:
        """
        Index (or re-index) one file of a source if it changed.
        Returns one of: unchanged, indexed, skipped, error.
        """
        full_path = os.path.join(root, rel_path)
        try:
            st = os.stat(full_path)
        except OSError:
            return "error"

        if known and known.mtime == st.st_mtime and known.size == st.st_size:
            return "unchanged"
        if st.st_size > self.settings.max_file_size_bytes:
            self.remove_source_file(source_id, rel_path)
            return "skipped"

        try:
            with open(full_path, "rb") as f:
                content = f.read()
        except OSError as e:
            logger.warning(f"Cannot read {full_path}: {e}")
            return "error"

        content_hash = hashlib.sha256(content).hexdigest()
        doc_id = source_doc_id(source_id, rel_path)
        if known and known.content_hash == content_hash:
            with self.db.connect() as conn:  # touched but identical: just remember the new mtime
                conn.execute("UPDATE documents SET mtime = ? WHERE doc_id = ?", (st.st_mtime, doc_id))
            return "unchanged"

        try:
            _, _, skip_reason = self._extract_and_store(
                full_path,
                doc_id=doc_id,
                filename=os.path.basename(rel_path),
                stored_path=rel_path,
                display_path=f"{source_name}/{rel_path}",
                file_type=Path(rel_path).suffix.lower(),
                file_size=st.st_size,
                content_hash=content_hash,
                source_id=source_id,
                mtime=st.st_mtime,
            )
        except Exception as e:
            logger.error(f"Indexing failed for {full_path}: {e}")
            return "error"

        if skip_reason:
            # Keep a row so unchanged unreadable files aren't retried on every scan
            with self.db.connect() as conn:
                conn.execute("DELETE FROM documents WHERE doc_id = ?", (doc_id,))
                conn.execute(
                    "INSERT INTO documents(doc_id, filename, path, file_type, file_size, total_chars, metadata, "
                    "indexed_at, source_id, mtime, content_hash) VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?)",
                    (
                        doc_id,
                        os.path.basename(rel_path),
                        rel_path,
                        Path(rel_path).suffix.lower(),
                        st.st_size,
                        json.dumps({"skipped": skip_reason}),
                        utc_now_iso(),
                        source_id,
                        st.st_mtime,
                        content_hash,
                    ),
                )
                Database.bump_index_revision(conn)
            return "skipped"
        return "indexed"

    def remove_source_file(self, source_id: int, rel_path: str) -> bool:
        with self.db.connect() as conn:
            cur = conn.execute(
                "DELETE FROM documents WHERE source_id = ? AND path = ?", (source_id, rel_path)
            )
            if cur.rowcount:
                Database.bump_index_revision(conn)
        return cur.rowcount > 0

    def remove_source_prefix(self, source_id: int, rel_dir: str) -> int:
        """Remove every document under a directory (used when a folder is deleted)."""
        prefix = rel_dir.rstrip("/") + "/"
        with self.db.connect() as conn:
            cur = conn.execute(
                "DELETE FROM documents WHERE source_id = ? AND substr(path, 1, ?) = ?",
                (source_id, len(prefix), prefix),
            )
            if cur.rowcount:
                Database.bump_index_revision(conn)
        return cur.rowcount

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    @property
    def revision(self) -> int:
        return self.db.get_index_revision()

    def document_exists(self, doc_id: str) -> bool:
        with self.db.connect() as conn:
            return conn.execute("SELECT 1 FROM documents WHERE doc_id = ?", (doc_id,)).fetchone() is not None

    def load_index(self, force_reload: bool = False) -> list[dict[str, Any]]:
        """All chunks (with document/source info), cached until the index revision changes."""
        revision = self.revision
        with self._cache_lock:
            if not force_reload and self._cache is not None and revision == self._cache_revision:
                return self._cache

            with self.db.connect() as conn:
                rows = conn.execute(
                    "SELECT c.id, c.doc_id, d.path AS doc_path, d.filename, d.source_id, s.name AS source_name, "
                    "c.chunk_id, c.text, c.context, c.page, c.metadata, c.created_at "
                    "FROM chunks c JOIN documents d ON d.doc_id = c.doc_id "
                    "LEFT JOIN sources s ON s.id = d.source_id ORDER BY c.id"
                ).fetchall()

            records = []
            for r in rows:
                metadata = json.loads(r["metadata"] or "{}")
                metadata.setdefault("original_filename", r["filename"])
                metadata["doc_id"] = r["doc_id"]
                records.append(
                    {
                        "id": r["id"],
                        "doc_id": r["doc_id"],
                        "doc_path": r["doc_path"],
                        "filename": r["filename"],
                        "source_id": r["source_id"],
                        "source_name": r["source_name"],
                        "chunk_id": r["chunk_id"],
                        "text": r["text"],
                        "context": r["context"],
                        "page": r["page"],
                        "metadata": metadata,
                        "created_at": r["created_at"],
                    }
                )
            self._cache = records
            self._cache_revision = revision
            return records

    def get_chunks(self, doc_id: str) -> list[dict[str, Any]]:
        return sorted((r for r in self.load_index() if r["doc_id"] == doc_id), key=lambda r: r["chunk_id"])

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
            source_id=row["source_id"],
            source_name=row["source_name"],
            metadata=json.loads(row["metadata"] or "{}"),
        )

    _DOC_QUERY = (
        "SELECT d.*, s.name AS source_name, "
        "(SELECT COUNT(*) FROM chunks c WHERE c.doc_id = d.doc_id) AS chunk_count "
        "FROM documents d LEFT JOIN sources s ON s.id = d.source_id"
    )

    def list_documents(self, scope: AccessScope = FULL_ACCESS) -> list[DocumentInfo]:
        with self.db.connect() as conn:
            rows = conn.execute(
                f"{self._DOC_QUERY} WHERE d.total_chars > 0 ORDER BY d.indexed_at DESC"
            ).fetchall()
        return [self._row_to_document(r) for r in rows if scope.allows(r["source_id"])]

    def get_document(self, doc_id: str, scope: AccessScope = FULL_ACCESS) -> DocumentInfo | None:
        with self.db.connect() as conn:
            row = conn.execute(f"{self._DOC_QUERY} WHERE d.doc_id = ?", (doc_id,)).fetchone()
        if row is None or not scope.allows(row["source_id"]):
            return None
        return self._row_to_document(row)

    def document_file_path(self, doc_id: str, scope: AccessScope = FULL_ACCESS) -> str | None:
        """Absolute path of the original file, if it is accessible and still exists."""
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT d.path, d.source_id, s.path AS root FROM documents d "
                "LEFT JOIN sources s ON s.id = d.source_id WHERE d.doc_id = ?",
                (doc_id,),
            ).fetchone()
        if row is None or not scope.allows(row["source_id"]):
            return None
        root = row["root"] if row["source_id"] is not None else self.settings.docs_path
        full = os.path.realpath(os.path.join(root, row["path"]))
        if not full.startswith(os.path.realpath(root) + os.sep) or not os.path.isfile(full):
            return None
        return full

    def delete_document(self, doc_id: str) -> tuple[bool, int]:
        """Delete an uploaded document (row, chunks, stored file). Returns (found, chunks_removed)."""
        with self.db.connect() as conn:
            row = conn.execute("SELECT path, source_id FROM documents WHERE doc_id = ?", (doc_id,)).fetchone()
            if row is None:
                return False, 0
            if row["source_id"] is not None:
                raise ValueError(
                    "Documents from a source are managed by the source; exclude or remove the file instead"
                )
            chunks_removed = conn.execute(
                "SELECT COUNT(*) FROM chunks WHERE doc_id = ?", (doc_id,)
            ).fetchone()[0]
            conn.execute("DELETE FROM documents WHERE doc_id = ?", (doc_id,))
            Database.bump_index_revision(conn)
            stored_path = row["path"]

        full_path = os.path.realpath(os.path.join(self.settings.docs_path, stored_path))
        if full_path.startswith(os.path.realpath(self.settings.docs_path) + os.sep):
            self._remove_quietly(full_path)
        logger.info(f"Deleted document {doc_id}: {chunks_removed} chunks")
        return True, chunks_removed

    def get_stats(self) -> dict[str, Any]:
        with self.db.connect() as conn:
            docs = conn.execute("SELECT COUNT(*) FROM documents WHERE total_chars > 0").fetchone()[0]
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
    return IndexerService(get_settings(), get_db())
