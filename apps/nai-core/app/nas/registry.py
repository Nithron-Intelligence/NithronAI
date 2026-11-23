"""
nAI NAS Adapter Registry
Picks the adapter from NAI_NAS_PLATFORM (set by packaging; no guessing from the environment).
"""

from __future__ import annotations

from ..config import Settings
from .adapters import GenericAdapter, NithronOSAdapter
from .base import NasAdapter
from .truenas import TrueNASAdapter

ADAPTERS: dict[str, NasAdapter] = {
    a.name: a for a in (GenericAdapter(), NithronOSAdapter(), TrueNASAdapter())
}


def get_nas_adapter(settings: Settings) -> NasAdapter:
    """The configured adapter; unknown names fall back to the generic one (it always works)."""
    name = settings.nas_platform.strip().lower()
    if name == "truenas":
        return TrueNASAdapter(
            url=settings.truenas_url,
            api_key=settings.truenas_api_key.get_secret_value(),
            ca_file=settings.truenas_ca_file or None,
            timeout=settings.truenas_timeout,
        )
    return ADAPTERS.get(name, ADAPTERS["generic"])
