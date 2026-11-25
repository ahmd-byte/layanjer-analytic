from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from layan_engine.storage.database import get_db
from layan_engine.storage.models import Account

router = APIRouter()


@router.get("/")
def list_accounts(db: Session = Depends(get_db)):
    accounts = db.query(Account).filter(Account.is_active.is_(True)).all()
    return [
        {
            "id": a.id,
            "platform": a.platform,
            "account_id": a.account_id,
            "account_name": a.account_name,
            "auth_status": a.auth_status,
            "last_auth_at": a.last_auth_at.isoformat() if a.last_auth_at else None,
        }
        for a in accounts
    ]


@router.get("/{platform}")
def list_platform_accounts(platform: str, db: Session = Depends(get_db)):
    accounts = (
        db.query(Account)
        .filter(Account.platform == platform, Account.is_active.is_(True))
        .all()
    )
    return [
        {
            "id": a.id,
            "platform": a.platform,
            "account_id": a.account_id,
            "account_name": a.account_name,
            "auth_status": a.auth_status,
        }
        for a in accounts
    ]
