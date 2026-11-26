"""Extraction-run bookkeeping shared by the API routes, the scheduler and app startup."""
from __future__ import annotations

from datetime import datetime, timezone

from layan_engine.logging import get_logger
from layan_engine.platforms.base import ExtractionResult

log = get_logger(__name__)

INTERRUPTED = "Interrupted: the app stopped or crashed before this run finished"


def run_error_message(result: ExtractionResult) -> str | None:
    """Why a run failed, never blank: errors, else the warnings that explain it."""
    if result.errors:
        return "; ".join(result.errors)[:1000]
    if not result.success:
        return ("; ".join(result.warnings) or "No numbers could be read from the dashboard")[:1000]
    return None


def close_interrupted_runs() -> int:
    """At startup nothing can still be running (one process), so any run marked "running"
    was cut off by a crash or restart. Mark it failed so history and health stay honest."""
    from layan_engine.storage.database import get_session_factory
    from layan_engine.storage.models import ExtractionRun

    db = get_session_factory()()
    try:
        stuck = db.query(ExtractionRun).filter(ExtractionRun.status == "running").all()
        now = datetime.now(timezone.utc)
        for run in stuck:
            run.status = "failed"
            run.error_message = run.error_message or INTERRUPTED
            run.completed_at = run.completed_at or now
        db.commit()
        if stuck:
            log.info("interrupted_runs_closed", count=len(stuck))
        return len(stuck)
    finally:
        db.close()
