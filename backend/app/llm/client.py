import logging
from typing import Any, Dict, List, Optional, Protocol

import requests

from app.core.settings import get_settings

logger = logging.getLogger(__name__)

Schema = Optional[Dict[str, Any]]


class LLMError(Exception):
    pass


class LLMClient(Protocol):
    def complete(self, messages: List[Dict[str, str]], schema: Schema = None,
                 max_tokens: Optional[int] = None) -> str:
        """Return the assistant's reply text (JSON matching `schema` when given), or raise LLMError."""
        ...


class OpenRouterClient:
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None, url: Optional[str] = None,
                 timeout: Optional[float] = None, temperature: Optional[float] = None,
                 max_tokens: Optional[int] = None):
        s = get_settings()  # anything not passed comes from config/settings.yml
        self.api_key = s.openrouter_api_key if api_key is None else api_key
        self.model = model or s.openrouter_model
        self.url = url or s.openrouter_url
        self.timeout = timeout or s.llm_timeout_seconds
        self.temperature = s.llm_temperature if temperature is None else temperature
        self.max_tokens = max_tokens or s.llm_max_tokens

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def complete(self, messages: List[Dict[str, str]], schema: Schema = None,
                 max_tokens: Optional[int] = None) -> str:
        if not self.configured:
            raise LLMError("OPENROUTER_API_KEY is not set")
        payload: Dict[str, Any] = {"model": self.model, "messages": messages,
                                   "max_tokens": max_tokens or self.max_tokens, "temperature": self.temperature}
        if schema:
            # Honoured by models that support structured output, ignored by the others.
            payload["response_format"] = {"type": "json_schema",
                                          "json_schema": {"name": "answer", "schema": schema}}
        try:
            response = requests.post(self.url, headers={"Authorization": f"Bearer {self.api_key}"},
                                     json=payload, timeout=self.timeout)
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]
        except requests.RequestException as exc:
            raise LLMError(f"OpenRouter request failed: {exc}") from exc
        except (KeyError, IndexError, ValueError) as exc:
            raise LLMError(f"Unexpected OpenRouter response: {exc}") from exc


class OllamaClient:
    """Local models through Ollama's native /api/chat endpoint, which (unlike its
    OpenAI-compatible endpoint) accepts num_ctx and a JSON schema. Tries the main model, then the fallback."""

    def __init__(self, model: Optional[str] = None, fallback_model: Optional[str] = None,
                 url: Optional[str] = None, timeout: Optional[float] = None,
                 temperature: Optional[float] = None, num_ctx: Optional[int] = None,
                 max_tokens: Optional[int] = None, keep_alive: Optional[str] = None):
        s = get_settings()  # anything not passed comes from config/settings.yml
        model = model or s.ollama_model
        self.models = [model] + ([fallback_model] if fallback_model and fallback_model != model else [])
        self.url = (url or s.ollama_url).rstrip("/")
        self.timeout = timeout or s.ollama_timeout_seconds
        self.keep_alive = keep_alive or s.ollama_keep_alive
        self.warm_up_timeout = s.ollama_warm_up_timeout_seconds
        self.health_timeout = s.ollama_health_timeout_seconds
        self.options = {
            "temperature": s.llm_temperature if temperature is None else temperature,
            "num_ctx": num_ctx or s.ollama_num_ctx,
            "num_predict": max_tokens or s.llm_max_tokens,
        }

    def warm_up(self) -> None:
        """Load the main model into memory so the first user message doesn't pay the load time."""
        try:
            response = requests.post(f"{self.url}/api/chat", timeout=self.warm_up_timeout, json={
                "model": self.models[0], "messages": [], "keep_alive": self.keep_alive,
                "options": {"num_ctx": self.options["num_ctx"]},
            })
            response.raise_for_status()
            logger.info("Ollama model %s loaded", self.models[0])
        except requests.RequestException as exc:
            logger.warning("Could not preload Ollama model %s: %s", self.models[0], exc)

    @property
    def configured(self) -> bool:
        """True when Ollama is reachable and at least one of the models is pulled."""
        try:
            response = requests.get(f"{self.url}/api/tags", timeout=self.health_timeout)
            response.raise_for_status()
            available = {m["name"] for m in response.json().get("models", [])}
        except (requests.RequestException, ValueError, KeyError):
            return False
        return any(model in available for model in self.models)

    def complete(self, messages: List[Dict[str, str]], schema: Schema = None,
                 max_tokens: Optional[int] = None) -> str:
        errors = []
        for model in self.models:
            try:
                return self._chat(model, messages, schema, max_tokens)
            except LLMError as exc:
                logger.warning("Ollama model %s failed: %s", model, exc)
                errors.append(f"{model}: {exc}")
        raise LLMError("; ".join(errors))

    def _chat(self, model: str, messages: List[Dict[str, str]], schema: Schema, max_tokens: Optional[int]) -> str:
        options = dict(self.options, **({"num_predict": max_tokens} if max_tokens else {}))
        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "think": False,  # Qwen3 reasons step by step by default; too slow for a chat reply
            "keep_alive": self.keep_alive,
            "options": options,
        }
        if schema:
            payload["format"] = schema  # Ollama constrains decoding to this JSON schema
        try:
            response = requests.post(f"{self.url}/api/chat", json=payload, timeout=self.timeout)
            response.raise_for_status()
            content = response.json()["message"]["content"]
        except requests.RequestException as exc:
            raise LLMError(f"request failed: {exc}") from exc
        except (KeyError, ValueError) as exc:
            raise LLMError(f"unexpected response: {exc}") from exc
        if not content.strip():
            raise LLMError("empty reply")
        return content
