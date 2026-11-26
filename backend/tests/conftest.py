import os

# Runs before any test module imports layan_engine.config. Environment variables
# take precedence over the developer's .env, so tests never reach DeepSeek/OpenAI
# or a real Google Sheet with real credentials.
import tempfile

_TEST_DIR = tempfile.mkdtemp(prefix="layan-tests-")

os.environ.update({
    "AI_API_KEY": "",
    "GOOGLE_SHEETS_CREDENTIALS_PATH": "",
    "GOOGLE_SHEETS_SPREADSHEET_ID": "",
    # The real local_data/layan.db once collected test schedules ("Due", "Future"...)
    # that the app then ran for real. Point every test at a throwaway DB and profiles.
    "DB_PATH": os.path.join(_TEST_DIR, "layan-test.db"),
    "BROWSER_PROFILES_DIR": os.path.join(_TEST_DIR, "browser_profiles"),
})
