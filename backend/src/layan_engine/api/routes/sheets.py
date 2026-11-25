"""Google Sheets sync API routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from layan_engine.config import settings
from layan_engine.storage.database import get_db
from layan_engine.storage.models import SyncQueue

router = APIRouter()


@router.get("/status")
def sheets_status(db: Session = Depends(get_db)):
    """Check Google Sheets configuration and sync queue status."""
    configured = bool(
        settings.google_sheets_credentials_path
        and settings.google_sheets_spreadsheet_id
    )
    pending = (
        db.query(func.count(SyncQueue.id))
        .filter(SyncQueue.status == "pending")
        .scalar()
        or 0
    )
    synced = (
        db.query(func.count(SyncQueue.id))
        .filter(SyncQueue.status == "synced")
        .scalar()
        or 0
    )
    last_sync = (
        db.query(func.max(SyncQueue.synced_at))
        .filter(SyncQueue.status == "synced")
        .scalar()
    )

    return {
        "configured": configured,
        "spreadsheet_id": settings.google_sheets_spreadsheet_id or None,
        "credentials_set": bool(settings.google_sheets_credentials_path),
        "sync_queue": {
            "pending": pending,
            "synced": synced,
        },
        "last_sync_at": last_sync.isoformat() if last_sync else None,
    }


@router.post("/test-connection")
def test_sheets_connection():
    """Test that Google Sheets credentials and spreadsheet access work."""
    from layan_engine.sheets.client import SheetsClient

    client = SheetsClient()
    if not client.is_configured:
        return {
            "connected": False,
            "error": "Google Sheets not configured. Set GOOGLE_SHEETS_CREDENTIALS_PATH and GOOGLE_SHEETS_SPREADSHEET_ID in .env",
        }
    return client.test_connection()


@router.post("/sync")
def trigger_full_sync(db: Session = Depends(get_db)):
    """Trigger a full sync of all metrics to Google Sheets."""
    from layan_engine.sheets.sync import SheetsSyncEngine

    engine = SheetsSyncEngine()
    if not engine.is_configured:
        return {
            "success": False,
            "error": "Google Sheets not configured",
        }

    result = engine.full_sync(db)
    return {
        "success": result.success,
        "account_metrics_synced": result.account_metrics_synced,
        "content_metrics_synced": result.content_metrics_synced,
        "summary_rows": result.summary_rows,
        "errors": result.errors,
        "warnings": result.warnings,
    }


@router.post("/sync-incremental")
def trigger_incremental_sync(db: Session = Depends(get_db)):
    """Sync only pending items from the sync queue."""
    from layan_engine.sheets.sync import SheetsSyncEngine

    engine = SheetsSyncEngine()
    if not engine.is_configured:
        return {
            "success": False,
            "error": "Google Sheets not configured",
        }

    result = engine.incremental_sync(db)
    return {
        "success": result.success,
        "account_metrics_synced": result.account_metrics_synced,
        "content_metrics_synced": result.content_metrics_synced,
        "errors": result.errors,
        "warnings": result.warnings,
    }
