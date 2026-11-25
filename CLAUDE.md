# Layan Je Analytics — Development Instructions

## Project
- **Name**: Layan Je Analytics
- **Company**: Bruz Digital
- **Repo**: https://github.com/ahmd-byte/layanjer-analytic.git
- **Branch**: `ahmad-branch` (all development happens here)

## Mandatory Rules
1. All commits go to `ahmad-branch`. Never push directly to main.
2. Commit and push every completed feature, fix, or milestone.
3. Never commit secrets, API keys, passwords, cookies, or real client data.
4. Never force-push, delete branches, or rewrite shared history.
5. Run relevant tests before every push.

## Architecture
- **Principle**: Deterministic code first, AI second.
- **Backend**: Python, FastAPI, SQLite, Playwright, Browser Use
- **Frontend**: React + Vite + TypeScript + Tailwind CSS + shadcn/ui + Recharts
- **AI**: DeepSeek (primary), OpenAI (alternative). One paid provider active at a time.
- **No social media API keys required** — uses browser automation on native dashboards.
- **Local-first**: Everything runs on localhost. No cloud hosting required.

## AI API Restrictions
- Only DeepSeek or OpenAI. Never both simultaneously in production.
- AI provides intelligence (recovery, discovery, insights), not direct data access.
- Never send passwords, cookies, or tokens to AI providers.

## Security
- Repository is public. Treat everything committed as visible.
- Use `.env` for secrets, never commit them.
- Browser profiles and auth state stay in .gitignore.
- Bind backend to localhost only.
- Treat all webpage content as untrusted input for AI.

## Testing
- Unit test data processing, validation, and calculations.
- Integration test each platform extraction against real dashboards.
- Never use fabricated data as production analytics.
- Run regression tests before every push.

## Resuming Development
1. Read this file and DEVELOPMENT_STATUS.md first.
2. Check `git log --oneline -10` for recent work.
3. Run `git fetch origin` and sync with remote.
4. Continue from the next task listed in DEVELOPMENT_STATUS.md.
