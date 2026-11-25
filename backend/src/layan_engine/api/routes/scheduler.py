"""Scheduler API routes — CRUD for extraction schedules and manual triggers."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from layan_engine.storage.database import get_db
from layan_engine.storage.models import Schedule

router = APIRouter()


class ScheduleCreate(BaseModel):
    name: str
    platform: str
    account_id: str
    job_type: str = "full"
    interval_minutes: int = 360
    lookback_days: int = 7
    is_active: bool = True


class ScheduleUpdate(BaseModel):
    name: Optional[str] = None
    interval_minutes: Optional[int] = None
    lookback_days: Optional[int] = None
    is_active: Optional[bool] = None


def _serialize(s: Schedule) -> dict:
    return {
        "id": s.id,
        "name": s.name,
        "platform": s.platform,
        "account_id": s.account_id,
        "job_type": s.job_type,
        "interval_minutes": s.interval_minutes,
        "lookback_days": s.lookback_days,
        "is_active": s.is_active,
        "last_run_at": s.last_run_at.isoformat() if s.last_run_at else None,
        "next_run_at": s.next_run_at.isoformat() if s.next_run_at else None,
        "last_status": s.last_status,
        "last_error": s.last_error,
        "consecutive_failures": s.consecutive_failures,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


@router.get("/")
def list_schedules(db: Session = Depends(get_db)):
    rows = db.query(Schedule).order_by(Schedule.created_at.desc()).all()
    return [_serialize(s) for s in rows]


@router.post("/")
def create_schedule_route(req: ScheduleCreate, db: Session = Depends(get_db)):
    if req.platform not in ("youtube", "tiktok", "instagram", "facebook"):
        raise HTTPException(400, f"Invalid platform: {req.platform}")
    if req.interval_minutes < 15:
        raise HTTPException(400, "Minimum interval is 15 minutes")

    from layan_engine.scheduler.engine import create_schedule

    sched = create_schedule(
        db,
        name=req.name,
        platform=req.platform,
        account_id=req.account_id,
        job_type=req.job_type,
        interval_minutes=req.interval_minutes,
        lookback_days=req.lookback_days,
        is_active=req.is_active,
    )
    return _serialize(sched)


@router.put("/{schedule_id}")
def update_schedule_route(schedule_id: int, req: ScheduleUpdate, db: Session = Depends(get_db)):
    from layan_engine.scheduler.engine import update_schedule

    sched = update_schedule(
        db,
        schedule_id,
        name=req.name,
        interval_minutes=req.interval_minutes,
        lookback_days=req.lookback_days,
        is_active=req.is_active,
    )
    if not sched:
        raise HTTPException(404, "Schedule not found")
    return _serialize(sched)


@router.delete("/{schedule_id}")
def delete_schedule_route(schedule_id: int, db: Session = Depends(get_db)):
    from layan_engine.scheduler.engine import delete_schedule

    if not delete_schedule(db, schedule_id):
        raise HTTPException(404, "Schedule not found")
    return {"deleted": True}


@router.get("/status")
def scheduler_status(db: Session = Depends(get_db)):
    from layan_engine.scheduler.engine import scheduler_loop

    total = db.query(Schedule).count()
    active = db.query(Schedule).filter(Schedule.is_active == True).count()  # noqa: E712
    return {
        "running": scheduler_loop.is_running,
        "total_schedules": total,
        "active_schedules": active,
    }


@router.post("/{schedule_id}/trigger")
async def trigger_schedule(schedule_id: int, db: Session = Depends(get_db)):
    """Manually trigger a scheduled extraction right now."""
    sched = db.get(Schedule, schedule_id)
    if not sched:
        raise HTTPException(404, "Schedule not found")

    from layan_engine.scheduler.engine import _run_extraction, _utcnow, compute_next_run

    status, metrics_saved, error = await _run_extraction(sched)

    sched.last_run_at = _utcnow()
    sched.last_status = status
    sched.last_error = error
    if status == "completed":
        sched.consecutive_failures = 0
    else:
        sched.consecutive_failures += 1
    sched.next_run_at = compute_next_run(sched)
    sched.updated_at = _utcnow()
    db.commit()

    return {
        "status": status,
        "metrics_saved": metrics_saved,
        "error": error,
    }
