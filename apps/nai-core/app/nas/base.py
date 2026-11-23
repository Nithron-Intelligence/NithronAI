"""
nAI NAS Adapter Interface
What nai-core may ask of a NAS platform; local accounts and manual sources never depend on it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol

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


def _covered(path: str, existing: list[str]) -> bool:
    """True if an existing source is this folder or contains it."""
    real = os.path.realpath(path)
    for source in existing:
        root = os.path.realpath(source)
        if real == root or real.startswith(root.rstrip(os.sep) + os.sep):
            return True
    return False


def discover_mounted_shares(roots: list[str], existing: list[str]) -> list[ShareCandidate]:
    """First-level folders under the allowed roots (how NAS shares appear inside the container)."""
    found: list[ShareCandidate] = []
    for root in roots:
        try:
            entries = sorted(os.scandir(root), key=lambda e: e.name.lower())
        except OSError:
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
