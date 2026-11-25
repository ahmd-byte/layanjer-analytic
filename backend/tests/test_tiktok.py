"""Tests for TikTok worker utilities and TikTok API routes."""
import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from layan_engine.platforms.tiktok.worker import TikTokWorker


# ── Unit tests for metric parsing ─────────────────────────────────


class TestParseMetricValue:
    def test_plain_integer(self):
        assert TikTokWorker._parse_metric_value("5678") == 5678.0

    def test_comma_separated(self):
        assert TikTokWorker._parse_metric_value("1,234,567") == 1234567.0

    def test_k_suffix(self):
        assert TikTokWorker._parse_metric_value("45.2K") == 45200.0

    def test_m_suffix(self):
        assert TikTokWorker._parse_metric_value("3.1M") == 3100000.0

    def test_b_suffix(self):
        assert TikTokWorker._parse_metric_value("1.5B") == 1500000000.0

    def test_percentage(self):
        assert TikTokWorker._parse_metric_value("67.8%") == 67.8

    def test_negative(self):
        assert TikTokWorker._parse_metric_value("-200") == -200.0

    def test_unicode_minus(self):
        assert TikTokWorker._parse_metric_value("−300") == -300.0

    def test_nbsp_stripped(self):
        assert TikTokWorker._parse_metric_value("1 234") == 1234.0

    def test_empty_returns_none(self):
        assert TikTokWorker._parse_metric_value("") is None

    def test_non_numeric_returns_none(self):
        assert TikTokWorker._parse_metric_value("N/A") is None

    def test_float(self):
        assert TikTokWorker._parse_metric_value("2.71") == pytest.approx(2.71)


class TestNormalizeMetricName:
    def test_known_name(self):
        assert TikTokWorker._normalize_metric_name("Video views") == "video_views"

    def test_profile_views(self):
        assert TikTokWorker._normalize_metric_name("Profile views") == "profile_views"

    def test_followers(self):
        assert TikTokWorker._normalize_metric_name("Followers") == "followers_change"

    def test_generic_name(self):
        assert TikTokWorker._normalize_metric_name("Some Custom Stat!") == "some_custom_stat"

    def test_empty(self):
        assert TikTokWorker._normalize_metric_name("") == ""


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


def test_tiktok_accounts_empty(client):
    resp = client.get("/api/tiktok/accounts")
    assert resp.status_code == 200
    assert resp.json() == []


def test_tiktok_metrics_empty(client):
    resp = client.get("/api/tiktok/metrics")
    assert resp.status_code == 200
    assert resp.json() == []


def test_tiktok_content_metrics_empty(client):
    resp = client.get("/api/tiktok/content-metrics")
    assert resp.status_code == 200
    assert resp.json() == []


def test_tiktok_audience_metrics_empty(client):
    resp = client.get("/api/tiktok/audience-metrics")
    assert resp.status_code == 200
    assert resp.json() == []
