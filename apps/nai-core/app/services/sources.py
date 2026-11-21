"""
nAI Core Sources

A *source* is a folder on the NAS (e.g. an SMB share) that nAI indexes in place and
keeps in sync:
- an incremental scan compares each file's mtime/size (then content hash) with the index,
  re-indexes what changed and drops what disappeared;
- a file watcher (inotify via ``watchfiles``) applies changes within seconds;
- a periodic rescan catches anything the watcher missed (network filesystems, restarts).

Safety: source paths must resolve inside ``NAI_SOURCES_ALLOWED_ROOTS``; symlinks that
leave the source are ignored; hidden folders and Btrfs ``.snapshots`` are skipped so
snapshots don't duplicate every file.
"""

import fnmatch
import json
import os
import threading
import time
from collections.abc import Iterator
from functools import lru_cache
from typing import Any

from ..config import Settings, get_settings
from ..db import Database, get_db
from ..models.schemas import ScanResult, SourceCreate, SourceInfo, SourceUpdate
from ..utils.logging import get_logger
from ..utils.timeutil import utc_now_iso
from .indexer import IndexerService, get_indexer

logger = get_logger(__name__)

SKIP_DIRS = {".snapshots", ".snapshot", "@eaDir", "#recycle", ".Trash", "$RECYCLE.BIN", "lost+found"}
WATCH_DEBOUNCE_MS = 1500


class SourceError(ValueError):
    pass


def _within(path: str, root: str) -> bool:
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


