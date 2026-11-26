from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from layan_engine.config import settings
from layan_engine.logging import setup_logging
from layan_engine.storage.database import init_db

logger = logging.getLogger("layan.app")

_startup_time: datetime | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _startup_time
    setup_logging()

    from layan_engine.hardening.validation import validate_config
    validation = validate_config()
    if not validation.ok:
        for err in validation.errors:
            logger.error("STARTUP BLOCKED: %s", err)
        raise SystemExit("Configuration validation failed — check errors above")

    init_db()
    _startup_time = datetime.now(timezone.utc)

    from layan_engine.storage.runs import close_interrupted_runs
    close_interrupted_runs()

    from layan_engine.scheduler.engine import scheduler_loop
    await scheduler_loop.start()
    logger.info("Layan Je Analytics started on http://%s:%d", settings.backend_host, settings.backend_port)
    yield
    logger.info("Shutting down...")
    await scheduler_loop.stop()
    logger.info("Shutdown complete")


app = FastAPI(
    title="Layan Je Analytics",
    version="0.1.0",
    description="AI-powered social media analytics engine",
    lifespan=lifespan,
)

from layan_engine.hardening.middleware import ErrorHandlerMiddleware, RequestLoggingMiddleware  # noqa: E402
from layan_engine.hardening.rate_limit import RateLimitMiddleware  # noqa: E402

app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(ErrorHandlerMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        f"http://localhost:{settings.frontend_port}",
        f"http://127.0.0.1:{settings.frontend_port}",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health():
    from layan_engine.storage.database import get_engine

    db_ok = True
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(__import__("sqlalchemy").text("SELECT 1"))
    except Exception:
        db_ok = False

    from layan_engine.scheduler.engine import scheduler_loop

    return {
        "status": "ok" if db_ok else "degraded",
        "version": "0.1.0",
        "ai_provider": settings.ai_provider,
        "ai_configured": bool(settings.ai_api_key),
        "database": "connected" if db_ok else "error",
        "scheduler": "running" if scheduler_loop.is_running else "stopped",
        "uptime_seconds": (
            (datetime.now(timezone.utc) - _startup_time).total_seconds()
            if _startup_time else None
        ),
    }


from layan_engine.api.routes import accounts, ai, analytics, extraction, facebook, instagram, scheduler, sheets, system, tiktok, youtube  # noqa: E402

app.include_router(accounts.router, prefix="/api/accounts", tags=["accounts"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["analytics"])
app.include_router(extraction.router, prefix="/api/extraction", tags=["extraction"])
app.include_router(system.router, prefix="/api/system", tags=["system"])
app.include_router(ai.router, prefix="/api/ai", tags=["ai"])
app.include_router(scheduler.router, prefix="/api/scheduler", tags=["scheduler"])
app.include_router(sheets.router, prefix="/api/sheets", tags=["sheets"])
app.include_router(youtube.router, prefix="/api/youtube", tags=["youtube"])
app.include_router(tiktok.router, prefix="/api/tiktok", tags=["tiktok"])
app.include_router(instagram.router, prefix="/api/instagram", tags=["instagram"])
app.include_router(facebook.router, prefix="/api/facebook", tags=["facebook"])
