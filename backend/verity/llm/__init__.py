from .. import config
from .base import LLMProvider, NullProvider
from .gemini import GeminiProvider

_provider: LLMProvider | None = None


def get_provider() -> LLMProvider:
    global _provider
    if _provider is None:
        if config.LLM_PROVIDER == "gemini":
            _provider = GeminiProvider(config.GEMINI_API_KEY, config.LLM_MODEL)
        else:
            _provider = NullProvider()
    return _provider


def set_provider(provider: LLMProvider | None) -> None:
    """Override the active provider (used by tests)."""
    global _provider
    _provider = provider


__all__ = ["LLMProvider", "NullProvider", "GeminiProvider", "get_provider", "set_provider"]
