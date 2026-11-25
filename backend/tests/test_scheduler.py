"""Tests for scheduler engine, models, and API routes."""
import os
import tempfile
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def fresh_db(monkeypatch):
    """Provide a fresh temporary DB for each test."""
    from pathlib import Path

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setenv("DB_PATH", path)

    from importlib import reload
    import layan_engine.config
    reload(layan_engine.config)
    import layan_engine.storage.database as db_mod
    db_mod._engine = None
    db_mod._SessionLocal = None
    monkeypatch.setattr(db_mod, "settings", layan_engine.config.settings)
    db_mod.init_db()

    yield db_mod

    if db_mod._engine:
        db_mod._engine.dispose()
        db_mod._engine = None
        db_mod._SessionLocal = None
    try:
        os.unlink(path)
    except PermissionError:
        pass


# ── Schedule model tests ─────────────────────────────────────────


class TestScheduleModel:
    def test_fields(self):
        from layan_engine.storage.models import Schedule

        s = Schedule(
            name="test",
            platform="youtube",
            account_id="default",
            job_type="full",
            interval_minutes=360,
            lookback_days=7,
            is_active=True,
            consecutive_failures=0,
        )
        assert s.name == "test"
        assert s.platform == "youtube"
        assert s.job_type == "full"
        assert s.interval_minutes == 360


# ── Scheduler engine tests ───────────────────────────────────────


class TestComputeNextRun:
    def test_adds_interval(self):
        from layan_engine.scheduler.engine import compute_next_run
        from layan_engine.storage.models import Schedule

        s = Schedule(
            name="test", platform="youtube", account_id="x",
            interval_minutes=60,
        )
        result = compute_next_run(s)
        now = datetime.now(timezone.utc)
        assert abs((result - now).total_seconds() - 3600) < 5


class TestCreateSchedule:
    def test_create_and_read(self, fresh_db):
        db_mod = fresh_db
        from layan_engine.scheduler.engine import create_schedule
        from layan_engine.storage.models import Schedule

        db = db_mod.get_session_factory()()
        try:
            sched = create_schedule(
                db, name="YT Daily", platform="youtube",
                account_id="default", interval_minutes=360,
            )
            assert sched.id is not None
            assert sched.name == "YT Daily"
            assert sched.next_run_at is not None

            rows = db.query(Schedule).all()
            assert len(rows) == 1
        finally:
            db.close()


class TestUpdateSchedule:
    def test_update_fields(self, fresh_db):
        db_mod = fresh_db
        from layan_engine.scheduler.engine import create_schedule, update_schedule

        db = db_mod.get_session_factory()()
        try:
            sched = create_schedule(
                db, name="Old", platform="tiktok",
                account_id="default", interval_minutes=120,
            )
            updated = update_schedule(db, sched.id, name="New", interval_minutes=60)
            assert updated is not None
            assert updated.name == "New"
            assert updated.interval_minutes == 60
        finally:
            db.close()


class TestDeleteSchedule:
    def test_delete_existing(self, fresh_db):
        db_mod = fresh_db
        from layan_engine.scheduler.engine import create_schedule, delete_schedule
        from layan_engine.storage.models import Schedule

        db = db_mod.get_session_factory()()
        try:
            sched = create_schedule(
                db, name="Tmp", platform="instagram",
                account_id="default",
            )
            assert delete_schedule(db, sched.id)
            assert db.query(Schedule).count() == 0
        finally:
            db.close()

    def test_delete_nonexistent(self, fresh_db):
        db_mod = fresh_db
        from layan_engine.scheduler.engine import delete_schedule

        db = db_mod.get_session_factory()()
        try:
            assert not delete_schedule(db, 999)
        finally:
            db.close()


class TestGetDueSchedules:
    def test_returns_due_only(self, fresh_db):
        db_mod = fresh_db
        from layan_engine.scheduler.engine import get_due_schedules
        from layan_engine.storage.models import Schedule

        db = db_mod.get_session_factory()()
        try:
            now = datetime.now(timezone.utc)
            due = Schedule(
                name="Due", platform="youtube", account_id="a",
                is_active=True, next_run_at=now - timedelta(minutes=5),
            )
            future = Schedule(
                name="Future", platform="tiktok", account_id="b",
                is_active=True, next_run_at=now + timedelta(hours=1),
            )
            inactive = Schedule(
                name="Off", platform="instagram", account_id="c",
                is_active=False, next_run_at=now - timedelta(minutes=5),
            )
            db.add_all([due, future, inactive])
            db.commit()

            result = get_due_schedules(db)
            assert len(result) == 1
            assert result[0].name == "Due"
        finally:
            db.close()


class TestSchedulerLoop:
    def test_initial_state(self):
        from layan_engine.scheduler.engine import SchedulerLoop

        loop = SchedulerLoop()
        assert not loop.is_running


# ── API route tests ──────────────────────────────────────────────


@pytest.fixture
def client(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setenv("DB_PATH", path)

    from importlib import reload
    import layan_engine.config
    reload(layan_engine.config)
    import layan_engine.storage.database as db_mod
    db_mod._engine = None
    db_mod._SessionLocal = None
    monkeypatch.setattr(db_mod, "settings", layan_engine.config.settings)

    from layan_engine.api.app import app
    with TestClient(app) as c:
        yield c

    if db_mod._engine:
        db_mod._engine.dispose()
        db_mod._engine = None
        db_mod._SessionLocal = None
    try:
        os.unlink(path)
    except PermissionError:
        pass


def test_list_schedules_empty(client):
    resp = client.get("/api/scheduler/")
    assert resp.status_code == 200
    assert resp.json() == []


def test_scheduler_status(client):
    resp = client.get("/api/scheduler/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "running" in data
    assert data["total_schedules"] == 0
    assert data["active_schedules"] == 0


def test_create_schedule(client):
    resp = client.post("/api/scheduler/", json={
        "name": "Test YT",
        "platform": "youtube",
        "account_id": "default",
        "interval_minutes": 60,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Test YT"
    assert data["platform"] == "youtube"
    assert data["is_active"] is True
    assert data["interval_minutes"] == 60
    assert data["id"] is not None


def test_create_schedule_invalid_platform(client):
    resp = client.post("/api/scheduler/", json={
        "name": "Bad",
        "platform": "twitter",
        "account_id": "x",
    })
    assert resp.status_code == 400


def test_create_schedule_min_interval(client):
    resp = client.post("/api/scheduler/", json={
        "name": "Too Fast",
        "platform": "youtube",
        "account_id": "x",
        "interval_minutes": 5,
    })
    assert resp.status_code == 400


def test_update_schedule(client):
    create = client.post("/api/scheduler/", json={
        "name": "Before",
        "platform": "tiktok",
        "account_id": "default",
    })
    sid = create.json()["id"]
    resp = client.put(f"/api/scheduler/{sid}", json={"name": "After", "is_active": False})
    assert resp.status_code == 200
    assert resp.json()["name"] == "After"
    assert resp.json()["is_active"] is False


def test_delete_schedule(client):
    create = client.post("/api/scheduler/", json={
        "name": "Del",
        "platform": "instagram",
        "account_id": "default",
    })
    sid = create.json()["id"]
    resp = client.delete(f"/api/scheduler/{sid}")
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True

    listing = client.get("/api/scheduler/")
    assert all(s["id"] != sid for s in listing.json())


def test_delete_nonexistent(client):
    resp = client.delete("/api/scheduler/999")
    assert resp.status_code == 404
