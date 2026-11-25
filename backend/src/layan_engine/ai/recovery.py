"""AI-powered recovery engine for extraction failures.

Principle: deterministic code first, AI second.  This module is invoked
only after standard selectors and parsing have already failed.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from layan_engine.ai.factory import get_ai_provider
from layan_engine.ai.prompts import (
    CLASSIFY_CHALLENGE_PROMPT,
    EXTRACT_METRICS_PROMPT,
    INTERPRET_VALUE_PROMPT,
    RECOVER_SELECTOR_PROMPT,
    SYSTEM_PROMPT,
)
from layan_engine.ai.provider import AIResponse
from layan_engine.config import settings
from layan_engine.logging import get_logger

log = get_logger(__name__)

_JSON_BLOCK = re.compile(r"```(?:json)?\s*([\s\S]*?)```")


def _extract_json(text: str) -> Any:
    """Pull JSON from an AI response, tolerating markdown fences."""
    m = _JSON_BLOCK.search(text)
    raw = m.group(1).strip() if m else text.strip()
    return json.loads(raw)


@dataclass
class RecoveryResult:
    success: bool = False
    data: Any = None
    ai_response: AIResponse | None = None
    error: str = ""


class RecoveryEngine:
    """Calls the configured AI provider for extraction recovery tasks."""

    def __init__(self):
        self._provider = get_ai_provider()

    @property
    def is_configured(self) -> bool:
        return bool(settings.ai_api_key)

    async def _call(self, user_prompt: str, *, max_tokens: int = 1024) -> AIResponse:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
        return await self._provider.chat(messages, max_tokens=max_tokens)

    # ── Public recovery methods ──────────────────────────────────

    async def extract_metrics_from_dom(
        self, platform: str, dom_snippet: str
    ) -> RecoveryResult:
        if not self.is_configured:
            return RecoveryResult(error="AI provider not configured")

        prompt = EXTRACT_METRICS_PROMPT.format(
            platform=platform, dom_snippet=dom_snippet[:4000]
        )
        try:
            resp = await self._call(prompt, max_tokens=2048)
            metrics = _extract_json(resp.content)
            if not isinstance(metrics, list):
                return RecoveryResult(
                    ai_response=resp, error="AI returned non-list response"
                )
            return RecoveryResult(success=True, data=metrics, ai_response=resp)
        except Exception as e:
            log.warning("ai_extract_metrics_failed", error=str(e))
            return RecoveryResult(error=str(e))

    async def suggest_selectors(
        self,
        platform: str,
        failed_selector: str,
        dom_structure: str,
        url: str,
        target_description: str,
    ) -> RecoveryResult:
        if not self.is_configured:
            return RecoveryResult(error="AI provider not configured")

        prompt = RECOVER_SELECTOR_PROMPT.format(
            selector=failed_selector,
            platform=platform,
            url=url,
            dom_structure=dom_structure[:4000],
            target_description=target_description,
        )
        try:
            resp = await self._call(prompt)
            selectors = _extract_json(resp.content)
            if not isinstance(selectors, list):
                return RecoveryResult(
                    ai_response=resp, error="AI returned non-list response"
                )
            return RecoveryResult(success=True, data=selectors, ai_response=resp)
        except Exception as e:
            log.warning("ai_suggest_selectors_failed", error=str(e))
            return RecoveryResult(error=str(e))

    async def classify_page_state(
        self, platform: str, url: str, title: str, text_excerpt: str
    ) -> RecoveryResult:
        if not self.is_configured:
            return RecoveryResult(error="AI provider not configured")

        prompt = CLASSIFY_CHALLENGE_PROMPT.format(
            platform=platform,
            url=url,
            title=title,
            text_excerpt=text_excerpt[:500],
        )
        try:
            resp = await self._call(prompt)
            classification = _extract_json(resp.content)
            if not isinstance(classification, dict):
                return RecoveryResult(
                    ai_response=resp, error="AI returned non-dict response"
                )
            return RecoveryResult(
                success=True, data=classification, ai_response=resp
            )
        except Exception as e:
            log.warning("ai_classify_page_failed", error=str(e))
            return RecoveryResult(error=str(e))

    async def interpret_metric_value(
        self, platform: str, label: str, raw_value: str
    ) -> RecoveryResult:
        if not self.is_configured:
            return RecoveryResult(error="AI provider not configured")

        prompt = INTERPRET_VALUE_PROMPT.format(
            platform=platform, label=label, raw_value=raw_value
        )
        try:
            resp = await self._call(prompt, max_tokens=256)
            parsed = _extract_json(resp.content)
            if not isinstance(parsed, dict) or "value" not in parsed:
                return RecoveryResult(
                    ai_response=resp, error="AI returned invalid structure"
                )
            return RecoveryResult(success=True, data=parsed, ai_response=resp)
        except Exception as e:
            log.warning("ai_interpret_value_failed", error=str(e))
            return RecoveryResult(error=str(e))
