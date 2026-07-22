from collections.abc import Iterator

from .base import LLMProvider


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self, api_key: str, model: str) -> None:
        self._api_key = api_key
        self._model = model
        self._client = None

    def is_configured(self) -> bool:
        return bool(self._api_key)

    def _client_or_raise(self):
        if not self._api_key:
            raise RuntimeError("GEMINI_API_KEY is not set")
        if self._client is None:
            from google import genai

            self._client = genai.Client(api_key=self._api_key)
        return self._client

    def _config(self, system: str, max_tokens: int):
        from google.genai import types

        return types.GenerateContentConfig(
            system_instruction=system,
            temperature=0.2,
            max_output_tokens=max_tokens,
        )

    def generate(self, system: str, prompt: str, max_tokens: int = 600) -> str:
        client = self._client_or_raise()
        resp = client.models.generate_content(
            model=self._model,
            contents=prompt,
            config=self._config(system, max_tokens),
        )
        return (resp.text or "").strip()

    def stream(self, system: str, prompt: str, max_tokens: int = 600) -> Iterator[str]:
        client = self._client_or_raise()
        for chunk in client.models.generate_content_stream(
            model=self._model,
            contents=prompt,
            config=self._config(system, max_tokens),
        ):
            if chunk.text:
                yield chunk.text
