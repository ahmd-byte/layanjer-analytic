"""Startup configuration validation.

Checks settings at boot and returns structured warnings for the operator.
No hard failures for optional features (AI, Sheets) — just warnings.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("layan.validation")


@dataclass
class ValidationResult:
    ok: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def validate_config() -> ValidationResult:
    from layan_engine.config import settings

    result = ValidationResult()

    if settings.backend_host not in ("127.0.0.1", "localhost", "::1"):
        result.errors.append(
            f"backend_host={settings.backend_host} — must be localhost for security"
        )
        result.ok = False

    if settings.backend_port < 1024 or settings.backend_port > 65535:
        result.errors.append(f"backend_port={settings.backend_port} — invalid port range")
        result.ok = False

    db_dir = Path(settings.db_path).parent
    if not db_dir.exists():
        try:
            db_dir.mkdir(parents=True, exist_ok=True)
            result.warnings.append(f"Created database directory: {db_dir}")
        except OSError as e:
            result.errors.append(f"Cannot create database directory {db_dir}: {e}")
            result.ok = False

    if not settings.ai_api_key:
        result.warnings.append("AI_API_KEY not set — AI recovery features disabled")

    if settings.ai_provider not in ("deepseek", "openai"):
        result.errors.append(f"ai_provider={settings.ai_provider} — must be deepseek or openai")
        result.ok = False

    if settings.ai_daily_budget <= 0:
        result.warnings.append(f"ai_daily_budget={settings.ai_daily_budget} — no AI budget allocated")

    if not settings.google_sheets_credentials_path:
        result.warnings.append("Google Sheets credentials not set — sync disabled")
    elif not Path(settings.google_sheets_credentials_path).exists():
        result.warnings.append(
            f"Google Sheets credentials file not found: {settings.google_sheets_credentials_path}"
        )

    if not settings.google_sheets_spreadsheet_id:
        result.warnings.append("Google Sheets spreadsheet ID not set — sync disabled")

    if settings.browser_timeout < 5000:
        result.warnings.append(f"browser_timeout={settings.browser_timeout}ms — may be too low")

    for msg in result.errors:
        logger.error("Config error: %s", msg)
    for msg in result.warnings:
        logger.warning("Config warning: %s", msg)

    return result
