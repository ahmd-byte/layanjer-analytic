from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from layan_engine.storage.models import Account


def record_authenticated_account(
    db: Session,
    platform: str,
    account_id: str,
    account_name: str | None = None,
    account_url: str | None = None,
) -> Account:
    """Upsert the account after a successful login.

    account_id must be the browser-profile key the session was saved under,
    because extraction loads the saved login by that same key.
    """
    acct = (
        db.query(Account)
        .filter(Account.platform == platform, Account.account_id == account_id)
        .first()
    )
    if acct is None:
        acct = Account(platform=platform, account_id=account_id, account_name=account_name or account_id)
        db.add(acct)
    elif account_name:
        acct.account_name = account_name
    if account_url:
        acct.account_url = account_url
    acct.auth_status = "authenticated"
    acct.last_auth_at = datetime.now(timezone.utc)
    acct.is_active = True
    db.commit()
    db.refresh(acct)
    return acct
