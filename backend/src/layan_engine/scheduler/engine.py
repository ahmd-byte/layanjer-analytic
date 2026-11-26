"""Scheduler engine — manages periodic extraction jobs.

Uses asyncio tasks to check and run due schedules on a configurable tick interval.
No external task queue required (local-first).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from layan_engine.storage.database import get_session_factory
from layan_engine.storage.models import Schedule

logger = logging.getLogger("layan.scheduler")

TICK_SECONDS = 30
MAX_CONSECUTIVE_FAILURES = 5


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def get_due_schedules(db: Session) -> list[Schedule]:
    now = _utcnow()
    return (
        db.query(Schedule)
        .filter(Schedule.is_active == True, Schedule.next_run_at <= now)  # noqa: E712
        .order_by(Schedule.next_run_at.asc())
        .all()
    )


def compute_next_run(schedule: Schedule) -> datetime:
    return _utcnow() + timedelta(minutes=schedule.interval_minutes)


def create_schedule(
    db: Session,
    *,
    name: str,
    platform: str,
    account_id: str,
    job_type: str = "full",
    interval_minutes: int = 360,
    lookback_days: int = 7,
    is_active: bool = True,
) -> Schedule:
    now = _utcnow()
    sched = Schedule(
        name=name,
        platform=platform,
        account_id=account_id,
        job_type=job_type,
        interval_minutes=interval_minutes,
        lookback_days=lookback_days,
        is_active=is_active,
        next_run_at=now + timedelta(minutes=interval_minutes),
        created_at=now,
        updated_at=now,
    )
    db.add(sched)
    db.commit()
    db.refresh(sched)
    return sched


def update_schedule(
    db: Session,
    schedule_id: int,
    *,
    name: Optional[str] = None,
    interval_minutes: Optional[int] = None,
    lookback_days: Optional[int] = None,
    is_active: Optional[bool] = None,
) -> Schedule | None:
    sched = db.get(Schedule, schedule_id)
    if not sched:
        return None
    if name is not None:
        sched.name = name
    if interval_minutes is not None:
        sched.interval_minutes = interval_minutes
        sched.next_run_at = compute_next_run(sched)
    if lookback_days is not None:
        sched.lookback_days = lookback_days
    if is_active is not None:
        sched.is_active = is_active
        if is_active and sched.next_run_at is None:
            sched.next_run_at = compute_next_run(sched)
    sched.updated_at = _utcnow()
    db.commit()
    db.refresh(sched)
    return sched


def delete_schedule(db: Session, schedule_id: int) -> bool:
    sched = db.get(Schedule, schedule_id)
    if not sched:
        return False
    db.delete(sched)
    db.commit()
    return True


def _get_worker(platform: str):
    """Return (WorkerClass, BrowserSession) for a platform."""
    from layan_engine.browser.session import BrowserSession

    if platform == "youtube":
        from layan_engine.platforms.youtube.worker import YouTubeWorker as W
    elif platform == "tiktok":
        from layan_engine.platforms.tiktok.worker import TikTokWorker as W
    elif platform == "instagram":
        from layan_engine.platforms.instagram.worker import InstagramWorker as W
    elif platform == "facebook":
        from layan_engine.platforms.facebook.worker import FacebookWorker as W
    else:
        raise ValueError(f"Unknown platform: {platform}")

    browser = BrowserSession()
    return W(browser), browser


async def _run_extraction(schedule: Schedule) -> tuple[str, int, str | None]:
    """Execute a single scheduled extraction.

    Returns (status, metrics_saved, error_msg).
    """
    import uuid

    from layan_engine.storage.models import ExtractionRun

    platform = schedule.platform
    account_id = schedule.account_id
    lookback = schedule.lookback_days
    job_type = schedule.job_type

    today = _utcnow().strftime("%Y-%m-%d")
    start = (_utcnow() - timedelta(days=lookback)).strftime("%Y-%m-%d")

    db = get_session_factory()()
    browser = None
    try:
        worker, browser = _get_worker(platform)

        run_id = str(uuid.uuid4())
        run = ExtractionRun(
            run_id=run_id,
            platform=platform,
            account_id=account_id,
            job_type=job_type,
            status="running",
            date_range_start=start,
            date_range_end=today,
            started_at=_utcnow(),
        )
        db.add(run)
        db.commit()
        db.refresh(run)

        if job_type == "account_metrics":
            result = await worker.extract_account_metrics(account_id, start, today)
        elif job_type == "content_metrics":
            result = await worker.extract_content_metrics(account_id, start, today)
        elif job_type == "audience_metrics":
            result = await worker.extract_audience_metrics(account_id, start, today)
        elif job_type == "full":
            result = await worker.extract_account_metrics(account_id, start, today)
            content = await worker.extract_content_metrics(account_id, start, today)
            result.metrics.extend(content.metrics)
            result.content_records.extend(content.content_records)
            result.errors.extend(content.errors)
            result.warnings.extend(content.warnings)
            if not result.success and content.success:
                result.success = True
        else:
            run.status = "failed"
            run.error_message = f"Unknown job_type: {job_type}"
            run.completed_at = _utcnow()
            db.commit()
            return "failed", 0, run.error_message

        metrics_saved = 0
        if result.success:
            from layan_engine.storage.metrics import save_result

            metrics_saved = save_result(db, platform, account_id, result, run.id)

        run.status = "completed" if result.success else "failed"
        run.metrics_extracted = metrics_saved
        run.metrics_failed = len(result.errors)
        run.error_message = "; ".join(result.errors) if result.errors else None
        run.completed_at = _utcnow()
        run.duration_seconds = (run.completed_at - run.started_at.replace(tzinfo=timezone.utc)).total_seconds() if run.started_at else None
        db.commit()

        if result.success:
            from layan_engine.sheets.sync import sync_after_pull

            sync_after_pull(db)

        return run.status, metrics_saved, run.error_message

    except Exception as e:
        logger.exception("Scheduled extraction failed for %s/%s", platform, account_id)
        return "failed", 0, str(e)
    finally:
        if browser:
            try:
                await browser.stop()
            except Exception:
                pass
        db.close()


async def process_due_schedules() -> int:
    """Check for and run due schedules. Returns number processed."""
    db = get_session_factory()()
    try:
        due = get_due_schedules(db)
        if not due:
            return 0

        processed = 0
        for sched in due:
            logger.info(
                "Running scheduled extraction: %s (%s/%s)",
                sched.name, sched.platform, sched.account_id,
            )
            sched.last_run_at = _utcnow()
            db.commit()

            status, metrics_saved, error = await _run_extraction(sched)

            sched.last_status = status
            sched.last_error = error
            if status == "completed":
                sched.consecutive_failures = 0
            else:
                sched.consecutive_failures += 1
                if sched.consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    sched.is_active = False
                    logger.warning(
                        "Schedule %s disabled after %d consecutive failures",
                        sched.name, sched.consecutive_failures,
                    )

            sched.next_run_at = compute_next_run(sched)
            sched.updated_at = _utcnow()
            db.commit()
            processed += 1

        return processed
    finally:
        db.close()


class SchedulerLoop:
    """Async background loop that checks and runs due schedules."""

    def __init__(self):
        self._task: asyncio.Task | None = None
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("Scheduler loop started (tick every %ds)", TICK_SECONDS)

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Scheduler loop stopped")

    async def _loop(self):
        while self._running:
            try:
                count = await process_due_schedules()
                if count:
                    logger.info("Processed %d scheduled extraction(s)", count)
            except Exception:
                logger.exception("Scheduler tick error")
            await asyncio.sleep(TICK_SECONDS)


scheduler_loop = SchedulerLoop()
