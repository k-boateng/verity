from collections.abc import Iterator


class LLMProvider:
    """Common shape every backend implements. Kept deliberately small so a
    different provider (Claude, a local model) can drop in without touching
    callers."""

    name = "base"

    def is_configured(self) -> bool:
        return False

    def generate(self, system: str, prompt: str, max_tokens: int = 600) -> str:
        raise NotImplementedError

    def stream(self, system: str, prompt: str, max_tokens: int = 600) -> Iterator[str]:
        raise NotImplementedError


class NullProvider(LLMProvider):
    """Stands in when no model is configured. Callers check is_configured()
    and surface an honest 'not set up yet' state rather than failing."""

    name = "none"

    def is_configured(self) -> bool:
        return False

    def generate(self, system: str, prompt: str, max_tokens: int = 600) -> str:
        raise RuntimeError("no LLM provider configured")

    def stream(self, system: str, prompt: str, max_tokens: int = 600) -> Iterator[str]:
        raise RuntimeError("no LLM provider configured")
