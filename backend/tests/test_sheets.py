"""Tests for Google Sheets client, sync engine, and API routes."""
import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from layan_engine.sheets.client import SheetsClient, SheetsClientError
from layan_engine.sheets.sync import (
    SheetsSyncEngine,
    SyncResult,
    _ACCOUNT_HEADERS,
    _CONTENT_HEADERS,
    _SUMMARY_HEADERS,
)


# ── SheetsClient unit tests ─────────────────────────────────────


class TestSheetsClient:
    def test_not_configured_without_settings(self, monkeypatch):
        monkeypatch.setattr(
            "layan_engine.sheets.client.settings.google_sheets_credentials_path", ""
        )
        monkeypatch.setattr(
            "layan_engine.sheets.client.settings.google_sheets_spreadsheet_id", ""
        )
        client = SheetsClient()
        assert not client.is_configured

    def test_configured_with_both_settings(self, monkeypatch):
        monkeypatch.setattr(
            "layan_engine.sheets.client.settings.google_sheets_credentials_path",
            "/some/creds.json",
        )
        monkeypatch.setattr(
            "layan_engine.sheets.client.settings.google_sheets_spreadsheet_id",
            "abc123",
        )
        client = SheetsClient()
        assert client.is_configured

    def test_explicit_params_override(self):
        client = SheetsClient(
            credentials_path="/custom/path.json",
            spreadsheet_id="custom_id",
        )
        assert client.is_configured

    def test_test_connection_unconfigured(self, monkeypatch):
        monkeypatch.setattr(
            "layan_engine.sheets.client.settings.google_sheets_credentials_path", ""
        )
        monkeypatch.setattr(
            "layan_engine.sheets.client.settings.google_sheets_spreadsheet_id", ""
        )
        client = SheetsClient()
        result = client.test_connection()
        assert not result["connected"]
        assert "error" in result


# ── SyncResult ───────────────────────────────────────────────────


class TestSyncResult:
    def test_default(self):
        r = SyncResult()
        assert not r.success
        assert r.account_metrics_synced == 0
        assert r.content_metrics_synced == 0
        assert r.errors == []

    def test_success_with_counts(self):
        r = SyncResult(success=True, account_metrics_synced=10, content_metrics_synced=5, summary_rows=3)
        assert r.success
        assert r.account_metrics_synced == 10


# ── SheetsSyncEngine ─────────────────────────────────────────────


class TestSheetsSyncEngine:
    def test_not_configured(self, monkeypatch):
        monkeypatch.setattr(
            "layan_engine.sheets.client.settings.google_sheets_credentials_path", ""
        )
        monkeypatch.setattr(
            "layan_engine.sheets.client.settings.google_sheets_spreadsheet_id", ""
        )
        engine = SheetsSyncEngine()
        assert not engine.is_configured


# ── Headers ──────────────────────────────────────────────────────


class TestHeaders:
    def test_account_headers(self):
        assert "Platform" in _ACCOUNT_HEADERS
        assert "Metric" in _ACCOUNT_HEADERS
        assert "Value" in _ACCOUNT_HEADERS
        assert len(_ACCOUNT_HEADERS) == 9

    def test_content_headers(self):
        assert "Content ID" in _CONTENT_HEADERS
        assert len(_CONTENT_HEADERS) == 7

    def test_summary_headers(self):
        assert "Latest Value" in _SUMMARY_HEADERS
        assert len(_SUMMARY_HEADERS) == 6


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


def test_sheets_status(client):
    resp = client.get("/api/sheets/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "configured" in data
    assert "sync_queue" in data
    assert data["sync_queue"]["pending"] == 0


def test_sheets_test_connection_unconfigured(client):
    resp = client.post("/api/sheets/test-connection")
    assert resp.status_code == 200
    data = resp.json()
    assert not data["connected"]


def test_sheets_sync_unconfigured(client):
    resp = client.post("/api/sheets/sync")
    assert resp.status_code == 200
    data = resp.json()
    assert not data["success"]
    assert "not configured" in data["error"].lower()


def test_sheets_incremental_sync_unconfigured(client):
    resp = client.post("/api/sheets/sync-incremental")
    assert resp.status_code == 200
    data = resp.json()
    assert not data["success"]
