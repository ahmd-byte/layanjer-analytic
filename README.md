# Layan Je Analytics

AI-powered social media analytics system by [Bruz Digital](https://bruzdigital.com).

Collects, normalizes, and visualizes analytics from YouTube, TikTok, Instagram, and Facebook using browser automation and AI-assisted extraction.

## Status

🚧 **Under active development** — Phase 1: Project initialization

## Features (Planned)

- **Multi-platform analytics** — YouTube, TikTok, Instagram, Facebook
- **Hybrid extraction engine** — Native exports → DOM extraction → OCR → AI vision
- **Persistent browser sessions** — Login once, collect daily
- **Self-healing workflows** — AI-assisted recovery from failures
- **Local SQLite database** — Source of truth for all analytics
- **Google Sheets sync** — Automated reporting destination
- **Analytics dashboard** — Local React dashboard with charts and filters
- **Operations control** — Monitor extraction jobs, browser health, data quality

## Architecture

```
Authenticated dashboards
  → Playwright browser automation
  → Platform-specific extraction workers
  → Hybrid extraction engine
  → Data validation
  → SQLite database
  → FastAPI backend
  → React dashboard
  → Google Sheets sync
```

**Principle**: Deterministic code first, AI second.

## Requirements

- Python 3.12+
- Node.js 22+
- Git
- Chromium browser (installed by Playwright)
- DeepSeek or OpenAI API key (for AI features)
- Google OAuth credentials (for Sheets sync)

## Quick Start

```powershell
# Clone
git clone https://github.com/ahmd-byte/layanjer-analytic.git
cd layanjer-analytic

# Backend setup
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
playwright install chromium

# Frontend setup
cd ../frontend
npm install

# Configure
cp .env.example .env
# Edit .env with your API keys

# Run
cd ..
.\start.ps1
```

## Development

All development happens on the `ahmad-branch` branch.

```powershell
git checkout ahmad-branch
git pull origin ahmad-branch
```

## License

Proprietary — Bruz Digital. All rights reserved.
