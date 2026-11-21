"""
nAI Core LLM Service
Single place that talks to LLM providers through LiteLLM (completion and streaming).
"""

import logging
from collections.abc import AsyncIterator
from functools import lru_cache
from typing import Any

from ..config import Settings, get_settings
from ..hardware import choose_ollama_model, detect_hardware, ollama_models
from ..utils.logging import get_logger

logger = get_logger(__name__)


class LLMUnavailableError(RuntimeError):
    pass


class LLMService:
    """Thin async wrapper around ``litellm.acompletion``."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._litellm_importable: bool | None = None

    def is_available(self) -> bool:
        """LLM enabled, LiteLLM installed and (for model=auto) a model could be chosen."""
        if not self.settings.llm_enabled:
            return False
        if self._litellm_importable is None:
            try:
                import litellm

                litellm.suppress_debug_info = True  # no "Provider List" banners in the logs
                logging.getLogger("LiteLLM").setLevel(logging.WARNING)
                self._litellm_importable = True
            except ImportError:
                logger.warning("NAI_LLM_ENABLED is set but litellm is not installed")
                self._litellm_importable = False
        return self._litellm_importable and self.resolved_model is not None

    @property
    def resolved_model(self) -> str | None:
        """The configured model, or for 'auto' the best installed Ollama model for this hardware."""
        model = self.settings.llm_model
        if model != "auto":
            return model
        if self.settings.llm_provider != "ollama":
            logger.warning("NAI_LLM_MODEL=auto is only supported with the ollama provider")
            return None
        base = self.settings.llm_api_base or ""
        return choose_ollama_model(ollama_models(base), detect_hardware())

    @property
    def model_name(self) -> str:
        """
        LiteLLM model string: always ``<provider>/<model>``, e.g. ``ollama/llama3.2`` or
        ``openai/Qwen/Qwen3-8B`` for an OpenAI-compatible server (vLLM, llama.cpp, LM Studio).
        A model that already starts with the provider prefix is used as is.
        """
        model = self.resolved_model
        if model is None:
            raise LLMUnavailableError("No LLM model available")
        provider = self.settings.llm_provider
        if model.startswith(f"{provider}/"):
            return model
        return f"{provider}/{model}"

    @property
    def display_name(self) -> str:
        return f"{self.settings.llm_provider}/{self.resolved_model}"

    def _kwargs(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "temperature": self.settings.llm_temperature,
            "max_tokens": self.settings.llm_max_tokens,
        }
        if self.settings.llm_api_base:
            kwargs["api_base"] = self.settings.llm_api_base
        if self.settings.llm_api_key:
            kwargs["api_key"] = self.settings.llm_api_key
        return kwargs

    async def complete(self, messages: list[dict[str, str]]) -> tuple[str, int | None]:
        """Run a chat completion. Returns (text, total_tokens). Raises on failure."""
        import litellm

        response = await litellm.acompletion(**self._kwargs(messages))
        text = response.choices[0].message.content or ""
        usage = getattr(response, "usage", None)
        tokens = getattr(usage, "total_tokens", None) if usage else None
        return text, tokens

    async def stream(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        """Yield text deltas as the model produces them. Raises on failure."""
        import litellm

        response = await litellm.acompletion(**self._kwargs(messages), stream=True)
        async for chunk in response:
            try:
                delta = chunk.choices[0].delta.content
            except (AttributeError, IndexError):
                delta = None
            if delta:
                yield delta


@lru_cache(maxsize=1)
def get_llm_service() -> LLMService:
    return LLMService(get_settings())
