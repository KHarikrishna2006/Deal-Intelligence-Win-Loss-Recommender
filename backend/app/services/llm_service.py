from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Optional

import httpx

from app.config import settings
from app.core.exceptions import UpstreamUnavailableError
from app.core.logging import get_logger

logger = get_logger(__name__)

_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


class LLMUnavailableError(UpstreamUnavailableError):
    code = "llm_unavailable"


class LLMResponseError(UpstreamUnavailableError):
    code = "llm_malformed_response"


@dataclass
class LLMResult:
    text: str
    model: str
    usage: dict[str, Any]


class LLMService:
    """Thin, provider-agnostic wrapper over an OpenAI-compatible chat endpoint.

    The API key never leaves this process; nothing here is reachable from the
    frontend.
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout: int | None = None,
    ):
        self.base_url = (base_url or settings.llm_base_url).rstrip("/")
        self.api_key = api_key if api_key is not None else settings.llm_api_key
        self.model = model or settings.llm_model
        self.timeout = timeout or settings.llm_timeout_seconds

    @property
    def configured(self) -> bool:
        return bool(self.base_url)

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def health(self) -> dict[str, Any]:
        """Returns availability without raising."""
        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.get(f"{self.base_url}/models", headers=self._headers())
                resp.raise_for_status()
                data = resp.json()
                models = [m.get("id") for m in data.get("data", [])] if isinstance(data, dict) else []
                return {"available": True, "model": self.model, "models": models[:25]}
        except Exception as exc:  # noqa: BLE001 - availability probe must not raise
            logger.debug("LLM health probe failed: %s", type(exc).__name__)
            return {"available": False, "model": self.model, "reason": type(exc).__name__}

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> LLMResult:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": settings.llm_temperature if temperature is None else temperature,
            "max_tokens": max_tokens or settings.llm_max_tokens,
            "stream": False,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(
                    f"{self.base_url}/chat/completions",
                    headers=self._headers(),
                    json=payload,
                )
                if resp.status_code >= 500:
                    raise LLMUnavailableError(
                        f"LLM provider returned {resp.status_code}.",
                        details={"provider": self.base_url},
                    )
                if resp.status_code == 404 and json_mode:
                    # Some providers reject response_format; retry without it.
                    payload.pop("response_format", None)
                    resp = client.post(
                        f"{self.base_url}/chat/completions",
                        headers=self._headers(),
                        json=payload,
                    )
                resp.raise_for_status()
                data = resp.json()
        except httpx.TimeoutException as exc:
            raise LLMUnavailableError("LLM provider timed out.") from exc
        except httpx.HTTPError as exc:
            raise LLMUnavailableError(
                f"LLM provider unreachable: {exc.__class__.__name__}."
            ) from exc
        except json.JSONDecodeError as exc:
            raise LLMResponseError("LLM provider returned a non-JSON body.") from exc

        try:
            choice = data["choices"][0]
            text = choice["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMResponseError("LLM provider returned an unexpected payload shape.") from exc

        return LLMResult(
            text=text,
            model=data.get("model", self.model),
            usage=data.get("usage", {}) or {},
        )

    def complete_json(
        self,
        messages: list[dict[str, str]],
        *,
        schema_hint: str | None = None,
        temperature: float | None = None,
    ) -> dict[str, Any]:
        result = self.complete(
            messages, temperature=temperature, json_mode=True
        )
        parsed = extract_json(result.text)
        if parsed is None:
            raise LLMResponseError(
                "LLM returned a response that could not be parsed as JSON.",
                details={"snippet": result.text[:400]},
            )
        return parsed


def extract_json(text: str) -> dict[str, Any] | None:
    """Best-effort JSON extraction that tolerates code fences and prose."""
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        obj = json.loads(cleaned)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass
    match = _JSON_BLOCK.search(cleaned)
    if match:
        try:
            obj = json.loads(match.group(0))
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            return None
    return None
