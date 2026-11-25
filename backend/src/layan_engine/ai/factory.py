from __future__ import annotations

from layan_engine.ai.provider import AIProvider
from layan_engine.config import settings


def get_ai_provider() -> AIProvider:
    if settings.ai_provider == "openai":
        from layan_engine.ai.openai_provider import OpenAIProvider
        return OpenAIProvider()
    from layan_engine.ai.deepseek import DeepSeekProvider
    return DeepSeekProvider()
