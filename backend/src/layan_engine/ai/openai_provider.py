from __future__ import annotations

from typing import Any

import httpx
from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential

from layan_engine.ai.provider import AIProvider, AIResponse
from layan_engine.config import settings
from layan_engine.logging import get_logger

log = get_logger(__name__)


class OpenAIProvider(AIProvider):
    def __init__(self):
        self._base_url = "https://api.openai.com/v1"
        self._api_key = settings.ai_api_key
        self._default_model = settings.ai_primary_model or "gpt-4o-mini"
        self._timeout = settings.ai_request_timeout

    @property
    def name(self) -> str:
        return "openai"

    async def is_available(self) -> bool:
        if not self._api_key:
            return False
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{self._base_url}/models",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )
                return resp.status_code == 200
        except Exception:
            return False

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        tools: list[dict] | None = None,
        response_format: type[BaseModel] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> AIResponse:
        body: dict[str, Any] = {
            "model": model or self._default_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            body["tools"] = tools
        if response_format:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": response_format.__name__,
                    "schema": response_format.model_json_schema(),
                },
            }

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                f"{self._base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()

        choice = data["choices"][0]
        message = choice.get("message", {})
        usage = data.get("usage", {})

        return AIResponse(
            content=message.get("content", "") or "",
            tool_calls=[tc for tc in message.get("tool_calls", []) if tc],
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            model=data.get("model", model or self._default_model),
            provider="openai",
        )
