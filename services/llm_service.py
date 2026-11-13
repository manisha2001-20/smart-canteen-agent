"""LLM service abstraction.

The rest of the app only talks to `LLMService`. Providers are pluggable:
  - AnthropicProvider        (Claude Messages API)
  - OpenAICompatibleProvider (OpenAI, Groq, Together, local Ollama, ...)

Only the standard library is used for HTTP, so no SDK is required.
If no provider/API key is configured, `LLMService.available` is False and
callers fall back to local logic - the app never depends on the LLM.
"""
import json
import re
import urllib.error
import urllib.request
from abc import ABC, abstractmethod

from utils.config import Settings, get_settings


class LLMProvider(ABC):
    name = "base"

    def __init__(self, api_key: str, model: str, timeout: int = 15):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    @abstractmethod
    def complete(self, system: str, prompt: str) -> str:
        ...

    def _post_json(self, url: str, headers: dict, body: dict) -> dict:
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode(),
            headers={"content-type": "application/json", **headers},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode())


class AnthropicProvider(LLMProvider):
    name = "anthropic"
    URL = "https://api.anthropic.com/v1/messages"

    def complete(self, system: str, prompt: str) -> str:
        data = self._post_json(
            self.URL,
            {"x-api-key": self.api_key, "anthropic-version": "2023-06-01"},
            {
                "model": self.model,
                "max_tokens": 400,
                "system": system,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        return "".join(block.get("text", "") for block in data.get("content", []))


class OpenAICompatibleProvider(LLMProvider):
    name = "openai"

    def __init__(self, api_key: str, model: str, timeout: int = 15, base_url: str = "https://api.openai.com/v1"):
        super().__init__(api_key, model, timeout)
        self.base_url = base_url

    def complete(self, system: str, prompt: str) -> str:
        data = self._post_json(
            f"{self.base_url}/chat/completions",
            {"authorization": f"Bearer {self.api_key}"},
            {
                "model": self.model,
                "temperature": 0,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
            },
        )
        return data["choices"][0]["message"]["content"]


def build_provider(settings: Settings) -> LLMProvider | None:
    if not settings.llm_enabled:
        return None
    if settings.llm_provider == "anthropic":
        return AnthropicProvider(settings.llm_api_key, settings.llm_model, settings.llm_timeout)
    if settings.llm_provider == "openai":
        return OpenAICompatibleProvider(
            settings.llm_api_key, settings.llm_model, settings.llm_timeout, settings.llm_base_url
        )
    return None


class LLMService:
    def __init__(self, provider: LLMProvider | None = None):
        self.provider = provider
        self.last_error: str | None = None

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "LLMService":
        return cls(build_provider(settings or get_settings()))

    @property
    def available(self) -> bool:
        return self.provider is not None

    @property
    def description(self) -> str:
        if not self.provider:
            return "Local mode (no LLM configured)"
        return f"{self.provider.name} / {self.provider.model}"

    def complete(self, system: str, prompt: str) -> str | None:
        """Returns the model's text, or None on any failure (never raises)."""
        if not self.provider:
            return None
        try:
            self.last_error = None
            return self.provider.complete(system, prompt)
        except (urllib.error.URLError, TimeoutError, KeyError, ValueError, OSError) as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            return None

    def complete_json(self, system: str, prompt: str) -> dict | None:
        text = self.complete(system, prompt)
        if not text:
            return None
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            self.last_error = "LLM response contained no JSON"
            return None
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            self.last_error = f"Invalid JSON from LLM: {exc}"
            return None
