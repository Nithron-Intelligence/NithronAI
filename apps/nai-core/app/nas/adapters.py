"""
nAI NAS Adapters (generic Docker host, NithronOS)
Step 1 of docs/architecture/nas-adapters.md: share discovery only; sign-in, permission sync
and the management MCP server are planned per adapter.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .base import Capabilities, ShareCandidate, discover_mounted_shares


@dataclass(frozen=True)
class GenericAdapter:
    """Any Linux box with Docker: shares are whatever is mounted under the allowed roots."""

    name: str = "generic"
    display_name: str = "Docker (any Linux)"
    capabilities: Capabilities = field(default_factory=Capabilities)

    def discover_shares(self, roots: list[str], existing: list[str]) -> list[ShareCandidate]:
        return discover_mounted_shares(roots, existing)


@dataclass(frozen=True)
class NithronOSAdapter(GenericAdapter):
    """NithronOS, the reference platform. The catalog template mounts the shares the user picked
    under /shares; permission sync, NithronOS sign-in and the management MCP server come next."""

    name: str = "nithronos"
    display_name: str = "NithronOS"
