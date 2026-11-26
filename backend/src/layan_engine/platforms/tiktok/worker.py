"""TikTok Analytics extraction worker.

Extracts analytics from TikTok Creator Center / Analytics
(analytics.tiktok.com) using Playwright browser automation.
Falls back to DOM extraction when native export is unavailable.
"""
from __future__ import annotations

import re
from typing import Any

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from layan_engine.browser.challenge import detect_challenge
from layan_engine.browser.session import BrowserSession
from layan_engine.config import settings
from layan_engine.logging import get_logger
from layan_engine.platforms.base import ExtractionResult, PlatformWorker

log = get_logger(__name__)

TIKTOK_ANALYTICS_URL = "https://www.tiktok.com/tiktokstudio/analytics"
TIKTOK_FOLLOWERS_URL = "https://www.tiktok.com/tiktokstudio/analytics/followers"
STUDIO_SOURCE = "TikTok Studio"

# TikTok Studio overview (2026): each card is "<label>" then its value on the next line
# ("--" when the period has no activity), then the change vs the previous period.
_OVERVIEW_LABELS = {
    "Video views": "video_views",
    "Profile views": "profile_views",
    "Likes": "likes",
    "Comments": "comments",
    "Shares": "shares",
    "Est. rewards": "est_rewards_usd",
}
_FOLLOWER_LABELS = {"Total followers": "total_followers", "Net followers": "net_followers"}
_PERIODS = (7, 28, 60, 365)

_LINES_JS = r"""() => document.body.innerText.split('\n').map(s => s.trim()).filter(Boolean)"""
TIKTOK_CREATOR_URL = "https://www.tiktok.com/creator#/analytics"
TIKTOK_LOGIN_URL = "https://www.tiktok.com/login"