class SourceService:
    def __init__(self, settings: Settings, db: Database, indexer: IndexerService):
        self.settings = settings
        self.db = db
        self.indexer = indexer
        self._scan_locks: dict[int, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def _validate_path(self, path: str) -> str:
        if not os.path.isabs(path):
            raise SourceError("Source path must be absolute")
        real = os.path.realpath(path)
        roots = [os.path.realpath(r) for r in self.settings.sources_allowed_roots]
        if not any(_within(real, root) for root in roots):
            raise SourceError(
                f"Source path must be inside one of: {', '.join(self.settings.sources_allowed_roots)}"
            )
        if not os.path.isdir(real):
            raise SourceError("Source path does not exist or is not a directory")
        if not os.access(real, os.R_OK | os.X_OK):
            raise SourceError("Source path is not readable by nAI")
        return real

    def _row_to_info(self, row: Any, include_path: bool = True) -> SourceInfo:
        return SourceInfo(
            id=row["id"],
            name=row["name"],
            path=row["path"] if include_path else None,
            recursive=bool(row["recursive"]),
            exclude_patterns=json.loads(row["exclude_patterns"] or "[]"),
            allowed_groups=json.loads(row["allowed_groups"] or "[]"),
            enabled=bool(row["enabled"]),
            created_at=row["created_at"],
            last_scan_started=row["last_scan_started"],
            last_scan_finished=row["last_scan_finished"],
            last_scan_status=row["last_scan_status"],
            last_error=row["last_error"],
            document_count=row["document_count"],
            scanning=self.is_scanning(row["id"]),
        )

    _QUERY = (
        "SELECT s.*, (SELECT COUNT(*) FROM documents d WHERE d.source_id = s.id AND d.total_chars > 0) "
        "AS document_count FROM sources s"
    )

    def list_sources(self, include_paths: bool = True) -> list[SourceInfo]:
        with self.db.connect() as conn:
            rows = conn.execute(f"{self._QUERY} ORDER BY s.name").fetchall()
        return [self._row_to_info(r, include_paths) for r in rows]

    def get(self, source_id: int, include_path: bool = True) -> SourceInfo | None:
        with self.db.connect() as conn:
            row = conn.execute(f"{self._QUERY} WHERE s.id = ?", (source_id,)).fetchone()
        return self._row_to_info(row, include_path) if row else None

    def create(self, data: SourceCreate) -> SourceInfo:
        real = self._validate_path(data.path)
        with self.db.connect() as conn:
            for row in conn.execute("SELECT name, path FROM sources").fetchall():
                if row["name"].lower() == data.name.lower():
                    raise SourceError("A source with this name already exists")
                if _within(real, row["path"]) or _within(row["path"], real):
                    raise SourceError(f"Overlaps with existing source '{row['name']}'")
            cur = conn.execute(
                "INSERT INTO sources(name, path, recursive, exclude_patterns, allowed_groups, enabled, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    data.name,
                    real,
                    int(data.recursive),
                    json.dumps(data.exclude_patterns),
                    json.dumps(sorted({g.strip() for g in data.allowed_groups if g.strip()})),
                    int(data.enabled),
                    utc_now_iso(),
                ),
            )
            source_id = int(cur.lastrowid or 0)
            Database.bump_index_revision(conn)  # source names are part of the cached index
        logger.info(f"Created source '{data.name}' -> {real}")
        info = self.get(source_id)
        assert info is not None
        return info

    def update(self, source_id: int, data: SourceUpdate) -> SourceInfo | None:
        fields: dict[str, Any] = {}
        if data.name is not None:
            fields["name"] = data.name
        if data.recursive is not None:
            fields["recursive"] = int(data.recursive)
        if data.exclude_patterns is not None:
            fields["exclude_patterns"] = json.dumps(data.exclude_patterns)
        if data.allowed_groups is not None:
            fields["allowed_groups"] = json.dumps(
                sorted({g.strip() for g in data.allowed_groups if g.strip()})
            )
        if data.enabled is not None:
            fields["enabled"] = int(data.enabled)
        if fields:
            assignments = ", ".join(f"{k} = ?" for k in fields)
            with self.db.connect() as conn:
                if "name" in fields:
                    clash = conn.execute(
                        "SELECT 1 FROM sources WHERE name = ? AND id != ?", (fields["name"], source_id)
                    ).fetchone()
                    if clash:
                        raise SourceError("A source with this name already exists")
                    old = conn.execute("SELECT name FROM sources WHERE id = ?", (source_id,)).fetchone()
                    if old is not None and old["name"] != fields["name"]:
                        self._rename_context(conn, source_id, old["name"], fields["name"])
                conn.execute(f"UPDATE sources SET {assignments} WHERE id = ?", (*fields.values(), source_id))
                Database.bump_index_revision(conn)
            if "name" in fields:
                self.indexer.notify_changed()  # re-embed the chunks whose context header changed
        return self.get(source_id)

    @staticmethod
    def _rename_context(conn: Any, source_id: int, old_name: str, new_name: str) -> None:
        """Chunk context headers start with 'Document: <source>/<path>': keep them in step with the name."""
        old_prefix = f"Document: {old_name}/"
        new_prefix = f"Document: {new_name}/"
        doc_filter = "doc_id IN (SELECT doc_id FROM documents WHERE source_id = ?)"
        conn.execute(
            "DELETE FROM chunk_embeddings WHERE chunk_rowid IN "
            f"(SELECT id FROM chunks WHERE {doc_filter} AND substr(context, 1, ?) = ?)",
            (source_id, len(old_prefix), old_prefix),
        )
        conn.execute(
            f"UPDATE chunks SET context = ? || substr(context, ?) WHERE {doc_filter} AND substr(context, 1, ?) = ?",
            (new_prefix, len(old_prefix) + 1, source_id, len(old_prefix), old_prefix),
        )

    def delete(self, source_id: int) -> bool:
        """Remove a source and its index entries. Files on disk are never touched."""
        with self.db.connect() as conn:
            conn.execute("DELETE FROM documents WHERE source_id = ?", (source_id,))
            cur = conn.execute("DELETE FROM sources WHERE id = ?", (source_id,))
            Database.bump_index_revision(conn)
        return cur.rowcount > 0

    # ------------------------------------------------------------------
    # Scanning
    # ------------------------------------------------------------------

    def _lock_for(self, source_id: int) -> threading.Lock:
        with self._locks_guard:
            return self._scan_locks.setdefault(source_id, threading.Lock())

    def is_scanning(self, source_id: int) -> bool:
        lock = self._scan_locks.get(source_id)
        return bool(lock and lock.locked())

    def _excluded(self, rel_path: str, patterns: list[str]) -> bool:
        name = os.path.basename(rel_path)
        return any(fnmatch.fnmatch(rel_path, p) or fnmatch.fnmatch(name, p) for p in patterns)

    def _walk(self, root: str, recursive: bool, patterns: list[str]) -> Iterator[str]:
        """Yield relative paths of candidate files."""
        extensions = self.indexer.extensions
        stack = [""]
        while stack:
            rel_dir = stack.pop()
            try:
                entries = list(os.scandir(os.path.join(root, rel_dir)))
            except OSError as e:
                logger.warning(f"Cannot list {os.path.join(root, rel_dir)}: {e}")
                continue
            for entry in entries:
                rel = os.path.join(rel_dir, entry.name) if rel_dir else entry.name
                if entry.name.startswith(".") or entry.name in SKIP_DIRS:
                    continue
                if self._excluded(rel, patterns):
                    continue
                try:
                    if entry.is_symlink():
                        target = os.path.realpath(entry.path)
                        if not _within(target, root) or os.path.isdir(target):
                            continue  # never follow links out of the source or into directories
                    if entry.is_dir(follow_symlinks=False):
                        if recursive:
                            stack.append(rel)
                    elif os.path.splitext(entry.name)[1].lower() in extensions:
                        yield rel
                except OSError:
                    continue

    def _row(self, source_id: int) -> Any:
        with self.db.connect() as conn:
            return conn.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()

    def _set_status(self, source_id: int, **fields: Any) -> None:
        assignments = ", ".join(f"{k} = ?" for k in fields)
        with self.db.connect() as conn:
            conn.execute(f"UPDATE sources SET {assignments} WHERE id = ?", (*fields.values(), source_id))

    def scan(self, source_id: int) -> ScanResult:
        """Incrementally sync one source with the index. Concurrent scans of a source are skipped."""
        lock = self._lock_for(source_id)
        if not lock.acquire(blocking=False):
            raise SourceError("A scan of this source is already running")
        started = time.monotonic()
        result = ScanResult(source_id=source_id)
        try:
            row = self._row(source_id)
            if row is None:
                raise SourceError("Source not found")
            root = row["path"]
            self._set_status(
                source_id, last_scan_started=utc_now_iso(), last_scan_status="scanning", last_error=None
            )
            if not os.path.isdir(root):
                raise SourceError(f"Source folder is missing: {root}")

            patterns = json.loads(row["exclude_patterns"] or "[]")
            known = self.indexer.source_file_states(source_id)
            seen: set[str] = set()
            for rel in self._walk(root, bool(row["recursive"]), patterns):
                seen.add(rel)
                outcome = self.indexer.index_source_file(source_id, row["name"], root, rel, known.get(rel))
                if outcome == "indexed":
                    result.indexed += 1
                elif outcome == "unchanged":
                    result.unchanged += 1
                elif outcome == "skipped":
                    result.skipped += 1
                else:
                    result.errors += 1

            for rel in known.keys() - seen:
                if self.indexer.remove_source_file(source_id, rel):
                    result.removed += 1

            result.seconds = round(time.monotonic() - started, 2)
            self._set_status(source_id, last_scan_finished=utc_now_iso(), last_scan_status="ok")
            logger.info(
                f"Scanned '{row['name']}': {result.indexed} indexed, {result.unchanged} unchanged, "
                f"{result.removed} removed, {result.skipped} skipped, {result.errors} errors ({result.seconds}s)"
            )
            return result
        except SourceError as e:
            if self._row(source_id) is not None:
                self._set_status(source_id, last_scan_status="error", last_error=str(e))
            raise
        except Exception as e:
            logger.error(f"Scan of source {source_id} failed: {e}")
            self._set_status(source_id, last_scan_status="error", last_error=str(e))
            raise
        finally:
            lock.release()

    def scan_all(self) -> None:
        for source in self.list_sources():
            if source.enabled and not self.is_scanning(source.id):
                try:
                    self.scan(source.id)
                except Exception as e:
                    logger.warning(f"Scan of '{source.name}' failed: {e}")

    def apply_changes(self, source_id: int, changed_paths: set[str]) -> None:
        """Apply file-watcher events: index created/modified files, drop deleted ones."""
        row = self._row(source_id)
        if row is None or not row["enabled"]:
            return
        root = row["path"]
        patterns = json.loads(row["exclude_patterns"] or "[]")
        extensions = self.indexer.extensions
        known = self.indexer.source_file_states(source_id)
        for full in changed_paths:
            real = os.path.realpath(full) if os.path.exists(full) else os.path.abspath(full)
            if not _within(real, root):
                continue
            rel = os.path.relpath(full, root)
            parts = rel.split(os.sep)
            if any(p.startswith(".") or p in SKIP_DIRS for p in parts) or self._excluded(rel, patterns):
                continue
            if not row["recursive"] and len(parts) > 1:
                continue
            if os.path.isfile(full):
                if os.path.splitext(full)[1].lower() in extensions:
                    self.indexer.index_source_file(source_id, row["name"], root, rel, known.get(rel))
            elif not os.path.exists(full):
                if not self.indexer.remove_source_file(source_id, rel):
                    self.indexer.remove_source_prefix(source_id, rel)  # a whole folder went away


