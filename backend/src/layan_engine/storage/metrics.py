"""Save an ExtractionResult: account metrics, content items and their metrics.

Rows are upserted on their unique period key, so pulling the same period twice updates the
values instead of failing on the unique constraint.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from layan_engine.platforms.base import ExtractionResult
from layan_engine.storage.models import AccountMetric, Content, ContentMetric


def save_result(db: Session, platform: str, account_id: str, result: ExtractionResult, run_id: int | None) -> int:
    """Store everything the worker returned. Returns the number of metric values saved."""
    saved = 0
    for m in result.metrics:
        _upsert_account_metric(db, platform, account_id, m, run_id)
        saved += 1
    for item in result.content_records:
        saved += _upsert_content(db, platform, account_id, item, run_id)
    db.flush()
    return saved


def _upsert_account_metric(db: Session, platform: str, account_id: str, m: dict[str, Any], run_id: int | None) -> None:
    row = (
        db.query(AccountMetric)
        .filter_by(platform=platform, account_id=account_id, metric_name=m["metric_name"],
                   date_start=m["date_start"], date_end=m["date_end"])
        .one_or_none()
    )
    if row is None:
        row = AccountMetric(platform=platform, account_id=account_id, metric_name=m["metric_name"],
                            date_start=m["date_start"], date_end=m["date_end"])
        db.add(row)
    row.metric_value = m["metric_value"]
    row.source_dashboard = m.get("source_dashboard", "")
    row.extraction_method = m.get("extraction_method", "")
    row.extraction_run_id = run_id
    row.validation_status = "extracted"
    row.extracted_at = datetime.now(timezone.utc)


def _upsert_content(db: Session, platform: str, account_id: str, item: dict[str, Any], run_id: int | None) -> int:
    if not item.get("content_id"):
        return 0  # older extractors return raw rows without an id; nothing to key them on
    content =db.query(Content).filter_by(platform=platform, content_id=item["content_id"]).one_or_none()
    if content is None:
        content = Content(platform=platform, account_id=account_id, content_id=item["content_id"],
                          content_type=item.get("content_type") or "post")
        db.add(content)
    content.content_type = item.get("content_type") or content.content_type
    content.title = item.get("title") or content.title
    content.content_url = item.get("content_url") or content.content_url
    if item.get("published_at"):
        content.published_at = datetime.fromisoformat(item["published_at"].replace("Z", "+00:00"))

    saved = 0
    for name, value in (item.get("metrics") or {}).items():
        if value is None:
            continue
        row = (
            db.query(ContentMetric)
            .filter_by(platform=platform, content_id=item["content_id"], metric_name=name,
                       date_start=item["date_start"], date_end=item["date_end"])
            .one_or_none()
        )
        if row is None:
            row = ContentMetric(platform=platform, account_id=account_id, content_id=item["content_id"],
                                metric_name=name, date_start=item["date_start"], date_end=item["date_end"])
            db.add(row)
        row.metric_value = value
        row.source_dashboard = item.get("source_dashboard", "")
        row.extraction_method = item.get("extraction_method", "dom")
        row.extraction_run_id = run_id
        row.validation_status = "extracted"
        row.extracted_at = datetime.now(timezone.utc)
        saved += 1
    return saved
