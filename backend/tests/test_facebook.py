"""Tests for Facebook worker utilities and Facebook API routes."""
import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from layan_engine.platforms.facebook.worker import FacebookWorker, _choose_target, _parse_targets


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


class TestParseDurationSeconds:
    def test_seconds_only(self):
        from layan_engine.platforms.facebook.worker import FacebookWorker
        assert FacebookWorker._parse_duration_seconds("0s") == 0.0

    def test_hours_minutes_seconds(self):
        from layan_engine.platforms.facebook.worker import FacebookWorker
        assert FacebookWorker._parse_duration_seconds("1h 2m 3s") == 3723.0

    def test_plain_number_is_not_a_duration(self):
        from layan_engine.platforms.facebook.worker import FacebookWorker
        assert FacebookWorker._parse_duration_seconds("12") is None


class TestChooseTarget:
    FOUND = {
        "pages": ["Other Page", "Brand Page"],
        "first": {"name": "Other Page", "asset_id": "111"},
        "matches": [{"target": "Brand Page", "name": "Brand Page", "asset_id": "222"}],
    }
    PROFILE = {"id": "999", "name": "Jane Doe"}

    def test_parse_targets(self):
        assert _parse_targets(" Brand Page, Jane Doe ,,") == ["Brand Page", "Jane Doe"]
        assert _parse_targets("") == []

    def test_no_targets_uses_first_managed_page(self):
        assert _choose_target([], self.FOUND, {}) == {"name": "Other Page", "asset_id": "111", "kind": "page"}

    def test_prefers_first_target_that_exists(self):
        chosen = _choose_target(["Missing", "brand page", "Jane Doe"], self.FOUND, self.PROFILE)
        assert chosen == {"name": "Brand Page", "asset_id": "222", "kind": "page"}

    def test_falls_back_to_signed_in_profile(self):
        chosen = _choose_target(["Missing", "Jane Doe"], self.FOUND, self.PROFILE)
        assert chosen == {"name": "Jane Doe", "asset_id": "999", "kind": "profile"}

    def test_never_picks_an_unlisted_page(self):
        chosen = _choose_target(["Missing"], self.FOUND, self.PROFILE)
        assert "error" in chosen
        assert "Other Page" in chosen["error"]  # lists what exists, but does not pull it
