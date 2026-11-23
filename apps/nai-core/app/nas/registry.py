"""
nAI NAS Adapter Registry
Picks the adapter from NAI_NAS_PLATFORM (set by packaging; no guessing from the environment).
"""

from __future__ import annotations

from ..config import Settings
from .adapters import GenericAdapter, NithronOSAdapter
from .base import NasAdapter

ADAPTERS: dict[str, NasAdapter] = {a.name: a for a in (GenericAdapter(), NithronOSAdapter())}


def get_nas_adapter(settings: Settings) -> NasAdapter:
    """The configured adapter; unknown names fall back to the generic one (it always works)."""
    return ADAPTERS.get(settings.nas_platform.strip().lower(), ADAPTERS["generic"])
