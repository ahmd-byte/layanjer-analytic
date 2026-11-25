from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel


@dataclass
class AIResponse:
    content: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""
    provider: str = ""


class AIProvider(ABC):
    @abstractmethod
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
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        ...
