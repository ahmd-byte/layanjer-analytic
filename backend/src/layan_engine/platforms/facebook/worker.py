"""Facebook Page Insights extraction worker.

Extracts analytics from Facebook Page Insights (Meta Business Suite
or the classic facebook.com/page/insights) using Playwright browser
automation with DOM extraction.
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

FB_BASE = "https://www.facebook.com"
FB_LOGIN = f"{FB_BASE}/login"
FB_BUSINESS_SUITE = "https://business.facebook.com"
FB_INSIGHTS_PATTERN = "/insights"


class FacebookWorker(PlatformWorker):
    platform = "facebook"

    def __init__(self, browser_session: BrowserSession):
        self._browser = browser_session
        self._page_id: str | None = None
        self._page_name: str | None = None

    # ── Authentication ────────────────────────────────────────────

    async def verify_auth(self) -> bool:
        ctx = await self._browser.get_context("facebook", self._page_id or "default")
        page = await ctx.new_page()
        try:
            resp = await page.goto(
                FB_BASE,
                wait_until="domcontentloaded",
                timeout=settings.browser_timeout,
            )
            challenge = await detect_challenge(page, resp)
            if challenge.detected:
                log.warning("facebook_auth_challenge", challenge=challenge.challenge_type.value)
                return False

            await page.wait_for_timeout(3000)
            url = page.url

            if "/login" in url or "/checkpoint" in url:
                log.info("facebook_not_authenticated", url=url)
                return False

            # Check if logged in by looking for navigation elements
            is_logged_in = await page.evaluate("""() => {
                return !!(
                    document.querySelector('[aria-label="Your profile"]') ||
                    document.querySelector('[aria-label="Account"]') ||
                    document.querySelector('[data-pagelet="ProfileTail"]') ||
                    document.querySelector('[role="banner"] [role="navigation"]')
                );
            }""")

            if is_logged_in:
                page_info = await self._detect_page_info(page)
                if page_info:
                    self._page_id = page_info.get("id", self._page_id)
                    self._page_name = page_info.get("name")
                log.info("facebook_authenticated", page_id=self._page_id)
                return True

            log.warning("facebook_auth_unknown_state", url=url)
            return False
        except PlaywrightTimeout:
            log.error("facebook_auth_timeout")
            return False
        finally:
            await page.close()

    async def login(self, account_id: str = "default") -> bool:
        """Open a browser window for the user to log in manually."""
        self._page_id = account_id
        ctx = await self._browser.get_context("facebook", account_id)
        page = await ctx.new_page()
        try:
            await page.goto(FB_LOGIN, wait_until="domcontentloaded", timeout=settings.browser_timeout)
            log.info("facebook_login_opened", message="Waiting for user to authenticate...")

            try:
                await page.wait_for_url(
                    "**/facebook.com/**",
                    timeout=300_000,
                )
                await page.wait_for_timeout(5000)
            except PlaywrightTimeout:
                log.warning("facebook_login_timeout")
                return False

            if "/login" in page.url or "/checkpoint" in page.url:
                log.warning("facebook_login_failed")
                return False

            page_info = await self._detect_page_info(page)
            if page_info:
                self._page_id = page_info.get("id", account_id)
                self._page_name = page_info.get("name")

            await self._browser.save_context("facebook", account_id)
            log.info("facebook_login_success", page_id=self._page_id)
            return True
        finally:
            await page.close()

    async def _detect_page_info(self, page: Page) -> dict[str, str] | None:
        """Try to detect managed Facebook Page info."""
        try:
            info = await page.evaluate("""() => {
                // Look for page switcher or page name in sidebar
                const pageLink = document.querySelector(
                    '[data-pagelet="page_switcher"] a, [aria-label="Switch Page"] span, [class*="PageName"]'
                );
                if (pageLink) {
                    return {name: pageLink.textContent?.trim() || '', id: ''};
                }

                // Check URL for page id
                const url = window.location.href;
                const idMatch = url.match(/facebook\\.com\\/(\\d+)|page_id=(\\d+)/);
                if (idMatch) {
                    return {name: '', id: idMatch[1] || idMatch[2]};
                }

                return null;
            }""")
            return info
        except Exception:
            return None

    # ── Account Metrics Extraction ────────────────────────────────

    async def extract_account_metrics(
        self, account_id: str, date_start: str, date_end: str
    ) -> ExtractionResult:
        result = ExtractionResult(platform="facebook", account_id=account_id)
        ctx = await self._browser.get_context("facebook", account_id)
        page = await ctx.new_page()

        try:
            # Try Meta Business Suite insights first
            insights_url = f"{FB_BUSINESS_SUITE}/insights"
            resp = await page.goto(
                insights_url,
                wait_until="domcontentloaded",
                timeout=settings.browser_timeout,
            )

            challenge = await detect_challenge(page, resp)
            if challenge.detected:
                result.errors.append(f"Challenge detected: {challenge.challenge_type.value}")
                return result

            await page.wait_for_timeout(3000)

            if "/login" in page.url:
                result.errors.append("Not authenticated — login required")
                return result

            # Try Overview tab
            overview_tab = page.locator('a:has-text("Overview"), [role="tab"]:has-text("Overview")').first
            try:
                if await overview_tab.is_visible(timeout=3000):
                    await overview_tab.click()
                    await page.wait_for_timeout(2000)
            except (PlaywrightTimeout, Exception):
                pass

            dom_metrics = await self._extract_overview_dom(page, account_id, date_start, date_end)
            if dom_metrics:
                result.metrics = dom_metrics
                result.extraction_method = "dom"
                result.success = True
                log.info("facebook_overview_extracted", metrics=len(dom_metrics))
            else:
                # Fallback: try classic insights URL
                classic_metrics = await self._try_classic_insights(page, account_id, date_start, date_end)
                if classic_metrics:
                    result.metrics = classic_metrics
                    result.extraction_method = "dom_classic"
                    result.success = True
                else:
                    result.warnings.append("No overview metrics could be extracted")

            return result

        except PlaywrightTimeout:
            result.errors.append("Timeout navigating to Facebook Insights")
            return result
        except Exception as e:
            result.errors.append(f"Extraction error: {str(e)}")
            log.error("facebook_extraction_error", error=str(e))
            return result
        finally:
            await page.close()

    async def _try_classic_insights(
        self, page: Page, account_id: str, date_start: str, date_end: str
    ) -> list[dict[str, Any]]:
        """Try extracting from classic Facebook Page Insights."""
        try:
            await page.goto(
                f"{FB_BASE}/{account_id}/insights/",
                wait_until="domcontentloaded",
                timeout=settings.browser_timeout,
            )
            await page.wait_for_timeout(3000)
            return await self._extract_overview_dom(page, account_id, date_start, date_end)
        except Exception as e:
            log.warning("facebook_classic_insights_failed", error=str(e))
            return []

    async def _extract_overview_dom(
        self, page: Page, account_id: str, date_start: str, date_end: str
    ) -> list[dict[str, Any]]:
        """Extract overview metrics from Facebook Insights DOM."""
        metrics: list[dict[str, Any]] = []

        metric_selectors = [
            {"selector": '[aria-label*="Page reach"], [class*="page_reach"] [class*="value"]', "name": "page_reach"},
            {"selector": '[aria-label*="Page visits"], [class*="page_visits"] [class*="value"]', "name": "page_visits"},
            {"selector": '[aria-label*="New followers"], [class*="new_followers"] [class*="value"]', "name": "new_followers"},
            {"selector": '[aria-label*="Post engagement"], [class*="engagement"] [class*="value"]', "name": "post_engagement"},
            {"selector": '[aria-label*="Post reach"], [class*="post_reach"] [class*="value"]', "name": "post_reach"},
            {"selector": '[aria-label*="reactions"], [class*="reactions"] [class*="value"]', "name": "reactions"},
        ]

        for sel in metric_selectors:
            try:
                el = page.locator(sel["selector"]).first
                if await el.is_visible(timeout=2000):
                    text = (await el.text_content() or "").strip()
                    value = self._parse_metric_value(text)
                    if value is not None and not any(m["metric_name"] == sel["name"] for m in metrics):
                        metrics.append({
                            "platform": "facebook",
                            "account_id": account_id,
                            "metric_name": sel["name"],
                            "native_metric_name": sel["name"],
                            "metric_value": value,
                            "date_start": date_start,
                            "date_end": date_end,
                            "source_dashboard": "Facebook Insights Overview",
                            "extraction_method": "dom",
                        })
            except (PlaywrightTimeout, Exception):
                continue

        if not metrics:
            metrics = await self._extract_metric_cards_generic(page, account_id, date_start, date_end)

        return metrics

    async def _extract_metric_cards_generic(
        self, page: Page, account_id: str, date_start: str, date_end: str
    ) -> list[dict[str, Any]]:
        """Generic extraction of metric cards from Facebook Insights."""
        metrics: list[dict[str, Any]] = []
        try:
            cards = await page.evaluate("""() => {
                const results = [];

                const containers = document.querySelectorAll(
                    '[class*="card"], [class*="metric"], [class*="stat"], [class*="kpi"], [class*="insight"], [class*="summary"]'
                );
                for (const el of containers) {
                    const label = el.querySelector(
                        '[class*="label"], [class*="title"], [class*="name"], [class*="heading"], h3, h4'
                    );
                    const value = el.querySelector(
                        '[class*="value"], [class*="number"], [class*="count"], [class*="num"], [class*="big"]'
                    );
                    if (label && value && label !== value) {
                        const lText = label.textContent?.trim();
                        const vText = value.textContent?.trim();
                        if (lText && vText && lText.length < 60 && lText !== vText) {
                            results.push({label: lText, value: vText});
                        }
                    }
                }

                // Meta Business Suite uses specific section patterns
                const sections = document.querySelectorAll('[role="region"], section');
                for (const section of sections) {
                    const heading = section.querySelector('h2, h3');
                    const bigNum = section.querySelector('[class*="value"], [class*="number"]');
                    if (heading && bigNum) {
                        const hText = heading.textContent?.trim();
                        const nText = bigNum.textContent?.trim();
                        if (hText && nText && hText.length < 60 && hText !== nText) {
                            results.push({label: hText, value: nText});
                        }
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
                        "platform": "facebook",
                        "account_id": account_id,
                        "metric_name": name,
                        "native_metric_name": card.get("label", ""),
                        "metric_value": value,
                        "date_start": date_start,
                        "date_end": date_end,
                        "source_dashboard": "Facebook Insights",
                        "extraction_method": "dom_generic",
                    })

        except Exception as e:
            log.warning("facebook_generic_extraction_error", error=str(e))

        return metrics

    # ── Content Metrics Extraction ────────────────────────────────

    async def extract_content_metrics(
        self, account_id: str, date_start: str, date_end: str
    ) -> ExtractionResult:
        result = ExtractionResult(platform="facebook", account_id=account_id)
        ctx = await self._browser.get_context("facebook", account_id)
        page = await ctx.new_page()

        try:
            resp = await page.goto(
                f"{FB_BUSINESS_SUITE}/insights/content",
                wait_until="domcontentloaded",
                timeout=settings.browser_timeout,
            )

            challenge = await detect_challenge(page, resp)
            if challenge.detected:
                result.errors.append(f"Challenge: {challenge.challenge_type.value}")
                return result

            await page.wait_for_timeout(3000)

            content_data = await self._extract_content_list(page, account_id, date_start, date_end)
            if content_data:
                result.content_records = content_data
                result.extraction_method = "dom"
                result.success = True
            else:
                result.warnings.append("No content metrics found")

            return result

        except PlaywrightTimeout:
            result.errors.append("Timeout on content insights")
            return result
        except Exception as e:
            result.errors.append(f"Content extraction error: {str(e)}")
            return result
        finally:
            await page.close()

    async def _extract_content_list(
        self, page: Page, account_id: str, date_start: str, date_end: str
    ) -> list[dict[str, Any]]:
        """Extract content performance from Facebook Insights."""
        records: list[dict[str, Any]] = []
        try:
            items = await page.evaluate("""() => {
                const results = [];
                const rows = document.querySelectorAll(
                    '[class*="post-item"], [class*="content-item"], [class*="PostRow"], tr[class*="post"], [role="row"]'
                );
                for (const row of rows) {
                    const titleEl = row.querySelector(
                        '[class*="title"], [class*="text"], [class*="caption"], [class*="preview"]'
                    );
                    const statEls = row.querySelectorAll(
                        '[class*="value"], [class*="count"], [class*="number"], td'
                    );
                    const title = titleEl?.textContent?.trim() || '';
                    const values = Array.from(statEls).map(e => e.textContent?.trim() || '');

                    if (title || values.length > 0) {
                        results.push({title: title.slice(0, 200), values});
                    }
                }
                return results;
            }""")

            for item in items:
                content_type = "post"
                title = item.get("title", "")
                lower_title = title.lower()
                if "reel" in lower_title:
                    content_type = "reel"
                elif "story" in lower_title or "stories" in lower_title:
                    content_type = "story"
                elif "video" in lower_title or "live" in lower_title:
                    content_type = "video"

                records.append({
                    "platform": "facebook",
                    "account_id": account_id,
                    "title": title,
                    "content_type": content_type,
                    "date_start": date_start,
                    "date_end": date_end,
                    "source_dashboard": "Facebook Insights Content",
                    "extraction_method": "dom",
                    "raw_values": item.get("values", []),
                })

        except Exception as e:
            log.warning("facebook_content_list_error", error=str(e))

        return records

    # ── Audience Metrics ──────────────────────────────────────────

    async def extract_audience_metrics(
        self, account_id: str, date_start: str, date_end: str
    ) -> ExtractionResult:
        result = ExtractionResult(platform="facebook", account_id=account_id)
        ctx = await self._browser.get_context("facebook", account_id)
        page = await ctx.new_page()

        try:
            resp = await page.goto(
                f"{FB_BUSINESS_SUITE}/insights/audience",
                wait_until="domcontentloaded",
                timeout=settings.browser_timeout,
            )

            challenge = await detect_challenge(page, resp)
            if challenge.detected:
                result.errors.append(f"Challenge: {challenge.challenge_type.value}")
                return result

            await page.wait_for_timeout(3000)

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
        """Extract audience demographics from Facebook Insights."""
        data: list[dict[str, Any]] = []
        try:
            demo_info = await page.evaluate("""() => {
                const results = [];
                const sections = document.querySelectorAll(
                    '[class*="gender"], [class*="age"], [class*="location"], [class*="city"], [class*="country"], [class*="demographic"], [class*="audience"]'
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
                        "platform": "facebook",
                        "account_id": account_id,
                        "metric_name": "audience_distribution",
                        "dimension": item.get("dimension", "unknown"),
                        "dimension_value": item.get("dimension_value", ""),
                        "metric_value": val,
                        "date_start": date_start,
                        "date_end": date_end,
                    })

        except Exception as e:
            log.warning("facebook_audience_extraction_error", error=str(e))

        return data

    # ── Helpers ────────────────────────────────────────────────────

    @staticmethod
    def _parse_metric_value(text: str) -> float | None:
        """Parse a metric value string into a float, handling K/M/B suffixes."""
        if not text:
            return None
        text = text.strip().replace(",", "").replace(" ", "").replace(" ", "")

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

        if text.startswith("+"):
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
            "page reach": "page_reach",
            "reach": "page_reach",
            "page visits": "page_visits",
            "new followers": "new_followers",
            "new page likes": "new_page_likes",
            "page likes": "total_page_likes",
            "post engagement": "post_engagement",
            "post reach": "post_reach",
            "reactions": "reactions",
            "comments": "comments",
            "shares": "shares",
            "link clicks": "link_clicks",
            "video views": "video_views",
            "reel plays": "reel_plays",
            "content reach": "content_reach",
            "content engagement": "content_engagement",
            "followers": "total_followers",
            "net followers": "net_followers",
        }
        if name in replacements:
            return replacements[name]
        name = re.sub(r"[^a-z0-9]+", "_", name)
        return name.strip("_")