# ---------------------------------------------------------------------------
# Background: periodic rescans + file watcher
# ---------------------------------------------------------------------------


class SourceManager:
    def __init__(self, service: SourceService):
        self.service = service
        self.settings = service.settings
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

    def start(self) -> None:
        if not self.settings.sources_background or self._threads:
            return
        self._stop.clear()
        self._spawn(self._periodic, "nai-sources-scan")
        if self.settings.sources_watch:
            try:
                import watchfiles  # noqa: F401

                self._spawn(self._watch, "nai-sources-watch")
            except ImportError:
                logger.info("watchfiles not installed: relying on periodic rescans")

    def _spawn(self, target: Any, name: str) -> None:
        thread = threading.Thread(target=target, name=name, daemon=True)
        thread.start()
        self._threads.append(thread)

    def stop(self) -> None:
        self._stop.set()
        for thread in self._threads:
            thread.join(timeout=10)
        self._threads = []

    def _periodic(self) -> None:
        # Initial sync shortly after startup, then every interval
        if self._stop.wait(5):
            return
        while not self._stop.is_set():
            self.service.scan_all()
            self._stop.wait(self.settings.sources_scan_interval_seconds)

    def _watch(self) -> None:
        from watchfiles import watch

        while not self._stop.is_set():
            sources = [
                s for s in self.service.list_sources() if s.enabled and s.path and os.path.isdir(s.path)
            ]
            if not sources:
                self._stop.wait(30)
                continue
            roots: dict[str, int] = {s.path: s.id for s in sources if s.path}
            signature = sorted(roots.items())
            try:
                for changes in watch(
                    *roots.keys(),
                    stop_event=self._stop,
                    debounce=WATCH_DEBOUNCE_MS,
                    rust_timeout=30_000,
                    yield_on_timeout=True,
                    recursive=True,
                ):
                    by_source: dict[int, set[str]] = {}
                    for _, path in changes:
                        for root, source_id in roots.items():
                            if _within(path, root):
                                by_source.setdefault(source_id, set()).add(path)
                    for source_id, paths in by_source.items():
                        try:
                            self.service.apply_changes(source_id, paths)
                        except Exception as e:
                            logger.warning(f"Applying file changes failed: {e}")
                    current = sorted(
                        (s.path, s.id)
                        for s in self.service.list_sources()
                        if s.enabled and s.path and os.path.isdir(s.path)
                    )
                    if current != signature:
                        break  # sources changed: restart the watcher with the new set
            except Exception as e:
                logger.warning(f"File watcher stopped ({e}); retrying in 30s")
                self._stop.wait(30)


@lru_cache(maxsize=1)
def get_source_service() -> SourceService:
    return SourceService(get_settings(), get_db(), get_indexer())


@lru_cache(maxsize=1)
def get_source_manager() -> SourceManager:
    return SourceManager(get_source_service())
