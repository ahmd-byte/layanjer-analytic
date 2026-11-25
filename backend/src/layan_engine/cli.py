"""Command-line interface for Layan Je Analytics engine."""
from __future__ import annotations

import argparse
import sys


def main():
    parser = argparse.ArgumentParser(
        prog="layan",
        description="Layan Je Analytics — AI-powered social media analytics engine",
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("setup", help="Initialize database and configuration")
    sub.add_parser("run", help="Start the backend API server")
    sub.add_parser("health", help="Check system health")

    login_p = sub.add_parser("login", help="Open browser login for a platform")
    login_p.add_argument("--platform", required=True, choices=["youtube", "tiktok", "instagram", "facebook"])

    pull_p = sub.add_parser("pull", help="Pull analytics from platforms")
    pull_p.add_argument("--all", action="store_true", help="Pull all platforms")
    pull_p.add_argument("--platform", choices=["youtube", "tiktok", "instagram", "facebook"])

    backfill_p = sub.add_parser("backfill", help="Backfill historical data")
    backfill_p.add_argument("--from", dest="date_from", required=True)
    backfill_p.add_argument("--to", dest="date_to", required=True)
    backfill_p.add_argument("--platform", choices=["youtube", "tiktok", "instagram", "facebook"])

    sub.add_parser("retry-failed", help="Retry failed extraction jobs")
    sub.add_parser("sync", help="Synchronize pending records to Google Sheets")
    sub.add_parser("validate", help="Run data validation checks")
    sub.add_parser("backup", help="Create a database backup")

    args = parser.parse_args()

    if args.command == "setup":
        _cmd_setup()
    elif args.command == "run":
        _cmd_run()
    elif args.command == "health":
        _cmd_health()
    elif args.command == "login":
        _cmd_login(args.platform)
    elif args.command == "pull":
        _cmd_pull(all_platforms=args.all, platform=args.platform)
    elif args.command == "backfill":
        _cmd_backfill(args.date_from, args.date_to, args.platform)
    elif args.command == "sync":
        _cmd_sync()
    elif args.command == "validate":
        _cmd_validate()
    elif args.command == "backup":
        _cmd_backup()
    else:
        parser.print_help()
        sys.exit(1)


def _cmd_setup():
    from layan_engine.logging import setup_logging
    from layan_engine.storage.database import init_db

    setup_logging()
    print("Initializing database...")
    init_db()
    print("Database initialized successfully.")
    print("Run 'layan run' to start the API server.")


def _cmd_run():
    import uvicorn

    from layan_engine.config import settings

    print(f"Starting Layan Je Analytics on http://{settings.backend_host}:{settings.backend_port}")
    uvicorn.run(
        "layan_engine.api.app:app",
        host=settings.backend_host,
        port=settings.backend_port,
        reload=False,
    )


def _cmd_health():
    from layan_engine.config import settings
    from layan_engine.storage.database import get_engine

    print("Layan Je Analytics — Health Check")
    print(f"  Database: {settings.db_path}")
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        print("  Database: OK")
    except Exception as e:
        print(f"  Database: FAILED ({e})")

    print(f"  AI Provider: {settings.ai_provider}")
    print(f"  AI Configured: {bool(settings.ai_api_key)}")
    print(f"  Google Sheets: {'configured' if settings.google_sheets_spreadsheet_id else 'not configured'}")


def _cmd_login(platform: str):
    print(f"Opening browser login for {platform}...")
    print("(Browser login will be implemented in Phase 4+)")


def _cmd_pull(all_platforms: bool, platform: str | None):
    if all_platforms:
        print("Pulling analytics from all platforms...")
    elif platform:
        print(f"Pulling analytics from {platform}...")
    else:
        print("Specify --all or --platform")
    print("(Extraction will be implemented in Phase 4+)")


def _cmd_backfill(date_from: str, date_to: str, platform: str | None):
    print(f"Backfilling data from {date_from} to {date_to}")
    if platform:
        print(f"  Platform: {platform}")
    print("(Backfill will be implemented in Phase 4+)")


def _cmd_sync():
    print("Synchronizing pending records to Google Sheets...")
    print("(Sync will be implemented in Phase 9)")


def _cmd_validate():
    print("Running data validation checks...")
    print("(Validation will be implemented in Phase 3+)")


def _cmd_backup():
    import shutil
    from datetime import datetime

    from layan_engine.config import settings

    if not settings.db_path.exists():
        print("No database found to backup.")
        return

    settings.app_backup_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = settings.app_backup_dir / f"layan_{ts}.db"
    shutil.copy2(settings.db_path, dest)
    print(f"Backup created: {dest}")


if __name__ == "__main__":
    main()
