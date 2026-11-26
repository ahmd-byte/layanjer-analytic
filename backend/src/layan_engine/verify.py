"""Startup verification — run before or after booting the server.

Usage:  python -m layan_engine.verify
Exits 0 if all checks pass, 1 otherwise.
"""
from __future__ import annotations

import sys


def main() -> int:
    checks_passed = 0
    checks_failed = 0

    def ok(label: str) -> None:
        nonlocal checks_passed
        checks_passed += 1
        print(f"  [OK]  {label}")

    def fail(label: str, detail: str = "") -> None:
        nonlocal checks_failed
        checks_failed += 1
        msg = f"  [FAIL] {label}"
        if detail:
            msg += f" — {detail}"
        print(msg)

    print("Layan Je Analytics — Startup Verification\n")

    # 1. Config loads
    print("Config:")
    try:
        from layan_engine.config import settings
        ok(f"Loaded (host={settings.backend_host}, port={settings.backend_port})")
    except Exception as exc:
        fail("Config load", str(exc))
        return 1

    # 2. Config validation
    print("\nValidation:")
    try:
        from layan_engine.hardening.validation import validate_config
        result = validate_config()
        if result.ok:
            ok("Config validation passed")
        else:
            fail("Config validation", "; ".join(result.errors))
        for w in result.warnings:
            print(f"  [WARN] {w}")
    except Exception as exc:
        fail("Config validation", str(exc))

    # 3. Database
    print("\nDatabase:")
    try:
        from layan_engine.storage.database import init_db, get_engine
        init_db()
        engine = get_engine()
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        ok(f"Connected ({settings.db_path})")
    except Exception as exc:
        fail("Database", str(exc))

    # 4. Tables
    try:
        from sqlalchemy import inspect as sa_inspect
        engine = get_engine()
        inspector = sa_inspect(engine)
        tables = inspector.get_table_names()
        expected = {"accounts", "account_metrics", "content_metrics", "extraction_runs", "schedules"}
        missing = expected - set(tables)
        if missing:
            fail("Tables", f"Missing: {missing}")
        else:
            ok(f"All tables present ({len(tables)} total)")
    except Exception as exc:
        fail("Tables", str(exc))

    # 5. Middleware stack
    print("\nMiddleware:")
    try:
        from layan_engine.api.app import app
        middleware_names = [m.cls.__name__ for m in app.user_middleware if hasattr(m, "cls")]
        ok(f"Registered: {', '.join(middleware_names)}")
    except Exception as exc:
        fail("Middleware", str(exc))

    # 6. Routes
    print("\nRoutes:")
    try:
        from layan_engine.api.app import app
        route_paths = sorted({r.path for r in app.routes if hasattr(r, "path")})
        api_routes = [p for p in route_paths if p.startswith("/api")]
        ok(f"{len(api_routes)} API endpoints registered")
    except Exception as exc:
        fail("Routes", str(exc))

    # 7. AI provider
    print("\nAI:")
    if settings.ai_api_key:
        ok(f"Provider: {settings.ai_provider}, model: {settings.ai_primary_model}")
    else:
        print("  [WARN] AI_API_KEY not set — AI recovery disabled")

    # 8. Google Sheets
    print("\nGoogle Sheets:")
    if settings.google_sheets_credentials_path and settings.google_sheets_spreadsheet_id:
        ok("Configured")
    else:
        print("  [WARN] Not configured — sync disabled")

    # Summary
    total = checks_passed + checks_failed
    print(f"\n{'='*50}")
    print(f"  {checks_passed}/{total} checks passed", end="")
    if checks_failed:
        print(f", {checks_failed} failed")
        return 1
    else:
        print(" — system ready")
        return 0


if __name__ == "__main__":
    sys.exit(main())
