import os
import tempfile

import pytest
from fastapi.testclient import TestClient


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


def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "version" in data


def test_list_accounts(client):
    resp = client.get("/api/accounts/")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_system_status(client):
    resp = client.get("/api/system/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "accounts" in data
    assert "metrics" in data
