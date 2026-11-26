"""Sync engine — pushes metrics from SQLite to Google Sheets.

Each platform gets its own worksheet tab.  A summary tab aggregates
the latest values across all platforms.  The sync queue tracks pending
items so we can do incremental updates.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from layan_engine.config import settings
from layan_engine.logging import get_logger
from layan_engine.sheets.client import SheetsClient, SheetsClientError
from layan_engine.storage.models import AccountMetric, Content, ContentMetric, SyncQueue

log = get_logger(__name__)

_ACCOUNT_HEADERS = [
    "Platform",
    "Account ID",
    "Metric",
    "Value",
    "Date Start",
    "Date End",
    "Source",
    "Method",
    "Extracted At",
]

_CONTENT_HEADERS = [
    "Platform",
    "Account ID",
    "Content ID",
    "Type",
    "Title",
    "Metric",
    "Value",
    "Date Start",
    "Date End",
    "Published",
    "URL",
    "Extracted At",
]

_SUMMARY_HEADERS = [
    "Platform",
    "Account ID",
    "Metric",
    "Latest Value",
    "Period",
    "Last Updated",
]


@dataclass
class SyncResult:
    success: bool = False
    account_metrics_synced: int = 0
    content_metrics_synced: int = 0
    summary_rows: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class SheetsSyncEngine:
    """Orchestrates metric sync from SQLite to Google Sheets."""

    def __init__(self, client: SheetsClient | None = None):
        self._client = client or SheetsClient()

    @property
    def is_configured(self) -> bool:
        return self._client.is_configured

    def full_sync(self, db: Session) -> SyncResult:
        """Replace all sheet data with current DB state."""
        result = SyncResult()

        if not self.is_configured:
            result.errors.append("Google Sheets not configured")
            return result

        try:
            self._client.open_spreadsheet()
        except SheetsClientError as e:
            result.errors.append(str(e))
            return result

        result.account_metrics_synced = self._sync_account_metrics(db, result)
        result.content_metrics_synced = self._sync_content_metrics(db, result)
        result.summary_rows = self._sync_summary(db, result)

        self._mark_queue_synced(db)

        result.success = len(result.errors) == 0
        log.info(
            "full_sync_complete",
            account_metrics=result.account_metrics_synced,
            content_metrics=result.content_metrics_synced,
            summary=result.summary_rows,
        )
        return result

    def incremental_sync(self, db: Session) -> SyncResult:
        """Sync only new/updated items from the sync queue."""
        result = SyncResult()

        if not self.is_configured:
            result.errors.append("Google Sheets not configured")
            return result

        pending = (
            db.query(SyncQueue)
            .filter(SyncQueue.status == "pending")
            .order_by(SyncQueue.created_at)
            .limit(500)
            .all()
        )

        if not pending:
            result.warnings.append("Nothing to sync")
            result.success = True
            return result

        try:
            self._client.open_spreadsheet()
        except SheetsClientError as e:
            result.errors.append(str(e))
            return result

        account_ids = [q.record_id for q in pending if q.table_name == "account_metrics"]
        content_ids = [q.record_id for q in pending if q.table_name == "content_metrics"]

        if account_ids:
            rows = self._fetch_account_rows_by_id(db, account_ids)
            if rows:
                ws = self._client.get_or_create_worksheet("Account Metrics")
                self._client.write_header(ws, _ACCOUNT_HEADERS)
                result.account_metrics_synced = self._client.append_rows(ws, rows)

        if content_ids:
            rows = self._fetch_content_rows_by_id(db, content_ids)
            if rows:
                ws = self._client.get_or_create_worksheet("Content Metrics")
                self._client.write_header(ws, _CONTENT_HEADERS)
                result.content_metrics_synced = self._client.append_rows(ws, rows)

        for q in pending:
            q.status = "synced"
            q.synced_at = datetime.now(timezone.utc)
        db.commit()

        result.success = True
        return result

    # ── Internal helpers ─────────────────────────────────────────

    def _sync_account_metrics(self, db: Session, result: SyncResult) -> int:
        try:
            metrics = (
                db.query(AccountMetric)
                .order_by(AccountMetric.platform, AccountMetric.date_end.desc(), AccountMetric.metric_name)
                .all()
            )
            rows = [_account_row(m) for m in metrics]
            ws = self._client.get_or_create_worksheet("Account Metrics")
            return self._client.clear_and_write(ws, _ACCOUNT_HEADERS, rows)
        except Exception as e:
            result.errors.append(f"Account metrics sync failed: {e}")
            return 0

    def _sync_content_metrics(self, db: Session, result: SyncResult) -> int:
        try:
            metrics = (
                db.query(ContentMetric)
                .order_by(ContentMetric.platform, ContentMetric.date_end.desc(), ContentMetric.content_id)
                .all()
            )
            rows = _content_rows(db, metrics)
            ws = self._client.get_or_create_worksheet("Content Metrics")
            return self._client.clear_and_write(ws, _CONTENT_HEADERS, rows)
        except Exception as e:
            result.errors.append(f"Content metrics sync failed: {e}")
            return 0

    def _sync_summary(self, db: Session, result: SyncResult) -> int:
        try:
            from sqlalchemy import func

            latest = (
                db.query(
                    AccountMetric.platform,
                    AccountMetric.account_id,
                    AccountMetric.metric_name,
                    AccountMetric.metric_value,
                    AccountMetric.date_start,
                    AccountMetric.date_end,
                    func.max(AccountMetric.extracted_at).label("last_updated"),
                )
                .group_by(
                    AccountMetric.platform,
                    AccountMetric.account_id,
                    AccountMetric.metric_name,
                )
                .order_by(AccountMetric.platform, AccountMetric.metric_name)
                .all()
            )
            rows = [
                [
                    r.platform,
                    r.account_id,
                    r.metric_name,
                    r.metric_value if r.metric_value is not None else "",
                    f"{r.date_start} → {r.date_end}",
                    _local(r.last_updated),
                ]
                for r in latest
            ]
            ws = self._client.get_or_create_worksheet("Summary")
            return self._client.clear_and_write(ws, _SUMMARY_HEADERS, rows)
        except Exception as e:
            result.errors.append(f"Summary sync failed: {e}")
            return 0

    def _fetch_account_rows_by_id(self, db: Session, ids: list[int]) -> list[list[Any]]:
        metrics = db.query(AccountMetric).filter(AccountMetric.id.in_(ids)).all()
        return [_account_row(m) for m in metrics]

    def _fetch_content_rows_by_id(self, db: Session, ids: list[int]) -> list[list[Any]]:
        metrics = db.query(ContentMetric).filter(ContentMetric.id.in_(ids)).all()
        return _content_rows(db, metrics)

    def _mark_queue_synced(self, db: Session):
        pending = db.query(SyncQueue).filter(SyncQueue.status == "pending").all()
        now = datetime.now(timezone.utc)
        for q in pending:
            q.status = "synced"
            q.synced_at = now
        db.commit()


def sync_after_pull(db: Session) -> dict[str, Any]:
    """Mirror the database into the Google Sheet after a pull. Never raises.

    A full rewrite (not appends) keeps the sheet identical to the database: a re-pull that
    updates a value can never leave a duplicate row behind.
    """
    engine = SheetsSyncEngine()
    if not engine.is_configured:
        return {"synced": False, "error": None, "skipped": "Google Sheets not configured"}
    try:
        r = engine.full_sync(db)
    except Exception as e:  # a Sheets outage must not fail the pull itself
        log.warning("sheets_sync_after_pull_failed", error=str(e)[:200])
        return {"synced": False, "error": str(e)[:300]}
    return {
        "synced": r.success,
        "rows": r.account_metrics_synced + r.content_metrics_synced,
        "error": "; ".join(r.errors) or None,
    }


def _local(ts: Any) -> str:
    """Timestamp as app-local wall time (MYT), which is what people reading the sheet expect."""
    from zoneinfo import ZoneInfo

    if not ts:
        return ""
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(ZoneInfo(settings.app_timezone)).strftime("%Y-%m-%d %H:%M:%S")


def _account_row(m: AccountMetric) -> list[Any]:
    return [
        m.platform, m.account_id, m.metric_name,
        m.metric_value if m.metric_value is not None else "",
        m.date_start, m.date_end,
        m.source_dashboard or "", m.extraction_method or "",
        _local(m.extracted_at),
    ]


def _content_rows(db: Session, metrics: list[ContentMetric]) -> list[list[Any]]:
    ids = {m.content_id for m in metrics}
    items = {c.content_id: c for c in db.query(Content).filter(Content.content_id.in_(ids)).all()} if ids else {}
    rows = []
    for m in metrics:
        c = items.get(m.content_id)
        rows.append([
            m.platform, m.account_id, m.content_id,
            c.content_type if c else "",
            (c.title or "").replace("\n", " ")[:300] if c else "",
            m.metric_name,
            m.metric_value if m.metric_value is not None else "",
            m.date_start, m.date_end,
            _local(c.published_at) if c else "",
            (c.content_url or "") if c else "",
            _local(m.extracted_at),
        ])
    return rows
