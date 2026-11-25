from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from layan_engine.config import settings
from layan_engine.logging import setup_logging
from layan_engine.storage.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    init_db()
    yield


app = FastAPI(
    title="Layan Je Analytics",
    version="0.1.0",
    description="AI-powered social media analytics engine",
    lifespan=lifespan,
)

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
    return {
        "status": "ok",
        "version": "0.1.0",
        "ai_provider": settings.ai_provider,
        "ai_configured": bool(settings.ai_api_key),
    }


from layan_engine.api.routes import accounts, ai, analytics, extraction, facebook, instagram, sheets, system, tiktok, youtube  # noqa: E402

app.include_router(accounts.router, prefix="/api/accounts", tags=["accounts"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["analytics"])
app.include_router(extraction.router, prefix="/api/extraction", tags=["extraction"])
app.include_router(system.router, prefix="/api/system", tags=["system"])
app.include_router(ai.router, prefix="/api/ai", tags=["ai"])
app.include_router(sheets.router, prefix="/api/sheets", tags=["sheets"])
app.include_router(youtube.router, prefix="/api/youtube", tags=["youtube"])
app.include_router(tiktok.router, prefix="/api/tiktok", tags=["tiktok"])
app.include_router(instagram.router, prefix="/api/instagram", tags=["instagram"])
app.include_router(facebook.router, prefix="/api/facebook", tags=["facebook"])
