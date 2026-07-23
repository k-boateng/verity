from .. import config
from .base import LLMProvider, NullProvider
from .gemini import GeminiProvider
from .openai_compat import OpenAICompatProvider

_provider: LLMProvider | None = None

_ENDPOINTS = {
    "cerebras": ("https://api.cerebras.ai/v1", lambda: config.CEREBRAS_API_KEY),
    "groq": ("https://api.groq.com/openai/v1", lambda: config.GROQ_API_KEY),
}


def get_provider() -> LLMProvider:
    global _provider
    if _provider is None:
        name = config.LLM_PROVIDER
        if name in _ENDPOINTS:
            base_url, key_getter = _ENDPOINTS[name]
            _provider = OpenAICompatProvider(name, base_url, key_getter(), config.LLM_MODEL)
        elif name == "gemini":
            _provider = GeminiProvider(config.GEMINI_API_KEY, config.LLM_MODEL)
        else:
            _provider = NullProvider()
    return _provider


def set_provider(provider: LLMProvider | None) -> None:
    """Override the active provider (used by tests)."""
    global _provider
    _provider = provider


__all__ = [
    "LLMProvider",
    "NullProvider",
    "GeminiProvider",
    "OpenAICompatProvider",
    "get_provider",
    "set_provider",
]
