"""
nAI Core LLM Service
Single place that talks to LLM providers through LiteLLM.
"""

from functools import lru_cache
from typing import Any

from ..config import Settings, get_settings
from ..utils.logging import get_logger

logger = get_logger(__name__)


class LLMService:
    """Thin async wrapper around ``litellm.acompletion``."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._litellm_importable: bool | None = None

    def is_available(self) -> bool:
        """True when the LLM is enabled and LiteLLM is installed (no network check)."""
        if not self.settings.llm_enabled:
            return False
        if self._litellm_importable is None:
            try:
                import litellm  # noqa: F401

                self._litellm_importable = True
                logger.info(f"LLM configured: {self.model_name}")
            except ImportError:
                logger.warning("NAI_LLM_ENABLED is set but litellm is not installed")
                self._litellm_importable = False
        return self._litellm_importable

    @property
    def model_name(self) -> str:
        """LiteLLM model string, e.g. ``ollama/llama3.2`` or ``anthropic/<model>``."""
        model = self.settings.llm_model
        provider = self.settings.llm_provider
        if "/" in model or provider == "openai":
            return model
        return f"{provider}/{model}"

    @property
    def display_name(self) -> str:
        return f"{self.settings.llm_provider}/{self.settings.llm_model}"

    async def complete(self, messages: list[dict[str, str]]) -> tuple[str, int | None]:
        """Run a chat completion. Returns (text, total_tokens). Raises on failure."""
        import litellm

        kwargs: dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "temperature": self.settings.llm_temperature,
            "max_tokens": self.settings.llm_max_tokens,
        }
        if self.settings.llm_api_base:
            kwargs["api_base"] = self.settings.llm_api_base
        if self.settings.llm_api_key:
            # Passed per call so it works for every provider (not only OpenAI's env var).
            kwargs["api_key"] = self.settings.llm_api_key

        response = await litellm.acompletion(**kwargs)
        text = response.choices[0].message.content or ""
        usage = getattr(response, "usage", None)
        tokens = getattr(usage, "total_tokens", None) if usage else None
        return text, tokens


@lru_cache(maxsize=1)
def get_llm_service() -> LLMService:
    """Get the LLM service singleton."""
    return LLMService(get_settings())
