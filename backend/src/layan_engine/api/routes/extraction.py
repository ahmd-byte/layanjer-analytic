from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from layan_engine.storage.database import get_db
from layan_engine.storage.models import ExtractionRun

router = APIRouter()


@router.get("/runs")
def list_extraction_runs(
    platform: str | None = None,
    status: str | None = None,
    limit: int = Query(default=50, le=200),
    db: Session = Depends(get_db),
):
    q = db.query(ExtractionRun)
    if platform:
        q = q.filter(ExtractionRun.platform == platform)
    if status:
        q = q.filter(ExtractionRun.status == status)
    rows = q.order_by(ExtractionRun.created_at.desc()).limit(limit).all()
    return [
        {
            "id": r.id,
            "run_id": r.run_id,
            "platform": r.platform,
            "account_id": r.account_id,
            "job_type": r.job_type,
            "status": r.status,
            "metrics_extracted": r.metrics_extracted,
            "metrics_failed": r.metrics_failed,
            "error_category": r.error_category,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            "duration_seconds": r.duration_seconds,
        }
        for r in rows
    ]


@router.get("/runs/{run_id}")
def get_extraction_run(run_id: str, db: Session = Depends(get_db)):
    run = db.query(ExtractionRun).filter(ExtractionRun.run_id == run_id).first()
    if not run:
        return {"error": "Run not found"}
    return {
        "id": run.id,
        "run_id": run.run_id,
        "platform": run.platform,
        "account_id": run.account_id,
        "job_type": run.job_type,
        "status": run.status,
        "date_range_start": run.date_range_start,
        "date_range_end": run.date_range_end,
        "metrics_extracted": run.metrics_extracted,
        "metrics_failed": run.metrics_failed,
        "error_category": run.error_category,
        "error_message": run.error_message,
        "steps": [
            {
                "step_name": s.step_name,
                "status": s.status,
                "error_category": s.error_category,
                "duration_seconds": s.duration_seconds,
            }
            for s in run.steps
        ],
    }
