"""AI usage budget tracking — enforces daily spend limits."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from layan_engine.config import settings
from layan_engine.logging import get_logger
from layan_engine.storage.models import AIUsage

log = get_logger(__name__)

# Rough cost-per-million-tokens for supported providers
_COST_PER_M: dict[str, dict[str, tuple[float, float]]] = {
    "deepseek": {
        "deepseek-chat": (0.14, 0.28),
        "deepseek-reasoner": (0.55, 2.19),
    },
    "openai": {
        "gpt-4o-mini": (0.15, 0.60),
        "gpt-4o": (2.50, 10.00),
    },
}


def estimate_cost(provider: str, model: str, input_tokens: int, output_tokens: int) -> float:
    rates = _COST_PER_M.get(provider, {}).get(model)
    if not rates:
        rates = (0.50, 2.00)
    input_cost = (input_tokens / 1_000_000) * rates[0]
    output_cost = (output_tokens / 1_000_000) * rates[1]
    return round(input_cost + output_cost, 6)


def get_today_spend(db: Session) -> float:
    today = datetime.now(timezone.utc).date().isoformat()
    total = (
        db.query(func.sum(AIUsage.estimated_cost))
        .filter(func.date(AIUsage.created_at) == today)
        .scalar()
    )
    return total or 0.0


def check_budget(db: Session) -> tuple[bool, float, float]:
    spent = get_today_spend(db)
    limit = settings.ai_daily_budget
    return spent < limit, spent, limit


def record_usage(
    db: Session,
    *,
    provider: str,
    model: str,
    purpose: str,
    input_tokens: int,
    output_tokens: int,
    extraction_run_id: int | None = None,
) -> AIUsage:
    cost = estimate_cost(provider, model, input_tokens, output_tokens)
    usage = AIUsage(
        provider=provider,
        model=model,
        purpose=purpose,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost=cost,
        extraction_run_id=extraction_run_id,
    )
    db.add(usage)
    db.commit()
    log.info(
        "ai_usage_recorded",
        provider=provider,
        model=model,
        purpose=purpose,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost=cost,
    )
    return usage
