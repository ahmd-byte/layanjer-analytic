"""End-to-end smoke tests — verify every API route returns valid responses.

These tests exercise the full middleware stack (rate limiting, error handling,
request logging) and confirm all routers are mounted and responding. They use
a fresh temporary DB per test session, same as the other test files.
"""
import os
import tempfile
from datetime import datetime, timezone
from uuid import uuid4

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


# ── Health & system ──────────────────────────────────────────────


class TestHealthSystem:
    def test_health_ok(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        d = r.json()
        assert d["status"] == "ok"
        assert d["database"] == "connected"
        assert d["version"] == "0.1.0"
        assert isinstance(d["uptime_seconds"], (int, float, type(None)))

    def test_system_status_shape(self, client):
        r = client.get("/api/system/status")
        assert r.status_code == 200
        d = r.json()
        for key in ("accounts", "metrics", "sync", "last_extraction", "ai", "google_sheets"):
            assert key in d, f"Missing key: {key}"


# ── Accounts ─────────────────────────────────────────────────────


class TestAccounts:
    def test_list_empty(self, client):
        r = client.get("/api/accounts/")
        assert r.status_code == 200
        assert r.json() == []


# ── Extraction ───────────────────────────────────────────────────


class TestExtraction:
    def test_runs_empty(self, client):
        r = client.get("/api/extraction/runs")
        assert r.status_code == 200
        assert r.json() == []

    def test_run_not_found(self, client):
        r = client.get(f"/api/extraction/runs/{uuid4()}")
        assert r.status_code == 200
        assert "error" in r.json()


# ── Analytics ────────────────────────────────────────────────────


class TestAnalytics:
    def test_account_metrics_empty(self, client):
        r = client.get("/api/analytics/account-metrics")
        assert r.status_code == 200
        assert r.json() == []

    def test_content_metrics_empty(self, client):
        r = client.get("/api/analytics/content-metrics")
        assert r.status_code == 200
        assert r.json() == []

    def test_trends_empty(self, client):
        r = client.get("/api/analytics/trends")
        assert r.status_code == 200
        assert r.json() == []

    def test_platform_summary_empty(self, client):
        r = client.get("/api/analytics/platform-summary")
        assert r.status_code == 200
        assert r.json() == []

    def test_extraction_history_empty(self, client):
        r = client.get("/api/analytics/extraction-history")
        assert r.status_code == 200
        assert r.json() == []


# ── AI ───────────────────────────────────────────────────────────


class TestAI:
    def test_ai_status(self, client):
        r = client.get("/api/ai/status")
        assert r.status_code == 200
        d = r.json()
        assert "provider" in d
        assert "budget" in d


# ── Sheets ───────────────────────────────────────────────────────


class TestSheets:
    def test_sheets_status(self, client):
        r = client.get("/api/sheets/status")
        assert r.status_code == 200
        d = r.json()
        assert "configured" in d
        assert "sync_queue" in d


# ── Scheduler ────────────────────────────────────────────────────


class TestScheduler:
    def test_list_empty(self, client):
        r = client.get("/api/scheduler/")
        assert r.status_code == 200
        assert r.json() == []

    def test_status(self, client):
        r = client.get("/api/scheduler/status")
        assert r.status_code == 200
        d = r.json()
        assert "running" in d
        assert "total_schedules" in d

    def test_crud_lifecycle(self, client):
        # Create
        r = client.post("/api/scheduler/", json={
            "name": "smoke-test",
            "platform": "youtube",
            "account_id": "smoke",
            "interval_minutes": 60,
        })
        assert r.status_code == 200
        sid = r.json()["id"]

        # Read
        r = client.get("/api/scheduler/")
        assert len(r.json()) == 1

        # Update
        r = client.put(f"/api/scheduler/{sid}", json={"name": "updated"})
        assert r.status_code == 200
        assert r.json()["name"] == "updated"

        # Delete
        r = client.delete(f"/api/scheduler/{sid}")
        assert r.status_code == 200

        r = client.get("/api/scheduler/")
        assert r.json() == []


# ── Platform routes (YouTube, TikTok, Instagram, Facebook) ───────


PLATFORMS = ["youtube", "tiktok", "instagram", "facebook"]


@pytest.mark.parametrize("platform", PLATFORMS)
class TestPlatformRoutes:
    def test_accounts_empty(self, client, platform):
        r = client.get(f"/api/{platform}/accounts")
        assert r.status_code == 200
        assert r.json() == []

    def test_metrics_empty(self, client, platform):
        r = client.get(f"/api/{platform}/metrics")
        assert r.status_code == 200
        assert r.json() == []


# ── Middleware integration ───────────────────────────────────────


class TestMiddleware:
    def test_response_time_header_on_every_request(self, client):
        for path in ["/api/health", "/api/accounts/", "/api/system/status"]:
            r = client.get(path)
            assert "X-Response-Time" in r.headers, f"Missing X-Response-Time on {path}"

    def test_rate_limit_header_present(self, client):
        r = client.get("/api/health")
        assert "X-RateLimit-Remaining" in r.headers

    def test_cors_headers_on_preflight(self, client):
        r = client.options(
            "/api/health",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert r.status_code == 200
        assert "access-control-allow-origin" in r.headers


# ── Cross-component integration ──────────────────────────────────


class TestIntegration:
    def test_scheduler_creates_then_analytics_unaffected(self, client):
        """Verify scheduler CRUD doesn't leak into analytics responses."""
        client.post("/api/scheduler/", json={
            "name": "int-test",
            "platform": "tiktok",
            "account_id": "int",
            "interval_minutes": 30,
        })
        r = client.get("/api/analytics/extraction-history")
        assert r.status_code == 200
        assert r.json() == []

    def test_health_reflects_scheduler_state(self, client):
        health = client.get("/api/health").json()
        sched = client.get("/api/scheduler/status").json()
        assert health["scheduler"] == ("running" if sched["running"] else "stopped")

    def test_all_routes_return_json(self, client):
        """Every GET route must return valid JSON."""
        get_routes = [
            "/api/health",
            "/api/system/status",
            "/api/accounts/",
            "/api/extraction/runs",
            "/api/analytics/account-metrics",
            "/api/analytics/content-metrics",
            "/api/analytics/trends",
            "/api/analytics/platform-summary",
            "/api/analytics/extraction-history",
            "/api/ai/status",
            "/api/sheets/status",
            "/api/scheduler/",
            "/api/scheduler/status",
            "/api/youtube/accounts",
            "/api/youtube/metrics",
            "/api/tiktok/accounts",
            "/api/tiktok/metrics",
            "/api/instagram/accounts",
            "/api/instagram/metrics",
            "/api/facebook/accounts",
            "/api/facebook/metrics",
        ]
        for path in get_routes:
            r = client.get(path)
            assert r.status_code == 200, f"{path} returned {r.status_code}"
            r.json()  # will raise if not valid JSON
