"""
nAI Core Access Control

Who may see which documents:
- Admins (and the built-in anonymous admin when auth is disabled) see everything.
- Uploaded documents (no source) are visible to every signed-in user.
- Documents from a source are visible when the source has no ``allowed_groups``, or
  when the user belongs to one of them.

Search applies the scope *before* ranking, so restricted users still get a full top-k.
"""

import json
from dataclasses import dataclass

import numpy as np

from ..db import Database
from ..models.schemas import User

UPLOADS_SOURCE = -1  # value used for "no source" in per-chunk numpy arrays


@dataclass(frozen=True)
class AccessScope:
    """The set of documents a request may see."""

    all_sources: bool
    source_ids: frozenset[int] = frozenset()
    uploads: bool = True

    def allows(self, source_id: int | None) -> bool:
        if source_id is None:
            return self.uploads
        return self.all_sources or source_id in self.source_ids

    def mask(self, sources: np.ndarray) -> np.ndarray | None:
        """Boolean mask over a per-chunk source-id array (None = everything allowed)."""
        if self.all_sources and self.uploads:
            return None
        if self.all_sources:
            return sources != UPLOADS_SOURCE
        allowed = np.isin(sources, np.fromiter(self.source_ids, dtype=np.int64, count=len(self.source_ids)))
        if self.uploads:
            allowed |= sources == UPLOADS_SOURCE
        return allowed

    def narrow(self, source_ids: list[int] | None, include_uploads: bool = True) -> "AccessScope":
        """Further restrict the scope to the sources a request asked for."""
        if source_ids is None:
            return AccessScope(self.all_sources, self.source_ids, self.uploads and include_uploads)
        requested = frozenset(source_ids)
        allowed = requested if self.all_sources else requested & self.source_ids
        return AccessScope(False, allowed, self.uploads and include_uploads)


FULL_ACCESS = AccessScope(all_sources=True)


def user_groups(db: Database, user_id: str) -> list[str]:
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT group_name FROM user_groups WHERE user_id = ? ORDER BY group_name", (user_id,)
        ).fetchall()
    return [r["group_name"] for r in rows]


def scope_for_user(db: Database, user: User) -> AccessScope:
    if user.is_admin:
        return FULL_ACCESS
    groups = {g.lower() for g in user_groups(db, user.id)}
    with db.connect() as conn:
        rows = conn.execute("SELECT id, allowed_groups FROM sources").fetchall()
    visible = set()
    for row in rows:
        allowed = {g.lower() for g in json.loads(row["allowed_groups"] or "[]")}
        if not allowed or allowed & groups:
            visible.add(row["id"])
    return AccessScope(all_sources=False, source_ids=frozenset(visible), uploads=True)
