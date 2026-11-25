"""AI-related API routes — status, budget, and recovery endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from layan_engine.ai.budget import check_budget, get_today_spend
from layan_engine.ai.factory import get_ai_provider
from layan_engine.ai.recovery import RecoveryEngine
from layan_engine.config import settings
from layan_engine.storage.database import get_db

router = APIRouter()


@router.get("/status")
async def ai_status(db: Session = Depends(get_db)):
    """Get AI provider status and budget information."""
    provider = get_ai_provider()
    within_budget, spent, limit = check_budget(db)
    available = False
    if settings.ai_api_key:
        try:
            available = await provider.is_available()
        except Exception:
            pass

    return {
        "provider": settings.ai_provider,
        "model": settings.ai_primary_model,
        "configured": bool(settings.ai_api_key),
        "available": available,
        "budget": {
            "daily_limit": limit,
            "spent_today": round(spent, 4),
            "remaining": round(limit - spent, 4),
            "within_budget": within_budget,
        },
    }


class InterpretRequest(BaseModel):
    platform: str
    label: str
    raw_value: str


@router.post("/interpret-value")
async def interpret_value(req: InterpretRequest, db: Session = Depends(get_db)):
    """Use AI to interpret a metric value that standard parsing couldn't handle."""
    within_budget, spent, limit = check_budget(db)
    if not within_budget:
        return {"error": "Daily AI budget exceeded", "spent": spent, "limit": limit}

    engine = RecoveryEngine()
    if not engine.is_configured:
        return {"error": "AI provider not configured"}

    result = await engine.interpret_metric_value(
        platform=req.platform, label=req.label, raw_value=req.raw_value
    )
    if result.success and result.ai_response:
        from layan_engine.ai.budget import record_usage

        record_usage(
            db,
            provider=result.ai_response.provider,
            model=result.ai_response.model,
            purpose="interpret_value",
            input_tokens=result.ai_response.input_tokens,
            output_tokens=result.ai_response.output_tokens,
        )

    return {
        "success": result.success,
        "data": result.data,
        "error": result.error or None,
    }


class ClassifyRequest(BaseModel):
    platform: str
    url: str
    title: str
    text_excerpt: str


@router.post("/classify-page")
async def classify_page(req: ClassifyRequest, db: Session = Depends(get_db)):
    """Use AI to classify an unexpected page state."""
    within_budget, spent, limit = check_budget(db)
    if not within_budget:
        return {"error": "Daily AI budget exceeded", "spent": spent, "limit": limit}

    engine = RecoveryEngine()
    if not engine.is_configured:
        return {"error": "AI provider not configured"}

    result = await engine.classify_page_state(
        platform=req.platform,
        url=req.url,
        title=req.title,
        text_excerpt=req.text_excerpt,
    )
    if result.success and result.ai_response:
        from layan_engine.ai.budget import record_usage

        record_usage(
            db,
            provider=result.ai_response.provider,
            model=result.ai_response.model,
            purpose="classify_page",
            input_tokens=result.ai_response.input_tokens,
            output_tokens=result.ai_response.output_tokens,
        )

    return {
        "success": result.success,
        "data": result.data,
        "error": result.error or None,
    }
