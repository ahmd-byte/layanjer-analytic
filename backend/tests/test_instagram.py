"""Tests for Instagram worker utilities and Instagram API routes."""
import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from layan_engine.platforms.instagram.worker import InstagramWorker


# ── Unit tests for metric parsing ─────────────────────────────────


class TestParseMetricValue:
    def test_plain_integer(self):
        assert InstagramWorker._parse_metric_value("9876") == 9876.0

    def test_comma_separated(self):
        assert InstagramWorker._parse_metric_value("2,345,678") == 2345678.0

    def test_k_suffix(self):
        assert InstagramWorker._parse_metric_value("78.3K") == 78300.0

    def test_m_suffix(self):
        assert InstagramWorker._parse_metric_value("1.2M") == 1200000.0

    def test_b_suffix(self):
        assert InstagramWorker._parse_metric_value("2.0B") == 2000000000.0

    def test_percentage(self):
        assert InstagramWorker._parse_metric_value("12.5%") == 12.5

    def test_negative(self):
        assert InstagramWorker._parse_metric_value("-50") == -50.0

    def test_unicode_minus(self):
        assert InstagramWorker._parse_metric_value("−100") == -100.0

    def test_plus_sign(self):
        assert InstagramWorker._parse_metric_value("+250") == 250.0

    def test_empty_returns_none(self):
        assert InstagramWorker._parse_metric_value("") is None

    def test_non_numeric_returns_none(self):
        assert InstagramWorker._parse_metric_value("N/A") is None

    def test_float(self):
        assert InstagramWorker._parse_metric_value("6.28") == pytest.approx(6.28)


class TestNormalizeMetricName:
    def test_accounts_reached(self):
        assert InstagramWorker._normalize_metric_name("Accounts reached") == "accounts_reached"

    def test_reach_alias(self):
        assert InstagramWorker._normalize_metric_name("Reach") == "accounts_reached"

    def test_total_followers(self):
        assert InstagramWorker._normalize_metric_name("Total followers") == "total_followers"

    def test_profile_visits(self):
        assert InstagramWorker._normalize_metric_name("Profile visits") == "profile_visits"

    def test_reels_plays(self):
        assert InstagramWorker._normalize_metric_name("Reels plays") == "reels_plays"

    def test_generic_name(self):
        assert InstagramWorker._normalize_metric_name("Some Custom Insight!") == "some_custom_insight"

    def test_empty(self):
        assert InstagramWorker._normalize_metric_name("") == ""


# ── API route tests ───────────────────────────────────────────────


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


def test_instagram_accounts_empty(client):
    resp = client.get("/api/instagram/accounts")
    assert resp.status_code == 200
    assert resp.json() == []


def test_instagram_metrics_empty(client):
    resp = client.get("/api/instagram/metrics")
    assert resp.status_code == 200
    assert resp.json() == []


def test_instagram_content_metrics_empty(client):
    resp = client.get("/api/instagram/content-metrics")
    assert resp.status_code == 200
    assert resp.json() == []


def test_instagram_audience_metrics_empty(client):
    resp = client.get("/api/instagram/audience-metrics")
    assert resp.status_code == 200
    assert resp.json() == []
