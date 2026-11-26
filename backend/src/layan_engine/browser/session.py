from __future__ import annotations

import asyncio
import json
from pathlib import Path

from playwright.async_api import BrowserContext, Playwright, async_playwright

from layan_engine.config import settings
from layan_engine.logging import get_logger

log = get_logger(__name__)

# Chrome locks a user-data dir, so only one run may hold a given profile at a time.
_profile_locks: dict[str, asyncio.Lock] = {}
_headless_user_agent: str | None = None

_LAUNCH_ARGS = ["--disable-blink-features=AutomationControlled"]
# --enable-automation sets navigator.webdriver and the "controlled by automated software"
# bar; Google sign-in rejects such browsers as "not secure".
_IGNORE_DEFAULT_ARGS = ["--enable-automation"]


class BrowserSession:
    """Opens a permanent Chrome profile per platform/account so sign-ins survive between runs.

    The profile keeps cookies, storage and device trust like a normal Chrome install. The old
    approach (fresh browser + cookies copied back in) looked like a new device every run, and
    platforms revoked those sessions.
    """

    def __init__(self):
        self._playwright: Playwright | None = None
        self._contexts: dict[str, BrowserContext] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def start(self):
        if self._playwright is None:
            self._playwright = await async_playwright().start()

    async def get_context(self, platform: str, account_id: str) -> BrowserContext:
        key = f"{platform}_{account_id}"
        if key in self._contexts:
            return self._contexts[key]

        await self.start()
        lock = _profile_locks.setdefault(key, asyncio.Lock())
        await lock.acquire()
        self._locks[key] = lock
        try:
            profile_dir = Path(settings.browser_profiles_dir) / platform / account_id
            user_data_dir = profile_dir / "chrome"
            first_run = not user_data_dir.exists()
            user_data_dir.mkdir(parents=True, exist_ok=True)

            kwargs = {
                "headless": settings.browser_headless,
                "viewport": {"width": 1280, "height": 900},
                "locale": "en-US",
                "timezone_id": settings.app_timezone,
                "args": _LAUNCH_ARGS,
                "ignore_default_args": _IGNORE_DEFAULT_ARGS,
            }
            if settings.browser_headless:
                # Headless Chrome's UA says "HeadlessChrome", which YouTube Studio rejects.
                kwargs["user_agent"] = await self._headless_ua()

            ctx = await self._launch(user_data_dir, kwargs)
            if first_run:
                await _import_legacy_cookies(ctx, profile_dir / "state.json")
        except BaseException:
            self._locks.pop(key, None)
            lock.release()
            raise

        self._contexts[key] = ctx
        log.info("browser_context_created", platform=platform, account=account_id, first_run=first_run)
        return ctx

    async def _launch(self, user_data_dir: Path, kwargs: dict) -> BrowserContext:
        chromium = self._playwright.chromium
        try:
            return await chromium.launch_persistent_context(str(user_data_dir), channel="chrome", **kwargs)
        except Exception as e:
            log.warning("chrome_unavailable_using_bundled_chromium", error=str(e).splitlines()[0][:200])
            return await chromium.launch_persistent_context(str(user_data_dir), **kwargs)

    async def _headless_ua(self) -> str:
        global _headless_user_agent
        if _headless_user_agent is None:
            try:
                b = await self._playwright.chromium.launch(channel="chrome", headless=True)
            except Exception:
                b = await self._playwright.chromium.launch(headless=True)
            version = b.version
            await b.close()
            _headless_user_agent = (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                f"(KHTML, like Gecko) Chrome/{version} Safari/537.36"
            )
        return _headless_user_agent

    async def save_context(self, platform: str, account_id: str):
        """No-op: the persistent Chrome profile saves its own state."""

    async def close_context(self, platform: str, account_id: str):
        key = f"{platform}_{account_id}"
        ctx = self._contexts.pop(key, None)
        try:
            if ctx:
                await ctx.close()
        finally:
            lock = self._locks.pop(key, None)
            if lock:
                lock.release()

    async def stop(self):
        for key in list(self._contexts):
            platform, account_id = key.split("_", 1)
            try:
                await self.close_context(platform, account_id)
            except Exception as e:
                log.warning("browser_context_close_failed", key=key, error=str(e)[:200])
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
        log.info("browser_stopped")

    @property
    def is_running(self) -> bool:
        return bool(self._contexts)


async def _import_legacy_cookies(ctx: BrowserContext, state_file: Path) -> None:
    """Carry sign-ins from the old per-run state.json into a brand-new profile."""
    if not state_file.is_file():
        return
    try:
        cookies = json.loads(state_file.read_text(encoding="utf-8")).get("cookies", [])
        if cookies:
            await ctx.add_cookies(cookies)
            log.info("legacy_cookies_imported", count=len(cookies), source=state_file.parent.name)
    except Exception as e:
        log.warning("legacy_cookie_import_failed", error=str(e)[:200])
