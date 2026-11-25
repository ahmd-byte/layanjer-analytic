# Technology Decisions

## Browser Automation: Playwright Python
**Decision**: Use Playwright Python as the primary deterministic browser engine.
**Alternatives considered**: Selenium, Puppeteer
**Rationale**: Microsoft-maintained, excellent Python support, persistent browser contexts, semantic locators, auto-waiting, trace viewer for debugging, reliable on Windows. Industry standard for browser automation.

## AI Browser Recovery: Browser Use
**Decision**: Use Browser Use for AI-assisted browser navigation and recovery.
**Alternatives considered**: Stagehand, Skyvern
**Rationale**: Supports DeepSeek and OpenAI, runs locally, integrates with Playwright, provides structured extraction and tool calling. Stagehand requires Browserbase cloud for some features. Skyvern has AGPL licensing concerns.

## Backend Framework: FastAPI
**Decision**: FastAPI for the local API server.
**Rationale**: Modern async Python, automatic OpenAPI docs, Pydantic integration, lightweight, well-suited for local-first applications.

## Database: SQLite + SQLAlchemy
**Decision**: SQLite as primary database, SQLAlchemy for ORM.
**Rationale**: Zero-configuration, file-based, suitable for local single-user workloads. No server process needed. SQLAlchemy provides migrations via Alembic.

## AI Provider: DeepSeek (primary), OpenAI (fallback)
**Decision**: Provider-agnostic interface, DeepSeek preferred.
**Rationale**: Cost-effective, supports tool calling and structured output. OpenAI as proven fallback. Only one active at a time.

## Frontend: React + Vite + TypeScript + Tailwind CSS + shadcn/ui + Recharts
**Decision**: Modern React SPA for the analytics dashboard.
**Alternatives considered**: Streamlit, Next.js, Metabase
**Rationale**: Full control over UI, runs on localhost, no server deployment needed. Vite for fast dev experience. shadcn/ui for professional components. Recharts for analytics charts. Streamlit too limited for complex dashboards. Metabase too heavy for single-user local use.

## Data Validation: Pydantic
**Decision**: Pydantic for schema validation and AI response parsing.
**Rationale**: Already required by FastAPI, excellent for structured output validation, type safety.

## Data Processing: Pandas
**Decision**: Pandas for CSV/Excel processing and analytics normalization.
**Rationale**: Mature, well-documented, sufficient for our data volumes. Polars not needed unless performance bottleneck appears.

## Scheduling: APScheduler
**Decision**: APScheduler for job scheduling.
**Rationale**: Python-native, supports persistent job stores, cron-like scheduling, integrates with async frameworks.

## Retry: Tenacity
**Decision**: Tenacity for retry logic.
**Rationale**: Flexible retry policies, exponential backoff, jitter, clean decorator API.

## Google Sheets: gspread
**Decision**: gspread for Sheets integration.
**Rationale**: Simple API, well-maintained, handles OAuth and service accounts.

## Testing: Pytest + Vitest
**Decision**: Pytest for backend, Vitest for frontend.
**Rationale**: Industry standards for their respective ecosystems.

## Code Quality: Ruff
**Decision**: Ruff for Python linting and formatting.
**Rationale**: Fast, replaces multiple tools (flake8, black, isort), single configuration.