class TikTokWorker(PlatformWorker):
    platform = "tiktok"

    def __init__(self, browser_session: BrowserSession):
        self._browser = browser_session
        self._username: str | None = None

    # ── Authentication ────────────────────────────────────────────

    async def verify_auth(self) -> bool:
        ctx = await self._browser.get_context("tiktok", self._username or "default")
        page = await ctx.new_page()
        try:
            resp = await page.goto(
                TIKTOK_ANALYTICS_URL,
                wait_until="domcontentloaded",
                timeout=settings.browser_timeout,
            )
            challenge = await detect_challenge(page, resp)
            if challenge.detected:
                log.warning("tiktok_auth_challenge", challenge=challenge.challenge_type.value)
                return False

            await page.wait_for_timeout(3000)
            url = page.url

            if "/login" in url or "login" in url:
                log.info("tiktok_not_authenticated", url=url)
                return False

            # If we're on analytics or creator page, we're authenticated
            if "analytics" in url or "creator" in url:
                username = await self._detect_username(page)
                if username:
                    self._username = username
                    log.info("tiktok_authenticated", username=username)
                    return True

            log.warning("tiktok_auth_unknown_state", url=url)
            return False
        except PlaywrightTimeout:
            log.error("tiktok_auth_timeout")
            return False
        finally:
            await page.close()

    async def login(self, account_id: str = "default") -> bool:
        """Open a browser window for the user to log in manually."""
        self._username = account_id
        ctx = await self._browser.get_context("tiktok", account_id)
        page = await ctx.new_page()
        try:
            await page.goto(TIKTOK_LOGIN_URL, wait_until="domcontentloaded", timeout=settings.browser_timeout)
            log.info("tiktok_login_opened", message="Waiting for user to authenticate...")

            # Wait up to 5 minutes for login completion
            try:
                await page.wait_for_url(
                    lambda url: "tiktok.com" in url and "/login" not in url,
                    timeout=300_000,
                )
                # Give page time to settle after redirect
                await page.wait_for_timeout(5000)
            except PlaywrightTimeout:
                log.warning("tiktok_login_timeout")
                return False

            if "/login" in page.url:
                log.warning("tiktok_login_failed")
                return False

            # Signed in once past /login. The username is a nice-to-have for the account
            # name; failing to read it must not undo a good sign-in.
            self._username = await self._detect_username(page) or account_id
            log.info("tiktok_login_success", username=self._username)
            return True
        finally:
            await page.close()

    async def _detect_username(self, page: Page) -> str | None:
        """Extract the TikTok username from the analytics page."""
        try:
            username = await page.evaluate("""() => {
                // Signed-in nav: the "Profile" link points at /@<username>
                const nav = document.querySelector('a[data-e2e="nav-profile"][href*="/@"], a[href^="/@"][data-e2e*="profile"]');
                if (nav) {
                    const m = nav.getAttribute('href').match(/@([\\w.]+)/);
                    if (m) return m[1];
                }

                // Check for username in profile/header area
                const profileEl = document.querySelector(
                    '[class*="username"], [data-e2e="username"], [class*="UniqueId"]'
                );
                if (profileEl) return profileEl.textContent?.trim() || null;

                // Check meta tags
                const meta = document.querySelector('meta[property="og:title"]');
                if (meta && meta.content) return meta.content.split('|')[0]?.trim() || null;

                // Check URL for @username pattern
                const url = window.location.href;
                const match = url.match(/@([\\w.]+)/);
                if (match) return match[1];

                return null;
            }""")
            if username:
                return username.lstrip("@")
        except Exception:
            pass

        return None

    # ── Account Metrics Extraction ────────────────────────────────

    async def extract_account_metrics(
        self, account_id: str, date_start: str, date_end: str
    ) -> ExtractionResult:
        """TikTok Studio Overview (views, profile views, likes, comments, shares, rewards) for
        the preset period nearest the request, plus total and net followers."""
        from datetime import date, datetime, timedelta
        from zoneinfo import ZoneInfo

        result = ExtractionResult(platform="tiktok", account_id=account_id)
        ctx = await self._browser.get_context("tiktok", account_id)
        page = await ctx.new_page()

        try:
            resp = await page.goto(TIKTOK_ANALYTICS_URL, wait_until="domcontentloaded",
                                   timeout=settings.browser_timeout)
            challenge = await detect_challenge(page, resp)
            if challenge.detected:
                result.errors.append(f"Challenge detected: {challenge.challenge_type.value}")
                return result
            try:
                await page.get_by_text("Video views", exact=True).first.wait_for(timeout=25000)
            except PlaywrightTimeout:
                if "/login" in page.url:
                    result.errors.append("Not signed in to TikTok. Click Re-authenticate and log in once.")
                else:
                    result.errors.append(f"TikTok Studio analytics did not load ({page.url})")
                return result

            try:
                span = (date.fromisoformat(date_end) - date.fromisoformat(date_start)).days + 1
            except ValueError:
                span = 7
            days = await self._select_period(page, min(_PERIODS, key=lambda d: abs(d - span)))
            try:  # the rewards card renders after the others; not every account has it
                await page.get_by_text("Est. rewards", exact=True).first.wait_for(timeout=8000)
            except PlaywrightTimeout:
                pass
            await page.wait_for_timeout(1500)

            # Studio does not print the dates; its presets end on the last finished day.
            today = datetime.now(ZoneInfo(settings.app_timezone)).date()
            period_end = today - timedelta(days=1)
            period_start = period_end - timedelta(days=days - 1)
            source = f"{STUDIO_SOURCE} Overview (Last {days} days)"

            lines = await page.evaluate(_LINES_JS)
            for name, value in parse_studio_cards(lines, _OVERVIEW_LABELS).items():
                result.metrics.append(self._metric(account_id, name, value, period_start, period_end, source))

            await page.goto(TIKTOK_FOLLOWERS_URL, wait_until="domcontentloaded", timeout=settings.browser_timeout)
            try:
                await page.get_by_text("Total followers", exact=True).first.wait_for(timeout=20000)
                cards = parse_studio_cards(await page.evaluate(_LINES_JS), _FOLLOWER_LABELS)
                if "total_followers" in cards:  # "All time": a snapshot as of today
                    result.metrics.append(self._metric(account_id, "total_followers", cards["total_followers"],
                                                       today, today, f"{STUDIO_SOURCE} Followers"))
                if "net_followers" in cards:
                    result.metrics.append(self._metric(account_id, "net_followers", cards["net_followers"],
                                                       period_start, period_end,
                                                       f"{STUDIO_SOURCE} Followers (Last {days} days)"))
            except PlaywrightTimeout:
                result.warnings.append("TikTok Studio followers page did not load")

            if not result.metrics:
                result.errors.append("TikTok Studio loaded but no numbers could be read")
                return result
            if "--" in lines:
                result.warnings.append('TikTok shows "--" when a period has no activity; those are stored as 0.')
            result.extraction_method = "dom"
            result.success = True
            log.info("tiktok_studio_extracted", metrics=len(result.metrics), days=days)
            return result

        except PlaywrightTimeout:
            result.errors.append("Timeout navigating to TikTok Studio")
            return result
        except Exception as e:
            result.errors.append(f"Extraction error: {str(e)}")
            log.error("tiktok_extraction_error", error=str(e))
            return result
        finally:
            await page.close()

    async def _select_period(self, page: Page, days: int) -> int:
        """Pick "Last N days" in Studio's period menu. Returns the period actually shown."""
        current = page.get_by_text(re.compile(r"^Last \d+ days$")).first
        try:
            shown = int(re.search(r"\d+", await current.inner_text(timeout=5000)).group())
            if shown == days:
                return days
            await current.click(timeout=5000)
            await page.wait_for_timeout(1200)
            await page.get_by_text(f"Last {days} days", exact=True).last.click(timeout=5000)
            await page.wait_for_timeout(5000)
            return days
        except Exception as e:
            await page.keyboard.press("Escape")
            log.warning("tiktok_period_select_failed", days=days, error=str(e)[:150])
            try:
                return int(re.search(r"\d+", await current.inner_text(timeout=2000)).group())
            except Exception:
                return 7

    @staticmethod
    def _metric(account_id: str, name: str, value: float, start, end, source: str) -> dict[str, Any]:
        return {
            "platform": "tiktok",
            "account_id": account_id,
            "metric_name": name,
            "metric_value": value,
            "date_start": start.isoformat(),
            "date_end": end.isoformat(),
            "source_dashboard": source,
            "extraction_method": "dom",
        }

    async def _extract_overview_dom(
        self, page: Page, account_id: str, date_start: str, date_end: str
    ) -> list[dict[str, Any]]:
        """Extract overview metrics from TikTok Analytics DOM."""
        metrics: list[dict[str, Any]] = []

        # TikTok Analytics overview shows key metric cards
        metric_selectors = [
            {"selector": '[data-e2e="video-views"] .value, [class*="VideoViews"] [class*="value"]', "name": "video_views"},
            {"selector": '[data-e2e="profile-views"] .value, [class*="ProfileViews"] [class*="value"]', "name": "profile_views"},
            {"selector": '[data-e2e="likes"] .value, [class*="Likes"] [class*="value"]', "name": "likes"},
            {"selector": '[data-e2e="comments"] .value, [class*="Comments"] [class*="value"]', "name": "comments"},
            {"selector": '[data-e2e="shares"] .value, [class*="Shares"] [class*="value"]', "name": "shares"},
            {"selector": '[data-e2e="followers"] .value, [class*="Followers"] [class*="value"]', "name": "followers_change"},
        ]

        for sel in metric_selectors:
            try:
                el = page.locator(sel["selector"]).first
                if await el.is_visible(timeout=2000):
                    text = (await el.text_content() or "").strip()
                    value = self._parse_metric_value(text)
                    if value is not None and not any(m["metric_name"] == sel["name"] for m in metrics):
                        metrics.append({
                            "platform": "tiktok",
                            "account_id": account_id,
                            "metric_name": sel["name"],
                            "native_metric_name": sel["name"],
                            "metric_value": value,
                            "date_start": date_start,
                            "date_end": date_end,
                            "source_dashboard": "TikTok Analytics Overview",
                            "extraction_method": "dom",
                        })
            except (PlaywrightTimeout, Exception):
                continue

        # Fallback: generic card extraction
        if not metrics:
            metrics = await self._extract_metric_cards_generic(page, account_id, date_start, date_end)

        return metrics

    async def _extract_metric_cards_generic(
        self, page: Page, account_id: str, date_start: str, date_end: str
    ) -> list[dict[str, Any]]:
        """Generic extraction of metric cards from TikTok Analytics."""
        metrics: list[dict[str, Any]] = []
        try:
            cards = await page.evaluate("""() => {
                const results = [];

                // Look for card-like containers with label + value
                const containers = document.querySelectorAll(
                    '[class*="card"], [class*="metric"], [class*="stat"], [class*="kpi"], [class*="data-item"]'
                );
                for (const el of containers) {
                    const label = el.querySelector(
                        '[class*="label"], [class*="title"], [class*="name"], [class*="desc"]'
                    );
                    const value = el.querySelector(
                        '[class*="value"], [class*="number"], [class*="count"], [class*="num"]'
                    );
                    if (label && value) {
                        const lText = label.textContent?.trim();
                        const vText = value.textContent?.trim();
                        if (lText && vText && lText.length < 50) {
                            results.push({label: lText, value: vText});
                        }
                    }
                }

                // Also scan for standalone stat elements
                const statEls = document.querySelectorAll('[role="status"], [aria-label*="metric"], [aria-label*="stat"]');
                for (const el of statEls) {
                    const ariaLabel = el.getAttribute('aria-label') || '';
                    const text = el.textContent?.trim() || '';
                    if (ariaLabel && text) {
                        results.push({label: ariaLabel, value: text});
                    }
                }

                return results;
            }""")

            seen_names: set[str] = set()
            for card in cards:
                name = self._normalize_metric_name(card.get("label", ""))
                if not name or name in seen_names:
                    continue
                value = self._parse_metric_value(card.get("value", ""))
                if value is not None:
                    seen_names.add(name)
                    metrics.append({
                        "platform": "tiktok",
                        "account_id": account_id,
                        "metric_name": name,
                        "native_metric_name": card.get("label", ""),
                        "metric_value": value,
                        "date_start": date_start,
                        "date_end": date_end,
                        "source_dashboard": "TikTok Analytics Overview",
                        "extraction_method": "dom_generic",
                    })

        except Exception as e:
            log.warning("tiktok_generic_extraction_error", error=str(e))

        return metrics

    # ── Content Metrics Extraction ────────────────────────────────

    async def extract_content_metrics(
        self, account_id: str, date_start: str, date_end: str
    ) -> ExtractionResult:
        result = ExtractionResult(platform="tiktok", account_id=account_id)
        ctx = await self._browser.get_context("tiktok", account_id)
        page = await ctx.new_page()

        try:
            resp = await page.goto(
                TIKTOK_ANALYTICS_URL,
                wait_until="domcontentloaded",
                timeout=settings.browser_timeout,
            )

            challenge = await detect_challenge(page, resp)
            if challenge.detected:
                result.errors.append(f"Challenge: {challenge.challenge_type.value}")
                return result

            await page.wait_for_timeout(3000)

            # Navigate to Content tab
            content_tab = page.locator('[data-e2e="analytics-content-tab"], a:has-text("Content")').first
            try:
                if await content_tab.is_visible(timeout=3000):
                    await content_tab.click()
                    await page.wait_for_timeout(2000)
            except (PlaywrightTimeout, Exception):
                pass

            content_data = await self._extract_content_list(page, account_id, date_start, date_end)
            if content_data:
                result.content_records = content_data
                result.extraction_method = "dom"
                result.success = True
            else:
                result.warnings.append("No content metrics found")

            return result

        except PlaywrightTimeout:
            result.errors.append("Timeout on content analytics")
            return result
        except Exception as e:
            result.errors.append(f"Content extraction error: {str(e)}")
            return result
        finally:
            await page.close()

    async def _extract_content_list(
        self, page: Page, account_id: str, date_start: str, date_end: str
    ) -> list[dict[str, Any]]:
        """Extract video performance list from TikTok Analytics content tab."""
        records: list[dict[str, Any]] = []
        try:
            items = await page.evaluate("""() => {
                const results = [];
                // TikTok content tab lists videos with thumbnails and stats
                const rows = document.querySelectorAll(
                    '[class*="video-item"], [class*="content-item"], [class*="VideoCard"], tr[class*="video"]'
                );
                for (const row of rows) {
                    const titleEl = row.querySelector(
                        '[class*="title"], [class*="desc"], [class*="caption"]'
                    );
                    const statEls = row.querySelectorAll(
                        '[class*="value"], [class*="count"], [class*="number"], td'
                    );
                    const title = titleEl?.textContent?.trim() || '';
                    const values = Array.from(statEls).map(e => e.textContent?.trim() || '');

                    if (title) {
                        results.push({title, values});
                    }
                }
                return results;
            }""")

            for item in items:
                records.append({
                    "platform": "tiktok",
                    "account_id": account_id,
                    "title": item.get("title", ""),
                    "content_type": "video",
                    "date_start": date_start,
                    "date_end": date_end,
                    "source_dashboard": "TikTok Analytics Content",
                    "extraction_method": "dom",
                    "raw_values": item.get("values", []),
                })

        except Exception as e:
            log.warning("tiktok_content_list_error", error=str(e))

        return records

    # ── Audience Metrics ──────────────────────────────────────────

    async def extract_audience_metrics(
        self, account_id: str, date_start: str, date_end: str
    ) -> ExtractionResult:
        result = ExtractionResult(platform="tiktok", account_id=account_id)
        ctx = await self._browser.get_context("tiktok", account_id)
        page = await ctx.new_page()

        try:
            resp = await page.goto(
                TIKTOK_ANALYTICS_URL,
                wait_until="domcontentloaded",
                timeout=settings.browser_timeout,
            )

            challenge = await detect_challenge(page, resp)
            if challenge.detected:
                result.errors.append(f"Challenge: {challenge.challenge_type.value}")
                return result

            await page.wait_for_timeout(3000)

            # Navigate to Followers tab
            followers_tab = page.locator('[data-e2e="analytics-followers-tab"], a:has-text("Followers")').first
            try:
                if await followers_tab.is_visible(timeout=3000):
                    await followers_tab.click()
                    await page.wait_for_timeout(2000)
            except (PlaywrightTimeout, Exception):
                pass

            audience_data = await self._extract_audience_dom(page, account_id, date_start, date_end)
            if audience_data:
                result.audience_data = audience_data
                result.extraction_method = "dom"
                result.success = True

            return result

        except Exception as e:
            result.errors.append(f"Audience extraction error: {str(e)}")
            return result
        finally:
            await page.close()

    async def _extract_audience_dom(
        self, page: Page, account_id: str, date_start: str, date_end: str
    ) -> list[dict[str, Any]]:
        """Extract follower demographics from TikTok Analytics."""
        data: list[dict[str, Any]] = []
        try:
            demo_info = await page.evaluate("""() => {
                const results = [];
                // TikTok shows gender, age, and top territories sections
                const sections = document.querySelectorAll(
                    '[class*="gender"], [class*="age"], [class*="territory"], [class*="location"], [class*="demographic"]'
                );
                for (const section of sections) {
                    const heading = section.querySelector('h3, h4, [class*="heading"], [class*="title"]');
                    const items = section.querySelectorAll('[class*="row"], [class*="item"], [class*="bar"], li');
                    const sectionName = heading?.textContent?.trim() || 'unknown';

                    for (const item of items) {
                        const label = item.querySelector('[class*="label"], [class*="name"], [class*="text"]');
                        const value = item.querySelector('[class*="value"], [class*="percent"], [class*="number"]');
                        if (label && value) {
                            results.push({
                                dimension: sectionName,
                                dimension_value: label.textContent?.trim() || '',
                                metric_value: value.textContent?.trim() || ''
                            });
                        }
                    }
                }
                return results;
            }""")

            for item in demo_info:
                val = self._parse_metric_value(item.get("metric_value", ""))
                if val is not None:
                    data.append({
                        "platform": "tiktok",
                        "account_id": account_id,
                        "metric_name": "audience_distribution",
                        "dimension": item.get("dimension", "unknown"),
                        "dimension_value": item.get("dimension_value", ""),
                        "metric_value": val,
                        "date_start": date_start,
                        "date_end": date_end,
                    })

        except Exception as e:
            log.warning("tiktok_audience_extraction_error", error=str(e))

        return data

    # ── Helpers ────────────────────────────────────────────────────

    @staticmethod
    def _parse_metric_value(text: str) -> float | None:
        """Parse a metric value string into a float, handling K/M/B suffixes."""
        if not text:
            return None
        text = text.strip().replace(",", "").replace(" ", "")

        if text.endswith("%"):
            text = text[:-1]

        multipliers = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}
        for suffix, mult in multipliers.items():
            if text.upper().endswith(suffix):
                try:
                    return float(text[:-1]) * mult
                except ValueError:
                    return None

        negative = False
        if text.startswith("-") or text.startswith("−"):
            negative = True
            text = text[1:]

        try:
            val = float(text)
            return -val if negative else val
        except ValueError:
            return None

    @staticmethod
    def _normalize_metric_name(name: str) -> str:
        """Normalize a metric label to a consistent snake_case name."""
        if not name:
            return ""
        name = name.strip().lower()
        replacements = {
            "video views": "video_views",
            "profile views": "profile_views",
            "followers": "followers_change",
            "follower growth": "followers_change",
            "net followers": "followers_change",
            "likes": "likes",
            "comments": "comments",
            "shares": "shares",
            "total play time": "total_play_time",
            "average watch time": "avg_watch_time",
            "watched full video": "watched_full_video",
            "reached audience": "reached_audience",
            "engaged audience": "engaged_audience",
        }
        if name in replacements:
            return replacements[name]
        name = re.sub(r"[^a-z0-9]+", "_", name)
        return name.strip("_")


def parse_studio_cards(lines: list[str], labels: dict[str, str]) -> dict[str, float]:
    """Read "<label>" followed by its value line. "--" (no activity in the period) is 0;
    "$1.23" rewards drop the currency sign. Unparsable values are skipped."""
    out: dict[str, float] = {}
    for i, line in enumerate(lines[:-1]):
        name = labels.get(" ".join(line.split()))  # split() also folds non-breaking spaces
        if not name or name in out:
            continue
        raw = lines[i + 1].replace("$", "").strip()
        value = 0.0 if raw in ("--", "-") else TikTokWorker._parse_metric_value(raw)
        if value is not None:
            out[name] = value
    return out
