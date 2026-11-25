from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from layan_engine.ai.factory import get_ai_provider
from layan_engine.config import settings
from layan_engine.storage.database import get_db
from layan_engine.storage.models import (
    AIUsage,
    Account,
    AccountMetric,
    ContentMetric,
    ExtractionRun,
    SyncQueue,
)

router = APIRouter()


@router.get("/status")
def system_status(db: Session = Depends(get_db)):
    total_accounts = db.query(func.count(Account.id)).scalar() or 0
    authenticated = (
        db.query(func.count(Account.id))
        .filter(Account.auth_status == "authenticated")
        .scalar()
        or 0
    )
    total_account_metrics = db.query(func.count(AccountMetric.id)).scalar() or 0
    total_content_metrics = db.query(func.count(ContentMetric.id)).scalar() or 0
    pending_sync = (
        db.query(func.count(SyncQueue.id))
        .filter(SyncQueue.status == "pending")
        .scalar()
        or 0
    )
    last_run = (
        db.query(ExtractionRun)
        .order_by(ExtractionRun.created_at.desc())
        .first()
    )

    return {
        "accounts": {"total": total_accounts, "authenticated": authenticated},
        "metrics": {
            "account_metrics": total_account_metrics,
            "content_metrics": total_content_metrics,
        },
        "sync": {"pending": pending_sync},
        "last_extraction": {
            "platform": last_run.platform if last_run else None,
            "status": last_run.status if last_run else None,
            "completed_at": last_run.completed_at.isoformat() if last_run and last_run.completed_at else None,
        },
        "ai": {
            "provider": settings.ai_provider,
            "configured": bool(settings.ai_api_key),
        },
        "google_sheets": {
            "configured": bool(settings.google_sheets_spreadsheet_id),
        },
    }


@router.get("/ai-usage")
def ai_usage_summary(db: Session = Depends(get_db)):
    rows = (
        db.query(
            AIUsage.provider,
            AIUsage.model,
            func.sum(AIUsage.input_tokens).label("total_input"),
            func.sum(AIUsage.output_tokens).label("total_output"),
            func.sum(AIUsage.estimated_cost).label("total_cost"),
            func.count(AIUsage.id).label("request_count"),
        )
        .group_by(AIUsage.provider, AIUsage.model)
        .all()
    )
    return [
        {
            "provider": r.provider,
            "model": r.model,
            "total_input_tokens": r.total_input or 0,
            "total_output_tokens": r.total_output or 0,
            "total_cost": round(r.total_cost or 0, 4),
            "request_count": r.request_count,
        }
        for r in rows
    ]
