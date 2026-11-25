import os
import tempfile

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

from layan_engine.storage.models import (
    Account,
    AccountMetric,
    Base,
    Content,
    ContentMetric,
    ExtractionRun,
)


def _make_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}")

    def _wal(dbapi_conn, _):
        c = dbapi_conn.cursor()
        c.execute("PRAGMA foreign_keys=ON")
        c.close()

    event.listen(engine, "connect", _wal)
    Base.metadata.create_all(engine)
    return engine, path


def _cleanup(engine, path):
    engine.dispose()
    try:
        os.unlink(path)
    except PermissionError:
        pass


def test_create_tables():
    engine, path = _make_db()
    with engine.connect() as conn:
        tables = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'")).fetchall()
    names = {t[0] for t in tables}
    assert "accounts" in names
    assert "account_metrics" in names
    assert "content_metrics" in names
    assert "extraction_runs" in names
    _cleanup(engine, path)


def test_account_insert_and_uniqueness():
    engine, path = _make_db()
    Session = sessionmaker(bind=engine)

    with Session() as db:
        db.add(Account(platform="youtube", account_id="UC123", account_name="Test Channel"))
        db.commit()

    with Session() as db:
        accounts = db.query(Account).all()
        assert len(accounts) == 1
        assert accounts[0].platform == "youtube"

    with Session() as db:
        db.add(Account(platform="youtube", account_id="UC123", account_name="Duplicate"))
        try:
            db.commit()
            assert False, "Should have raised IntegrityError"
        except Exception:
            db.rollback()

    _cleanup(engine, path)


def test_metric_upsert():
    engine, path = _make_db()
    Session = sessionmaker(bind=engine)

    with Session() as db:
        db.add(
            AccountMetric(
                platform="youtube",
                account_id="UC123",
                metric_name="views",
                metric_value=1000,
                date_start="2024-01-01",
                date_end="2024-01-01",
            )
        )
        db.commit()

    with Session() as db:
        count = db.query(AccountMetric).count()
        assert count == 1

    _cleanup(engine, path)
