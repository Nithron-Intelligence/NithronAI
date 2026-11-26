"""
nAI Core Reranker
Optional cross-encoder that rescores the fused candidates (fastembed, ONNX on CPU).
"""

import threading
from functools import lru_cache

from ..config import Settings, get_settings
from ..utils.logging import get_logger

logger = get_logger(__name__)


class RerankerService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._model = None
        self._error: str | None = None
        self._lock = threading.Lock()
        self._auto: tuple[bool, str] | None = None  # hardware decision for mode=auto, computed once

    def decision(self) -> tuple[bool, str]:
        """(on?, reason) for the configured mode; auto asks the hardware policy (cached)."""
        mode = self.settings.reranker  # normalized to auto | on | off by Settings
        if mode == "on":
            return True, "on (set by NAI_RERANKER)"
        if mode == "off":
            return False, "off (set by NAI_RERANKER)"
        if self._auto is None:
            from ..hardware import detect_hardware, reranker_auto_decision

            on, why = reranker_auto_decision(detect_hardware(), self.settings.reranker_model)
            self._auto = (on, f"auto, {'on' if on else 'off'}: {why}")
        return self._auto

    def wanted(self) -> bool:
        return self.decision()[0]

    def _load(self):
        if self._model is not None or self._error is not None:
            return self._model
        with self._lock:
            if self._model is not None or self._error is not None:
                return self._model
            try:
                from fastembed.rerank.cross_encoder import TextCrossEncoder

                logger.info(f"Loading reranker {self.settings.reranker_model}")
                self._model = TextCrossEncoder(
                    model_name=self.settings.reranker_model, cache_dir=self.settings.models_path
                )
            except Exception as e:
                self._error = str(e)
                logger.warning(f"Reranker unavailable: {e}")
            return self._model

    def is_available(self) -> bool:
        return self.wanted() and self._load() is not None

    def rerank(self, query: str, documents: list[str]) -> list[float] | None:
        """Relevance score per document, or None when reranking is off/unavailable."""
        if not documents or not self.wanted():
            return None
        model = self._load()
        if model is None:
            return None
        try:
            return [float(s) for s in model.rerank(query, documents)]
        except Exception as e:
            logger.warning(f"Reranking failed: {e}")
            return None

    def stats(self) -> dict:
        return {
            "mode": self.settings.reranker,
            "active": self.wanted(),
            "reason": self.decision()[1],
            "top_k": self.settings.reranker_candidates,
            "model": self.settings.reranker_model,
            "error": self._error,
        }


@lru_cache(maxsize=1)
def get_reranker() -> RerankerService:
    return RerankerService(get_settings())
