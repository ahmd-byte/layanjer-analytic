from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from layan_engine.logging import get_logger

log = get_logger(__name__)


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
    ai_assisted: bool = False


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

    async def ai_fallback_extract(self, page: Any, account_id: str, date_start: str, date_end: str) -> ExtractionResult:
        """AI-assisted metric extraction — called when deterministic methods fail."""
        from layan_engine.ai.dom_extractor import ai_extract_metrics
        from layan_engine.ai.recovery import RecoveryEngine

        result = ExtractionResult(platform=self.platform, account_id=account_id)
        engine = RecoveryEngine()
        if not engine.is_configured:
            result.warnings.append("AI provider not configured — skipping AI fallback")
            return result

        log.info("ai_fallback_started", platform=self.platform, account=account_id)
        recovery = await ai_extract_metrics(page, self.platform, engine)

        if not recovery.success:
            result.errors.append(f"AI extraction failed: {recovery.error}")
            return result

        for m in recovery.data or []:
            if not isinstance(m, dict) or "metric_name" not in m:
                continue
            result.metrics.append({
                "metric_name": m["metric_name"],
                "metric_value": m.get("metric_value"),
                "date_start": date_start,
                "date_end": date_end,
                "source_dashboard": f"{self.platform}_insights",
                "extraction_method": "ai_dom_extraction",
            })

        result.success = len(result.metrics) > 0
        result.extraction_method = "ai_dom_extraction"
        result.ai_assisted = True
        result.warnings.append(f"AI extracted {len(result.metrics)} metrics (verify accuracy)")

        if recovery.ai_response:
            log.info(
                "ai_fallback_completed",
                platform=self.platform,
                metrics_found=len(result.metrics),
                input_tokens=recovery.ai_response.input_tokens,
                output_tokens=recovery.ai_response.output_tokens,
            )

        return result
