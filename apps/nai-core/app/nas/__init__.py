"""
nAI NAS adapters
Everything that depends on a particular NAS OS lives behind NasAdapter (docs/architecture/nas-adapters.md).
"""

from .base import Capabilities, NasAdapter, ShareCandidate
from .registry import ADAPTERS, get_nas_adapter

__all__ = ["ADAPTERS", "Capabilities", "NasAdapter", "ShareCandidate", "get_nas_adapter"]
