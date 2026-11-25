"""Tests for AI recovery engine, budget tracking, DOM extraction, and AI API routes."""
import json
import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from layan_engine.ai.budget import estimate_cost
from layan_engine.ai.dom_extractor import sanitize_dom
from layan_engine.ai.prompts import (
    CLASSIFY_CHALLENGE_PROMPT,
    EXTRACT_METRICS_PROMPT,
    INTERPRET_VALUE_PROMPT,
    RECOVER_SELECTOR_PROMPT,
    SYSTEM_PROMPT,
)
from layan_engine.ai.recovery import RecoveryEngine, RecoveryResult, _extract_json


# ── JSON extraction from AI responses ────────────────────────────


class TestExtractJson:
    def test_plain_array(self):
        assert _extract_json('[{"a": 1}]') == [{"a": 1}]

    def test_fenced_json(self):
        text = '```json\n[{"metric": "views"}]\n```'
        assert _extract_json(text) == [{"metric": "views"}]

    def test_fenced_no_lang(self):
        text = "```\n{\"key\": \"val\"}\n```"
        assert _extract_json(text) == {"key": "val"}

    def test_surrounding_text(self):
        text = 'Here are the results:\n```json\n[1, 2, 3]\n```\nDone.'
        assert _extract_json(text) == [1, 2, 3]

    def test_invalid_json_raises(self):
        with pytest.raises(json.JSONDecodeError):
            _extract_json("not json at all")

    def test_empty_array(self):
        assert _extract_json("[]") == []

    def test_nested_object(self):
        text = '{"classification": "login_required", "confidence": 0.9}'
        result = _extract_json(text)
        assert result["classification"] == "login_required"
        assert result["confidence"] == 0.9


# ── DOM sanitization ─────────────────────────────────────────────


class TestSanitizeDom:
    def test_strips_script_tags(self):
        html = '<div>Hello</div><script>alert("xss")</script><p>World</p>'
        result = sanitize_dom(html)
        assert "<script>" not in result
        assert "Hello" in result
        assert "World" in result

    def test_strips_style_tags(self):
        html = "<style>.a { color: red; }</style><div>Content</div>"
        result = sanitize_dom(html)
        assert "<style>" not in result
        assert "Content" in result

    def test_strips_sensitive_attributes(self):
        html = '<div data-token="abc123" data-session="xyz">Metric</div>'
        result = sanitize_dom(html)
        assert "abc123" not in result
        assert "xyz" not in result
        assert "Metric" in result

    def test_truncates_to_max_chars(self):
        html = "x" * 10000
        result = sanitize_dom(html, max_chars=100)
        assert len(result) == 100

    def test_collapses_whitespace(self):
        html = "<div>   \n\n\n   lots   \n   of   \n   space   </div>"
        result = sanitize_dom(html)
        assert "\n\n\n" not in result

    def test_empty_input(self):
        assert sanitize_dom("") == ""


# ── Budget estimation ────────────────────────────────────────────


class TestEstimateCost:
    def test_deepseek_chat(self):
        cost = estimate_cost("deepseek", "deepseek-chat", 1_000_000, 1_000_000)
        assert cost == pytest.approx(0.14 + 0.28, abs=0.001)

    def test_openai_gpt4o_mini(self):
        cost = estimate_cost("openai", "gpt-4o-mini", 1_000_000, 1_000_000)
        assert cost == pytest.approx(0.15 + 0.60, abs=0.001)

    def test_unknown_model_uses_default(self):
        cost = estimate_cost("unknown", "mystery-model", 1_000_000, 1_000_000)
        assert cost == pytest.approx(0.50 + 2.00, abs=0.001)

    def test_zero_tokens(self):
        cost = estimate_cost("deepseek", "deepseek-chat", 0, 0)
        assert cost == 0.0

    def test_small_usage(self):
        cost = estimate_cost("deepseek", "deepseek-chat", 1000, 500)
        assert cost > 0
        assert cost < 0.001


# ── Recovery engine configuration ────────────────────────────────


class TestRecoveryEngine:
    def test_not_configured_without_key(self, monkeypatch):
        monkeypatch.setattr("layan_engine.ai.recovery.settings.ai_api_key", "")
        engine = RecoveryEngine()
        assert not engine.is_configured

    def test_configured_with_key(self, monkeypatch):
        monkeypatch.setattr("layan_engine.ai.recovery.settings.ai_api_key", "sk-test123")
        engine = RecoveryEngine()
        assert engine.is_configured


class TestRecoveryResult:
    def test_default_failure(self):
        r = RecoveryResult()
        assert not r.success
        assert r.data is None
        assert r.error == ""

    def test_success_with_data(self):
        r = RecoveryResult(success=True, data=[{"metric": "views"}])
        assert r.success
        assert len(r.data) == 1


# ── Prompt templates ─────────────────────────────────────────────


class TestPrompts:
    def test_system_prompt_no_secrets(self):
        assert "password" not in SYSTEM_PROMPT.lower() or "never" in SYSTEM_PROMPT.lower()

    def test_extract_metrics_has_placeholders(self):
        assert "{platform}" in EXTRACT_METRICS_PROMPT
        assert "{dom_snippet}" in EXTRACT_METRICS_PROMPT

    def test_recover_selector_has_placeholders(self):
        assert "{selector}" in RECOVER_SELECTOR_PROMPT
        assert "{dom_structure}" in RECOVER_SELECTOR_PROMPT

    def test_classify_challenge_has_placeholders(self):
        assert "{platform}" in CLASSIFY_CHALLENGE_PROMPT
        assert "{text_excerpt}" in CLASSIFY_CHALLENGE_PROMPT

    def test_interpret_value_has_placeholders(self):
        assert "{label}" in INTERPRET_VALUE_PROMPT
        assert "{raw_value}" in INTERPRET_VALUE_PROMPT

    def test_extract_metrics_formats(self):
        formatted = EXTRACT_METRICS_PROMPT.format(
            platform="youtube", dom_snippet="<div>123K views</div>"
        )
        assert "youtube" in formatted
        assert "123K views" in formatted


# ── AI API routes ────────────────────────────────────────────────


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


def test_ai_status(client):
    resp = client.get("/api/ai/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "provider" in data
    assert "budget" in data
    assert "daily_limit" in data["budget"]
    assert "spent_today" in data["budget"]
    assert "within_budget" in data["budget"]


def test_ai_interpret_value_unconfigured(client):
    resp = client.post(
        "/api/ai/interpret-value",
        json={"platform": "youtube", "label": "Views", "raw_value": "12.5K"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("error") == "AI provider not configured"


def test_ai_classify_page_unconfigured(client):
    resp = client.post(
        "/api/ai/classify-page",
        json={
            "platform": "facebook",
            "url": "https://facebook.com/login",
            "title": "Log In",
            "text_excerpt": "Log into Facebook",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("error") == "AI provider not configured"
