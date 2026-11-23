"""
nAI NAS Adapter Interface
What nai-core may ask of a NAS platform; local accounts and manual sources never depend on it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol

from ..utils.logging import get_logger

logger = get_logger(__name__)

# Folders NAS systems keep inside shares that are never sources of their own
SKIPPED_SHARE_NAMES = {
    "@eaDir",
    "#recycle",
    "#snapshot",
    ".snapshots",
    "lost+found",
    "@Recycle",
    "@Recently-Snapshot",
}


@dataclass(frozen=True)
class ShareCandidate:
    """A folder that could be added as a source."""

    name: str
    path: str
    source: str = "mount"  # "mount": found under an allowed root; "nas-api": reported by the NAS
    already_added: bool = False


@dataclass(frozen=True)
class Capabilities:
    """What an adapter can do beyond the core (the UI only offers what is True)."""

    share_discovery: bool = True
    nas_sign_in: bool = False
    permission_sync: bool = False
    management_mcp: bool = False


class NasAdapter(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def display_name(self) -> str: ...

    @property
    def capabilities(self) -> Capabilities: ...

    def discover_shares(self, roots: list[str], existing: list[str]) -> list[ShareCandidate]: ...


def _inside(path: str, root: str) -> bool:
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


def _covered(path: str, existing: list[str]) -> bool:
    """True if an existing source overlaps this folder (contains it, or lies inside it); such a
    folder can't be added, because sources may not overlap (SourceService.create)."""
    real = os.path.realpath(path)
    for source in existing:
        root = os.path.realpath(source)
        if _inside(real, root) or _inside(root, real):
            return True
    return False


def discover_mounted_shares(roots: list[str], existing: list[str]) -> list[ShareCandidate]:
    """First-level folders under the allowed roots (how NAS shares appear inside the container).

    Symlinked folders are not suggested (they can still be added by path if they resolve inside a root).
    """
    found: list[ShareCandidate] = []
    for root in roots:
        try:
            with os.scandir(root) as it:
                entries = sorted(it, key=lambda e: e.name.lower())
        except OSError as e:
            logger.warning(f"Can't list allowed root {root}: {e}")
            continue
        for entry in entries:
            if entry.name.startswith(".") or entry.name in SKIPPED_SHARE_NAMES:
                continue
            if not entry.is_dir(follow_symlinks=False):
                continue
            found.append(
                ShareCandidate(name=entry.name, path=entry.path, already_added=_covered(entry.path, existing))
            )
    return found
