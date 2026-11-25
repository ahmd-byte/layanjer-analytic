from __future__ import annotations

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from layan_engine.config import settings

_engine = None
_SessionLocal = None


def _enable_wal(dbapi_conn, _connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


def get_engine():
    global _engine
    if _engine is None:
        settings.db_path.parent.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(
            f"sqlite:///{settings.db_path}",
            echo=False,
            pool_pre_ping=True,
        )
        event.listen(_engine, "connect", _enable_wal)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _SessionLocal


def get_db() -> Session:
    factory = get_session_factory()
    db = factory()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from layan_engine.storage.models import Base
    engine = get_engine()
    Base.metadata.create_all(engine)
