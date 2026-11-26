from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from layan_engine.storage.accounts import record_authenticated_account
from layan_engine.storage.models import Account, Base


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_creates_authenticated_account():
    db = _session()
    acct = record_authenticated_account(db, "youtube", "default", "UCabc", "https://studio.youtube.com/channel/UCabc")
    assert acct.account_id == "default"
    assert acct.account_name == "UCabc"
    assert acct.auth_status == "authenticated"
    assert acct.last_auth_at is not None


def test_relogin_updates_instead_of_duplicating():
    db = _session()
    record_authenticated_account(db, "instagram", "default", "old_name")
    record_authenticated_account(db, "instagram", "default", "new_name")
    rows = db.query(Account).filter(Account.platform == "instagram").all()
    assert len(rows) == 1
    assert rows[0].account_name == "new_name"


def test_missing_name_falls_back_to_account_id():
    db = _session()
    acct = record_authenticated_account(db, "facebook", "default", None)
    assert acct.account_name == "default"


def test_timestamps_come_back_as_aware_utc():
    """SQLite drops offsets; without this the browser showed UTC times as local (8h off in MYT)."""
    from datetime import datetime, timedelta, timezone

    db = _session()
    acct = record_authenticated_account(db, "youtube", "default", "UCabc")
    myt = timezone(timedelta(hours=8))
    acct.last_auth_at = datetime(2026, 11, 26, 19, 47, tzinfo=myt)
    db.commit()
    db.expire_all()
    loaded = db.query(Account).one().last_auth_at
    assert loaded.tzinfo is not None
    assert loaded.isoformat() == "2026-11-26T11:47:00+00:00"
