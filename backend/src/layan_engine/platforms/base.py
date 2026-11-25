from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExtractionResult:
    platform: str = ""
    account_id: str = ""
    metrics: list[dict[str, Any]] = field(default_factory=list)
    content_records: list[dict[str, Any]] = field(default_factory=list)
    audience_data: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    extraction_method: str = ""
    success: bool = False


class PlatformWorker(ABC):
    platform: str = ""

    @abstractmethod
    async def verify_auth(self) -> bool:
        ...

    @abstractmethod
    async def extract_account_metrics(
        self, account_id: str, date_start: str, date_end: str
    ) -> ExtractionResult:
        ...

    @abstractmethod
    async def extract_content_metrics(
        self, account_id: str, date_start: str, date_end: str
    ) -> ExtractionResult:
        ...

    async def extract_audience_metrics(
        self, account_id: str, date_start: str, date_end: str
    ) -> ExtractionResult:
        return ExtractionResult(
            platform=self.platform,
            account_id=account_id,
            warnings=["Audience extraction not yet implemented"],
        )
