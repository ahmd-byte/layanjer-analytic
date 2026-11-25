"""Tests for YouTube worker utilities and YouTube API routes."""
import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from layan_engine.platforms.youtube.worker import YouTubeWorker


# ── Unit tests for metric parsing ─────────────────────────────────


class TestParseMetricValue:
    def test_plain_integer(self):
        assert YouTubeWorker._parse_metric_value("1234") == 1234.0

    def test_comma_separated(self):
        assert YouTubeWorker._parse_metric_value("1,234,567") == 1234567.0

    def test_k_suffix(self):
        assert YouTubeWorker._parse_metric_value("12.5K") == 12500.0

    def test_m_suffix(self):
        assert YouTubeWorker._parse_metric_value("2.3M") == 2300000.0

    def test_b_suffix(self):
        assert YouTubeWorker._parse_metric_value("1.1B") == 1100000000.0

    def test_percentage(self):
        assert YouTubeWorker._parse_metric_value("45.2%") == 45.2

    def test_negative(self):
        assert YouTubeWorker._parse_metric_value("-150") == -150.0

    def test_unicode_minus(self):
        assert YouTubeWorker._parse_metric_value("−150") == -150.0

    def test_time_hms(self):
        assert YouTubeWorker._parse_metric_value("1:23:45") == 5025.0

    def test_time_ms(self):
        assert YouTubeWorker._parse_metric_value("5:30") == 330.0

    def test_empty_returns_none(self):
        assert YouTubeWorker._parse_metric_value("") is None

    def test_non_numeric_returns_none(self):
        assert YouTubeWorker._parse_metric_value("N/A") is None

    def test_float(self):
        assert YouTubeWorker._parse_metric_value("3.14") == pytest.approx(3.14)


class TestNormalizeMetricName:
    def test_known_name(self):
        assert YouTubeWorker._normalize_metric_name("Watch time (hours)") == "watch_time_hours"

    def test_ctr(self):
        assert YouTubeWorker._normalize_metric_name("Impressions click-through rate") == "ctr"

    def test_generic_name(self):
        assert YouTubeWorker._normalize_metric_name("My Custom Metric!") == "my_custom_metric"

    def test_empty(self):
        assert YouTubeWorker._normalize_metric_name("") == ""


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


def test_youtube_accounts_empty(client):
    resp = client.get("/api/youtube/accounts")
    assert resp.status_code == 200
    assert resp.json() == []


def test_youtube_metrics_empty(client):
    resp = client.get("/api/youtube/metrics")
    assert resp.status_code == 200
    assert resp.json() == []


def test_youtube_content_metrics_empty(client):
    resp = client.get("/api/youtube/content-metrics")
    assert resp.status_code == 200
    assert resp.json() == []


def test_youtube_audience_metrics_empty(client):
    resp = client.get("/api/youtube/audience-metrics")
    assert resp.status_code == 200
    assert resp.json() == []
