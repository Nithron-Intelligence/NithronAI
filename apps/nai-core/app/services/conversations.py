"""
nAI Core Conversation Store
Persistent multi-turn chat history (SQLite), scoped per user.
"""

import json
import uuid
from functools import lru_cache

from ..db import Database, get_db
from ..models.schemas import ChatMessage, Citation, ConversationSummary
from ..utils.timeutil import utc_now_iso

TITLE_MAX_CHARS = 80


class ConversationStore:
    def __init__(self, db: Database):
        self.db = db

    def create(self, user_id: str, title: str = "") -> str:
        conversation_id = str(uuid.uuid4())
        now = utc_now_iso()
        with self.db.connect() as conn:
            conn.execute(
                "INSERT INTO conversations(id, user_id, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (conversation_id, user_id, title[:TITLE_MAX_CHARS], now, now),
            )
        return conversation_id

    def exists(self, conversation_id: str, user_id: str) -> bool:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM conversations WHERE id = ? AND user_id = ?", (conversation_id, user_id)
            ).fetchone()
        return row is not None

    def add_message(
        self,
        conversation_id: str,
        message: ChatMessage,
        citations: list[Citation] | None = None,
    ) -> ChatMessage:
        timestamp = message.timestamp or utc_now_iso()
        with self.db.connect() as conn:
            conn.execute(
                "INSERT INTO messages(conversation_id, role, content, citations, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    conversation_id,
                    message.role,
                    message.content,
                    json.dumps([c.model_dump() for c in citations or []], ensure_ascii=False),
                    timestamp,
                ),
            )
            conn.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (timestamp, conversation_id))
        return ChatMessage(role=message.role, content=message.content, timestamp=timestamp)

    def get_messages(self, conversation_id: str, limit: int | None = None) -> list[ChatMessage]:
        """Messages in chronological order; ``limit`` keeps only the most recent ones."""
        query = "SELECT role, content, created_at FROM messages WHERE conversation_id = ? ORDER BY id DESC"
        params: tuple = (conversation_id,)
        if limit is not None:
            query += " LIMIT ?"
            params = (conversation_id, limit)
        with self.db.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [
            ChatMessage(role=r["role"], content=r["content"], timestamp=r["created_at"])
            for r in reversed(rows)
        ]

    def list_for_user(self, user_id: str) -> list[ConversationSummary]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT c.*, (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id) AS n "
                "FROM conversations c WHERE c.user_id = ? ORDER BY c.updated_at DESC",
                (user_id,),
            ).fetchall()
        return [
            ConversationSummary(
                conversation_id=r["id"],
                title=r["title"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
                message_count=r["n"],
            )
            for r in rows
        ]

    def delete(self, conversation_id: str, user_id: str) -> bool:
        with self.db.connect() as conn:
            cur = conn.execute(
                "DELETE FROM conversations WHERE id = ? AND user_id = ?", (conversation_id, user_id)
            )
            return cur.rowcount > 0


@lru_cache(maxsize=1)
def get_conversation_store() -> ConversationStore:
    return ConversationStore(get_db())
