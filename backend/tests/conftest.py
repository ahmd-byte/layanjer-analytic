import os

# Runs before any test module imports layan_engine.config. Environment variables
# take precedence over the developer's .env, so tests never reach DeepSeek/OpenAI
# or a real Google Sheet with real credentials.
os.environ.update({
    "AI_API_KEY": "",
    "GOOGLE_SHEETS_CREDENTIALS_PATH": "",
    "GOOGLE_SHEETS_SPREADSHEET_ID": "",
})
