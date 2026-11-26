"""TikTok-specific API routes for auth, extraction triggers, and metrics."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from layan_engine.storage.database import get_db
from layan_engine.storage.models import (
    Account,
    AccountMetric,
    AudienceMetric,
    ContentMetric,
    ExtractionRun,
)

router = APIRouter()


class LoginRequest(BaseModel):
    account_id: str = "default"


class ExtractionRequest(BaseModel):
    account_id: str
    date_start: str
    date_end: str
    job_type: str = "account_metrics"


# ── Auth ──────────────────────────────────────────────────────────


@router.get("/accounts")
def list_tiktok_accounts(db: Session = Depends(get_db)):
    rows = (
        db.query(Account)
        .filter(Account.platform == "tiktok", Account.is_active.is_(True))
        .all()
    )
    return [
        {
            "id": a.id,
            "account_id": a.account_id,
            "account_name": a.account_name,
            "account_url": a.account_url,
            "auth_status": a.auth_status,
            "last_auth_at": a.last_auth_at.isoformat() if a.last_auth_at else None,
        }
        for a in rows
    ]


@router.post("/login")
async def tiktok_login(req: LoginRequest, db: Session = Depends(get_db)):
    """Open a browser window for the user to log in to TikTok."""
    from layan_engine.browser.session import BrowserSession
    from layan_engine.platforms.tiktok.worker import TikTokWorker
    from layan_engine.storage.accounts import record_authenticated_account

    browser = BrowserSession()
    worker = TikTokWorker(browser)
    try:
        success = await worker.login(req.account_id)
        if success:
            record_authenticated_account(db, "tiktok", req.account_id, worker._username)
            return {
                "status": "authenticated",
                "username": worker._username,
                "message": "TikTok login successful",
            }
        return {"status": "failed", "message": "Login timed out or failed"}
    finally:
        await browser.stop()


@router.post("/verify-auth")
async def tiktok_verify_auth():
    """Check if the saved TikTok session is still valid."""
    from layan_engine.browser.session import BrowserSession
    from layan_engine.platforms.tiktok.worker import TikTokWorker

    browser = BrowserSession()
    worker = TikTokWorker(browser)
    try:
        authenticated = await worker.verify_auth()
        return {
            "authenticated": authenticated,
            "username": worker._username,
        }
    finally:
        await browser.stop()


# ── Extraction ────────────────────────────────────────────────────


@router.post("/extract")
async def tiktok_extract(req: ExtractionRequest, db: Session = Depends(get_db)):
    """Trigger a TikTok analytics extraction."""
    from layan_engine.browser.session import BrowserSession
    from layan_engine.platforms.tiktok.worker import TikTokWorker

    run_id = str(uuid.uuid4())
    run = ExtractionRun(
        run_id=run_id,
        platform="tiktok",
        account_id=req.account_id,
        job_type=req.job_type,
        status="running",
        date_range_start=req.date_start,
        date_range_end=req.date_end,
        started_at=datetime.now(timezone.utc),
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    browser = BrowserSession()
    worker = TikTokWorker(browser)
    try:
        if req.job_type == "account_metrics":
            result = await worker.extract_account_metrics(
                req.account_id, req.date_start, req.date_end
            )
        elif req.job_type == "content_metrics":
            result = await worker.extract_content_metrics(
                req.account_id, req.date_start, req.date_end
            )
        elif req.job_type == "audience_metrics":
            result = await worker.extract_audience_metrics(
                req.account_id, req.date_start, req.date_end
            )
        else:
            raise HTTPException(400, f"Unknown job_type: {req.job_type}")

        metrics_saved = 0
        if result.success:
            from layan_engine.storage.metrics import save_result

            metrics_saved = save_result(db, "tiktok", req.account_id, result, run.id)

        run.status = "completed" if result.success else "failed"
        run.metrics_extracted = metrics_saved
        run.metrics_failed = len(result.errors)
        run.error_message = "; ".join(result.errors) if result.errors else None
        run.completed_at = datetime.now(timezone.utc)
        run.duration_seconds = (
            (run.completed_at - run.started_at.replace(tzinfo=timezone.utc)).total_seconds() if run.started_at else None
        )
        db.commit()

        return {
            "run_id": run_id,
            "status": run.status,
            "metrics_extracted": metrics_saved,
            "extraction_method": result.extraction_method,
            "errors": result.errors,
            "warnings": result.warnings,
        }

    except Exception as e:
        run.status = "failed"
        run.error_message = str(e)
        run.completed_at = datetime.now(timezone.utc)
        db.commit()
        return {"run_id": run_id, "status": "failed", "error": str(e)}
    finally:
        await browser.stop()


# ── Metrics Retrieval ─────────────────────────────────────────────


@router.get("/metrics")
def get_tiktok_metrics(
    account_id: str | None = None,
    metric_name: str | None = None,
    date_start: str | None = None,
    date_end: str | None = None,
    limit: int = Query(default=100, le=500),
    db: Session = Depends(get_db),
):
    q = db.query(AccountMetric).filter(AccountMetric.platform == "tiktok")
    if account_id:
        q = q.filter(AccountMetric.account_id == account_id)
    if metric_name:
        q = q.filter(AccountMetric.metric_name == metric_name)
    if date_start:
        q = q.filter(AccountMetric.date_start >= date_start)
    if date_end:
        q = q.filter(AccountMetric.date_end <= date_end)
    rows = q.order_by(AccountMetric.extracted_at.desc()).limit(limit).all()
    return [
        {
            "id": m.id,
            "account_id": m.account_id,
            "metric_name": m.metric_name,
            "metric_value": m.metric_value,
            "date_start": m.date_start,
            "date_end": m.date_end,
            "source_dashboard": m.source_dashboard,
            "extraction_method": m.extraction_method,
            "extracted_at": m.extracted_at.isoformat() if m.extracted_at else None,
        }
        for m in rows
    ]


@router.get("/content-metrics")
def get_tiktok_content_metrics(
    account_id: str | None = None,
    limit: int = Query(default=50, le=200),
    db: Session = Depends(get_db),
):
    q = db.query(ContentMetric).filter(ContentMetric.platform == "tiktok")
    if account_id:
        q = q.filter(ContentMetric.account_id == account_id)
    rows = q.order_by(ContentMetric.extracted_at.desc()).limit(limit).all()
    return [
        {
            "id": m.id,
            "account_id": m.account_id,
            "content_id": m.content_id,
            "metric_name": m.metric_name,
            "metric_value": m.metric_value,
            "date_start": m.date_start,
            "date_end": m.date_end,
        }
        for m in rows
    ]


@router.get("/audience-metrics")
def get_tiktok_audience_metrics(
    account_id: str | None = None,
    limit: int = Query(default=50, le=200),
    db: Session = Depends(get_db),
):
    q = db.query(AudienceMetric).filter(AudienceMetric.platform == "tiktok")
    if account_id:
        q = q.filter(AudienceMetric.account_id == account_id)
    rows = q.order_by(AudienceMetric.extracted_at.desc()).limit(limit).all()
    return [
        {
            "id": m.id,
            "account_id": m.account_id,
            "metric_name": m.metric_name,
            "dimension": m.dimension,
            "dimension_value": m.dimension_value,
            "metric_value": m.metric_value,
            "date_start": m.date_start,
            "date_end": m.date_end,
        }
        for m in rows
    ]
