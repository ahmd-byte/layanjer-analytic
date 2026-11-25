"""Tests for Facebook worker utilities and Facebook API routes."""
import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from layan_engine.platforms.facebook.worker import FacebookWorker


# ── Unit tests for metric parsing ─────────────────────────────────


class TestParseMetricValue:
    def test_plain_integer(self):
        assert FacebookWorker._parse_metric_value("4567") == 4567.0

    def test_comma_separated(self):
        assert FacebookWorker._parse_metric_value("3,456,789") == 3456789.0

    def test_k_suffix(self):
        assert FacebookWorker._parse_metric_value("56.7K") == 56700.0

    def test_m_suffix(self):
        assert FacebookWorker._parse_metric_value("4.5M") == 4500000.0

    def test_b_suffix(self):
        assert FacebookWorker._parse_metric_value("1.0B") == 1000000000.0

    def test_percentage(self):
        assert FacebookWorker._parse_metric_value("89.3%") == 89.3

    def test_negative(self):
        assert FacebookWorker._parse_metric_value("-75") == -75.0

    def test_unicode_minus(self):
        assert FacebookWorker._parse_metric_value("−25") == -25.0

    def test_plus_sign(self):
        assert FacebookWorker._parse_metric_value("+500") == 500.0

    def test_empty_returns_none(self):
        assert FacebookWorker._parse_metric_value("") is None

    def test_non_numeric_returns_none(self):
        assert FacebookWorker._parse_metric_value("N/A") is None

    def test_float(self):
        assert FacebookWorker._parse_metric_value("1.618") == pytest.approx(1.618)


class TestNormalizeMetricName:
    def test_page_reach(self):
        assert FacebookWorker._normalize_metric_name("Page reach") == "page_reach"

    def test_reach_alias(self):
        assert FacebookWorker._normalize_metric_name("Reach") == "page_reach"

    def test_new_followers(self):
        assert FacebookWorker._normalize_metric_name("New followers") == "new_followers"

    def test_post_engagement(self):
        assert FacebookWorker._normalize_metric_name("Post engagement") == "post_engagement"

    def test_video_views(self):
        assert FacebookWorker._normalize_metric_name("Video views") == "video_views"

    def test_generic_name(self):
        assert FacebookWorker._normalize_metric_name("Some Page Metric!") == "some_page_metric"

    def test_empty(self):
        assert FacebookWorker._normalize_metric_name("") == ""


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


def test_facebook_accounts_empty(client):
    resp = client.get("/api/facebook/accounts")
    assert resp.status_code == 200
    assert resp.json() == []


def test_facebook_metrics_empty(client):
    resp = client.get("/api/facebook/metrics")
    assert resp.status_code == 200
    assert resp.json() == []


def test_facebook_content_metrics_empty(client):
    resp = client.get("/api/facebook/content-metrics")
    assert resp.status_code == 200
    assert resp.json() == []


def test_facebook_audience_metrics_empty(client):
    resp = client.get("/api/facebook/audience-metrics")
    assert resp.status_code == 200
    assert resp.json() == []
