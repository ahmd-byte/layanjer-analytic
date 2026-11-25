from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from layan_engine.storage.database import get_db
from layan_engine.storage.models import AccountMetric, ContentMetric, ExtractionRun

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


@router.get("/trends")
def get_metric_trends(
    platform: str | None = None,
    account_id: str | None = None,
    metric_names: str | None = None,
    limit: int = Query(default=50, le=200),
    db: Session = Depends(get_db),
):
    """Return metrics grouped by date_start for time-series charting.

    Returns rows sorted by date_start ascending, each row containing:
    { date: "2024-01-01", metric_name: value, ... }
    """
    q = db.query(AccountMetric)
    if platform:
        q = q.filter(AccountMetric.platform == platform)
    if account_id:
        q = q.filter(AccountMetric.account_id == account_id)
    if metric_names:
        names = [n.strip() for n in metric_names.split(",") if n.strip()]
        q = q.filter(AccountMetric.metric_name.in_(names))

    rows = q.order_by(AccountMetric.date_start.asc()).limit(limit * 10).all()

    date_map: dict[str, dict[str, float | str | None]] = {}
    for r in rows:
        key = r.date_start
        if key not in date_map:
            date_map[key] = {"date": key}
        date_map[key][r.metric_name] = r.metric_value

    result = sorted(date_map.values(), key=lambda d: d.get("date", ""))
    return result[-limit:]


@router.get("/platform-summary")
def get_platform_summary(db: Session = Depends(get_db)):
    """Return metric counts and latest extraction per platform for overview charts."""
    platform_metrics = (
        db.query(
            AccountMetric.platform,
            func.count(AccountMetric.id).label("metric_count"),
            func.count(func.distinct(AccountMetric.metric_name)).label("unique_metrics"),
        )
        .group_by(AccountMetric.platform)
        .all()
    )

    platform_runs = (
        db.query(
            ExtractionRun.platform,
            func.count(ExtractionRun.id).label("total_runs"),
            func.sum(
                func.case(
                    (ExtractionRun.status == "completed", 1),
                    else_=0,
                )
            ).label("successful_runs"),
            func.max(ExtractionRun.completed_at).label("last_extraction"),
        )
        .group_by(ExtractionRun.platform)
        .all()
    )

    runs_by_platform = {r.platform: r for r in platform_runs}

    return [
        {
            "platform": m.platform,
            "metric_count": m.metric_count,
            "unique_metrics": m.unique_metrics,
            "total_runs": getattr(runs_by_platform.get(m.platform), "total_runs", 0) or 0,
            "successful_runs": getattr(runs_by_platform.get(m.platform), "successful_runs", 0) or 0,
            "last_extraction": (
                runs_by_platform[m.platform].last_extraction.isoformat()
                if m.platform in runs_by_platform and runs_by_platform[m.platform].last_extraction
                else None
            ),
        }
        for m in platform_metrics
    ]


@router.get("/extraction-history")
def get_extraction_history(
    limit: int = Query(default=30, le=100),
    db: Session = Depends(get_db),
):
    """Return recent extraction runs for a timeline chart."""
    runs = (
        db.query(ExtractionRun)
        .order_by(ExtractionRun.started_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "run_id": r.run_id,
            "platform": r.platform,
            "status": r.status,
            "metrics_extracted": r.metrics_extracted,
            "metrics_failed": r.metrics_failed,
            "duration_seconds": r.duration_seconds,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        }
        for r in runs
    ]
