from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # AI
    ai_provider: Literal["deepseek", "openai"] = "deepseek"
    ai_api_key: str = ""
    ai_base_url: str = "https://api.deepseek.com"
    ai_primary_model: str = "deepseek-chat"
    ai_reasoning_model: str = "deepseek-reasoner"
    ai_vision_model: str = ""
    ai_request_timeout: int = 60
    ai_max_retries: int = 3
    ai_daily_budget: float = 5.00

    # Google Sheets
    google_sheets_credentials_path: str = ""
    google_sheets_spreadsheet_id: str = ""

    # App
    app_timezone: str = "Asia/Kuala_Lumpur"
    app_log_level: str = "INFO"
    app_data_dir: Path = Field(default=_ROOT / "local_data")
    app_backup_dir: Path = Field(default=_ROOT / "backups")

    # Browser
    browser_headless: bool = False
    browser_profiles_dir: Path = Field(default=_ROOT / "browser_profiles")
    browser_timeout: int = 30000

    # Backend
    backend_host: str = "127.0.0.1"
    backend_port: int = 8000

    # Frontend
    frontend_port: int = 5173

    # Database
    db_path: Path = Field(default=_ROOT / "local_data" / "layan.db")


settings = Settings()
