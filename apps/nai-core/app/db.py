"""
nAI Core Database
SQLite storage for documents, chunks, users and conversations.

One connection is opened per operation (cheap for SQLite) so the module is safe to use
from FastAPI's threadpool. WAL mode allows concurrent readers while a writer is active.
"""

import json
import os
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache
from typing import Any

from .config import Settings, get_settings
from .utils.logging import get_logger
from .utils.timeutil import utc_now_iso

logger = get_logger(__name__)

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS documents (
    doc_id      TEXT PRIMARY KEY,
    filename    TEXT NOT NULL,
    path        TEXT NOT NULL,
    file_type   TEXT NOT NULL DEFAULT '',
    file_size   INTEGER NOT NULL DEFAULT 0,
    total_chars INTEGER NOT NULL DEFAULT 0,
    metadata    TEXT NOT NULL DEFAULT '{}',
    indexed_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chunks (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id     TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
    chunk_id   INTEGER NOT NULL,
    text       TEXT NOT NULL,
    metadata   TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    UNIQUE (doc_id, chunk_id)
);

CREATE TABLE IF NOT EXISTS users (
    id            TEXT PRIMARY KEY,
    username      TEXT NOT NULL UNIQUE COLLATE NOCASE,
    email         TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    is_active     INTEGER NOT NULL DEFAULT 1,
    is_admin      INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conversations (
    id         TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL,
    title      TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_conversations_user ON conversations(user_id, updated_at);

CREATE TABLE IF NOT EXISTS messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL,
    content         TEXT NOT NULL,
    citations       TEXT NOT NULL DEFAULT '[]',
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id, id);
"""


class Database:
    """Thin wrapper around a SQLite file."""

    def __init__(self, path: str):
        self.path = path
        self._init_lock = threading.Lock()
        self._initialized = False

    def _open(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 30000")
        return conn

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """Open a connection; commits on success, rolls back on error."""
        self.initialize()
        conn = self._open()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def initialize(self) -> None:
        """Create the schema (idempotent)."""
        if self._initialized:
            return
        with self._init_lock:
            if self._initialized:
                return
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            conn = self._open()
            try:
                conn.execute("PRAGMA journal_mode = WAL")
                conn.executescript(SCHEMA)
                conn.execute(
                    "INSERT OR IGNORE INTO meta(key, value) VALUES ('schema_version', ?)",
                    (str(SCHEMA_VERSION),),
                )
                conn.execute("INSERT OR IGNORE INTO meta(key, value) VALUES ('index_revision', '0')")
                conn.commit()
            finally:
                conn.close()
            self._initialized = True

    # ------------------------------------------------------------------
    # Index revision: bumped on every document change so in-memory caches
    # (chunk list, BM25 index) know when to rebuild, even across workers.
    # ------------------------------------------------------------------

    def get_index_revision(self) -> int:
        with self.connect() as conn:
            row = conn.execute("SELECT value FROM meta WHERE key = 'index_revision'").fetchone()
            return int(row["value"]) if row else 0

    @staticmethod
    def bump_index_revision(conn: sqlite3.Connection) -> None:
        conn.execute(
            "UPDATE meta SET value = CAST(CAST(value AS INTEGER) + 1 AS TEXT) WHERE key = 'index_revision'"
        )


def migrate_legacy_files(db: Database, settings: Settings) -> None:
    """
    Import data written by nAI <= 0.2 (index.jsonl and users.json) into SQLite.
    The legacy files are renamed to *.migrated afterwards so this runs only once.
    """
    _migrate_legacy_index(db, settings.index_file)
    _migrate_legacy_users(db, os.path.join(settings.data_path, "users.json"))


def _migrate_legacy_index(db: Database, index_file: str) -> None:
    if not os.path.exists(index_file):
        return

    docs: dict[str, dict[str, Any]] = {}
    with open(index_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            metadata = record.get("metadata") or {}
            # In 0.2 the content hash lived in metadata.doc_id; the top-level doc_id was a
            # hash of the path. The content hash is the canonical id from now on.
            doc_id = metadata.get("doc_id") or record.get("doc_id")
            if not doc_id:
                continue
            doc = docs.setdefault(
                doc_id,
                {
                    "path": record.get("doc_path", ""),
                    "filename": metadata.get("original_filename")
                    or os.path.basename(record.get("doc_path", "")),
                    "file_type": metadata.get("extension") or os.path.splitext(record.get("doc_path", ""))[1],
                    "metadata": metadata,
                    "indexed_at": record.get("created_at") or utc_now_iso(),
                    "chunks": [],
                },
            )
            doc["chunks"].append(record)

    with db.connect() as conn:
        for doc_id, doc in docs.items():
            total_chars = sum(len(c.get("text", "")) for c in doc["chunks"])
            conn.execute(
                "INSERT OR IGNORE INTO documents"
                "(doc_id, filename, path, file_type, total_chars, metadata, indexed_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    doc_id,
                    doc["filename"],
                    doc["path"],
                    doc["file_type"],
                    total_chars,
                    json.dumps(doc["metadata"], ensure_ascii=False),
                    doc["indexed_at"],
                ),
            )
            for c in doc["chunks"]:
                conn.execute(
                    "INSERT OR IGNORE INTO chunks(doc_id, chunk_id, text, metadata, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        doc_id,
                        int(c.get("chunk_id", 0)),
                        c.get("text", ""),
                        json.dumps(c.get("metadata") or {}, ensure_ascii=False),
                        c.get("created_at") or utc_now_iso(),
                    ),
                )
        Database.bump_index_revision(conn)

    os.replace(index_file, index_file + ".migrated")
    logger.info(f"Migrated legacy index: {len(docs)} documents")


def _migrate_legacy_users(db: Database, users_file: str) -> None:
    if not os.path.exists(users_file):
        return
    try:
        with open(users_file, encoding="utf-8") as f:
            users = json.load(f)
    except (OSError, json.JSONDecodeError):
        logger.warning("Could not read legacy users.json; skipping migration")
        return

    with db.connect() as conn:
        for u in users.values():
            conn.execute(
                "INSERT OR IGNORE INTO users"
                "(id, username, email, password_hash, is_active, is_admin, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    u["id"],
                    u["username"],
                    u["email"],
                    u["password_hash"],
                    int(u.get("is_active", True)),
                    int(u.get("is_admin", False)),
                    u.get("created_at") or utc_now_iso(),
                ),
            )

    os.replace(users_file, users_file + ".migrated")
    logger.info(f"Migrated legacy users: {len(users)} users")


@lru_cache(maxsize=1)
def get_db() -> Database:
    """Get the database singleton (schema created and legacy data migrated on first use)."""
    settings = get_settings()
    db = Database(settings.db_file)
    db.initialize()
    migrate_legacy_files(db, settings)
    return db
