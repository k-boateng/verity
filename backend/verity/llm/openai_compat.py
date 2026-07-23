"""A provider for any OpenAI-compatible chat-completions endpoint.

Cerebras and Groq both speak the OpenAI schema, so one implementation serves
both (and any future host) — the difference is just base URL, key, and model.
"""

import json
import re
from collections.abc import Iterator

import httpx

from .base import LLMProvider

# Reasoning models wrap their scratch-work in <think>…</think>; strip it so the
# reader never sees the model thinking out loud. (The default models aren't
# reasoning models, so this is just a safety net.)
_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)


def _strip_think(text: str) -> str:
    return _THINK.sub("", text).strip()


class OpenAICompatProvider(LLMProvider):
    def __init__(self, name: str, base_url: str, api_key: str, model: str) -> None:
        self.name = name
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model

    def is_configured(self) -> bool:
        return bool(self._api_key)

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def _payload(self, system: str, prompt: str, max_tokens: int, stream: bool) -> dict:
        return {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "max_tokens": max_tokens,
            "stream": stream,
        }

    def generate(self, system: str, prompt: str, max_tokens: int = 600) -> str:
        if not self._api_key:
            raise RuntimeError(f"{self.name} API key not set")
        with httpx.Client(timeout=90.0) as client:
            resp = client.post(
                f"{self._base_url}/chat/completions",
                headers=self._headers(),
                json=self._payload(system, prompt, max_tokens, stream=False),
            )
            resp.raise_for_status()
            data = resp.json()
        content = data["choices"][0]["message"].get("content") or ""
        return _strip_think(content)

    def stream(self, system: str, prompt: str, max_tokens: int = 600) -> Iterator[str]:
        if not self._api_key:
            raise RuntimeError(f"{self.name} API key not set")
        with httpx.Client(timeout=120.0) as client:
            with client.stream(
                "POST",
                f"{self._base_url}/chat/completions",
                headers=self._headers(),
                json=self._payload(system, prompt, max_tokens, stream=True),
            ) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    chunk = line[len("data:") :].strip()
                    if chunk == "[DONE]":
                        break
                    try:
                        obj = json.loads(chunk)
                    except json.JSONDecodeError:
                        continue
                    delta = obj.get("choices", [{}])[0].get("delta", {})
                    piece = delta.get("content")
                    if piece:
                        yield piece
