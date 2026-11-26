"""Tests for production hardening: config validation, rate limiting, middleware, health check."""
import os
import tempfile
import time

import pytest
from fastapi.testclient import TestClient


# ── Config validation tests ──────────────────────────────────────


class TestValidation:
    def test_default_config_passes(self, monkeypatch):
        monkeypatch.setenv("BACKEND_HOST", "127.0.0.1")
        from importlib import reload
        import layan_engine.config
        reload(layan_engine.config)

        from layan_engine.hardening.validation import validate_config
        result = validate_config()
        assert result.ok

    def test_non_localhost_fails(self, monkeypatch):
        monkeypatch.setenv("BACKEND_HOST", "0.0.0.0")
        from importlib import reload
        import layan_engine.config
        reload(layan_engine.config)

        from layan_engine.hardening.validation import validate_config
        result = validate_config()
        assert not result.ok
        assert any("localhost" in e for e in result.errors)

    def test_missing_ai_key_warns(self, monkeypatch):
        monkeypatch.setenv("AI_API_KEY", "")
        monkeypatch.setenv("BACKEND_HOST", "127.0.0.1")
        from importlib import reload
        import layan_engine.config
        reload(layan_engine.config)

        from layan_engine.hardening.validation import validate_config
        result = validate_config()
        assert result.ok
        assert any("AI_API_KEY" in w for w in result.warnings)

    def test_missing_sheets_warns(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_SHEETS_CREDENTIALS_PATH", "")
        monkeypatch.setenv("GOOGLE_SHEETS_SPREADSHEET_ID", "")
        monkeypatch.setenv("BACKEND_HOST", "127.0.0.1")
        from importlib import reload
        import layan_engine.config
        reload(layan_engine.config)

        from layan_engine.hardening.validation import validate_config
        result = validate_config()
        assert result.ok
        assert any("Google Sheets" in w for w in result.warnings)

    def test_validation_result_defaults(self):
        from layan_engine.hardening.validation import ValidationResult
        r = ValidationResult()
        assert r.ok
        assert r.errors == []
        assert r.warnings == []


# ── Rate limiter tests ───────────────────────────────────────────


class TestRateLimiter:
    def test_allows_within_limit(self):
        from layan_engine.hardening.rate_limit import RateLimiter
        limiter = RateLimiter(max_requests=5, window_seconds=60)
        for _ in range(5):
            allowed, _ = limiter.is_allowed("test")
            assert allowed

    def test_blocks_over_limit(self):
        from layan_engine.hardening.rate_limit import RateLimiter
        limiter = RateLimiter(max_requests=3, window_seconds=60)
        for _ in range(3):
            limiter.is_allowed("test")
        allowed, remaining = limiter.is_allowed("test")
        assert not allowed
        assert remaining == 0

    def test_separate_keys(self):
        from layan_engine.hardening.rate_limit import RateLimiter
        limiter = RateLimiter(max_requests=2, window_seconds=60)
        limiter.is_allowed("a")
        limiter.is_allowed("a")
        allowed_a, _ = limiter.is_allowed("a")
        allowed_b, _ = limiter.is_allowed("b")
        assert not allowed_a
        assert allowed_b

    def test_remaining_decrements(self):
        from layan_engine.hardening.rate_limit import RateLimiter
        limiter = RateLimiter(max_requests=5, window_seconds=60)
        _, r1 = limiter.is_allowed("x")
        _, r2 = limiter.is_allowed("x")
        assert r1 == 4
        assert r2 == 3


# ── API route tests (health check, middleware) ───────────────────


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


def test_health_check_fields(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("ok", "degraded")
    assert "version" in data
    assert "database" in data
    assert "scheduler" in data
    assert "uptime_seconds" in data


def test_health_check_database_connected(client):
    resp = client.get("/api/health")
    data = resp.json()
    assert data["database"] == "connected"


def test_response_time_header(client):
    resp = client.get("/api/health")
    assert "X-Response-Time" in resp.headers


def test_rate_limit_header(client):
    resp = client.get("/api/health")
    assert "X-RateLimit-Remaining" in resp.headers


def test_404_returns_json(client):
    resp = client.get("/api/nonexistent")
    assert resp.status_code == 404


def test_system_status_still_works(client):
    resp = client.get("/api/system/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "accounts" in data
    assert "ai" in data
