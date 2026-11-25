from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from layan_engine.storage.database import get_db
from layan_engine.storage.models import AccountMetric, ContentMetric

router = APIRouter()


@router.get("/account-metrics")
def get_account_metrics(
    platform: str | None = None,
    account_id: str | None = None,
    date_start: str | None = None,
    date_end: str | None = None,
    limit: int = Query(default=100, le=1000),
    db: Session = Depends(get_db),
):
    q = db.query(AccountMetric)
    if platform:
        q = q.filter(AccountMetric.platform == platform)
    if account_id:
        q = q.filter(AccountMetric.account_id == account_id)
    if date_start:
        q = q.filter(AccountMetric.date_start >= date_start)
    if date_end:
        q = q.filter(AccountMetric.date_end <= date_end)
    rows = q.order_by(AccountMetric.date_start.desc()).limit(limit).all()
    return [
        {
            "id": r.id,
            "platform": r.platform,
            "account_id": r.account_id,
            "metric_name": r.metric_name,
            "metric_value": r.metric_value,
            "metric_unit": r.metric_unit,
            "date_start": r.date_start,
            "date_end": r.date_end,
            "extraction_method": r.extraction_method,
            "validation_status": r.validation_status,
            "extracted_at": r.extracted_at.isoformat() if r.extracted_at else None,
        }
        for r in rows
    ]


@router.get("/content-metrics")
def get_content_metrics(
    platform: str | None = None,
    content_id: str | None = None,
    date_start: str | None = None,
    date_end: str | None = None,
    limit: int = Query(default=100, le=1000),
    db: Session = Depends(get_db),
):
    q = db.query(ContentMetric)
    if platform:
        q = q.filter(ContentMetric.platform == platform)
    if content_id:
        q = q.filter(ContentMetric.content_id == content_id)
    if date_start:
        q = q.filter(ContentMetric.date_start >= date_start)
    if date_end:
        q = q.filter(ContentMetric.date_end <= date_end)
    rows = q.order_by(ContentMetric.date_start.desc()).limit(limit).all()
    return [
        {
            "id": r.id,
            "platform": r.platform,
            "content_id": r.content_id,
            "metric_name": r.metric_name,
            "metric_value": r.metric_value,
            "metric_unit": r.metric_unit,
            "date_start": r.date_start,
            "date_end": r.date_end,
            "extraction_method": r.extraction_method,
            "validation_status": r.validation_status,
        }
        for r in rows
    ]
