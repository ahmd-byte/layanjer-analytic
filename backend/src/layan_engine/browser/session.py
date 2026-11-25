from __future__ import annotations

from pathlib import Path

from playwright.async_api import Browser, BrowserContext, Playwright, async_playwright

from layan_engine.config import settings
from layan_engine.logging import get_logger

log = get_logger(__name__)


class BrowserSession:
    """Manages persistent browser contexts per platform/account."""

    def __init__(self):
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._contexts: dict[str, BrowserContext] = {}

    async def start(self):
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=settings.browser_headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        log.info("browser_started", headless=settings.browser_headless)

    async def get_context(self, platform: str, account_id: str) -> BrowserContext:
        key = f"{platform}_{account_id}"
        if key in self._contexts:
            return self._contexts[key]

        profile_dir = Path(settings.browser_profiles_dir) / platform / account_id
        profile_dir.mkdir(parents=True, exist_ok=True)
        storage_path = profile_dir / "state.json"

        ctx_kwargs = {
            "viewport": {"width": 1280, "height": 900},
            "locale": "en-US",
            "timezone_id": settings.app_timezone,
        }
        if storage_path.exists():
            ctx_kwargs["storage_state"] = str(storage_path)

        ctx = await self._browser.new_context(**ctx_kwargs)
        self._contexts[key] = ctx
        log.info("browser_context_created", platform=platform, account=account_id)
        return ctx

    async def save_context(self, platform: str, account_id: str):
        key = f"{platform}_{account_id}"
        ctx = self._contexts.get(key)
        if not ctx:
            return

        profile_dir = Path(settings.browser_profiles_dir) / platform / account_id
        profile_dir.mkdir(parents=True, exist_ok=True)
        storage_path = profile_dir / "state.json"
        await ctx.storage_state(path=str(storage_path))
        log.info("browser_context_saved", platform=platform, account=account_id)

    async def close_context(self, platform: str, account_id: str):
        key = f"{platform}_{account_id}"
        ctx = self._contexts.pop(key, None)
        if ctx:
            await self.save_context(platform, account_id)
            await ctx.close()

    async def stop(self):
        for key in list(self._contexts.keys()):
            parts = key.split("_", 1)
            if len(parts) == 2:
                await self.save_context(parts[0], parts[1])
            ctx = self._contexts.pop(key)
            await ctx.close()

        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        log.info("browser_stopped")

    @property
    def is_running(self) -> bool:
        return self._browser is not None and self._browser.is_connected()
