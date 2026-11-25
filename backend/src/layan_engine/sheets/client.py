"""Google Sheets client — wraps gspread for authenticated spreadsheet access.

Credentials path and spreadsheet ID come from settings (.env).
The credentials file is a Google Service Account JSON — never committed.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from layan_engine.config import settings
from layan_engine.logging import get_logger

log = get_logger(__name__)


class SheetsClientError(Exception):
    pass


class SheetsClient:
    """Thin wrapper around gspread for reading/writing spreadsheet data."""

    def __init__(
        self,
        credentials_path: str | None = None,
        spreadsheet_id: str | None = None,
    ):
        self._creds_path = credentials_path or settings.google_sheets_credentials_path
        self._spreadsheet_id = spreadsheet_id or settings.google_sheets_spreadsheet_id
        self._gc = None
        self._spreadsheet = None

    @property
    def is_configured(self) -> bool:
        return bool(self._creds_path and self._spreadsheet_id)

    def _ensure_connected(self):
        if self._gc is not None:
            return
        try:
            import gspread
            from google.oauth2.service_account import Credentials
        except ImportError as e:
            raise SheetsClientError(
                "Google Sheets dependencies not installed. "
                "Run: pip install layan-engine[sheets]"
            ) from e

        creds_file = Path(self._creds_path)
        if not creds_file.exists():
            raise SheetsClientError(f"Credentials file not found: {creds_file}")

        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = Credentials.from_service_account_file(str(creds_file), scopes=scopes)
        self._gc = gspread.authorize(creds)
        log.info("sheets_client_connected")

    def open_spreadsheet(self):
        self._ensure_connected()
        try:
            self._spreadsheet = self._gc.open_by_key(self._spreadsheet_id)
            log.info("spreadsheet_opened", spreadsheet_id=self._spreadsheet_id)
        except Exception as e:
            raise SheetsClientError(f"Cannot open spreadsheet: {e}") from e
        return self._spreadsheet

    def get_or_create_worksheet(self, title: str, rows: int = 1000, cols: int = 20):
        if self._spreadsheet is None:
            self.open_spreadsheet()
        try:
            return self._spreadsheet.worksheet(title)
        except Exception:
            log.info("worksheet_created", title=title)
            return self._spreadsheet.add_worksheet(title=title, rows=rows, cols=cols)

    def write_header(self, worksheet, headers: list[str]):
        existing = worksheet.row_values(1)
        if existing != headers:
            worksheet.update(range_name="A1", values=[headers])
            log.info("header_written", sheet=worksheet.title, cols=len(headers))

    def append_rows(self, worksheet, rows: list[list[Any]]):
        if not rows:
            return 0
        worksheet.append_rows(rows, value_input_option="USER_ENTERED")
        log.info("rows_appended", sheet=worksheet.title, count=len(rows))
        return len(rows)

    def clear_and_write(self, worksheet, headers: list[str], rows: list[list[Any]]):
        worksheet.clear()
        all_data = [headers] + rows
        worksheet.update(range_name="A1", values=all_data, value_input_option="USER_ENTERED")
        log.info("sheet_replaced", sheet=worksheet.title, rows=len(rows))
        return len(rows)

    def get_all_values(self, worksheet) -> list[list[str]]:
        return worksheet.get_all_values()

    def test_connection(self) -> dict[str, Any]:
        """Test that credentials and spreadsheet access work."""
        try:
            self._ensure_connected()
            ss = self.open_spreadsheet()
            return {
                "connected": True,
                "spreadsheet_title": ss.title,
                "sheet_count": len(ss.worksheets()),
                "url": ss.url,
            }
        except SheetsClientError as e:
            return {"connected": False, "error": str(e)}
        except Exception as e:
            return {"connected": False, "error": str(e)}
