"""Instagram Insights extraction worker.

Extracts analytics from Instagram Professional Dashboard
(instagram.com/accounts/professional_dashboard and the Insights
pages) using Playwright browser automation with DOM extraction.
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

IG_BASE = "https://www.instagram.com"
IG_LOGIN = f"{IG_BASE}/accounts/login/"
IG_INSIGHTS = f"{IG_BASE}/accounts/insights/"
IG_PROFESSIONAL = f"{IG_BASE}/accounts/professional_dashboard/"


class InstagramWorker(PlatformWorker):
    platform = "instagram"

    def __init__(self, browser_session: BrowserSession):
        self._browser = browser_session
        self._username: str | None = None

    # ── Authentication ────────────────────────────────────────────

    async def verify_auth(self) -> bool:
        ctx = await self._browser.get_context("instagram", self._username or "default")
        page = await ctx.new_page()
        try:
            resp = await page.goto(
                IG_INSIGHTS,
                wait_until="domcontentloaded",
                timeout=settings.browser_timeout,
            )
            challenge = await detect_challenge(page, resp)
            if challenge.detected:
                log.warning("instagram_auth_challenge", challenge=challenge.challenge_type.value)
                return False

            await page.wait_for_timeout(3000)
            url = page.url

            if "/accounts/login" in url or "/challenge" in url:
                log.info("instagram_not_authenticated", url=url)
                return False

            if "insights" in url or "professional_dashboard" in url:
                username = await self._detect_username(page)
                if username:
                    self._username = username
                    log.info("instagram_authenticated", username=username)
                    return True

            log.warning("instagram_auth_unknown_state", url=url)
            return False
        except PlaywrightTimeout:
            log.error("instagram_auth_timeout")
            return False
        finally:
            await page.close()

    async def login(self, account_id: str = "default") -> bool:
        """Open a browser window for the user to log in manually."""
        self._username = account_id
        ctx = await self._browser.get_context("instagram", account_id)
        page = await ctx.new_page()
        try:
            await page.goto(IG_LOGIN, wait_until="domcontentloaded", timeout=settings.browser_timeout)
            log.info("instagram_login_opened", message="Waiting for user to authenticate...")

            try:
                await page.wait_for_url(
                    "**/instagram.com/**",
                    timeout=300_000,
                )
                await page.wait_for_timeout(5000)
            except PlaywrightTimeout:
                log.warning("instagram_login_timeout")
                return False

            # Navigate to insights to confirm professional account
            await page.goto(IG_INSIGHTS, wait_until="domcontentloaded", timeout=settings.browser_timeout)
            await page.wait_for_timeout(3000)

            if "/accounts/login" in page.url:
                log.warning("instagram_login_failed")
                return False

            username = await self._detect_username(page)
            if username:
                self._username = username
                await self._browser.save_context("instagram", account_id)
                log.info("instagram_login_success", username=username)
                return True

            log.warning("instagram_login_failed_no_username")
            return False
        finally:
            await page.close()

    async def _detect_username(self, page: Page) -> str | None:
        """Extract the Instagram username from the page."""
        try:
            username = await page.evaluate("""() => {
                // Profile link in navigation
                const profileLink = document.querySelector(
                    'a[href*="/"][role="link"] span[dir="auto"]'
                );
                if (profileLink) {
                    const text = profileLink.textContent?.trim();
                    if (text && !text.includes(' ') && text.length < 40) return text;
                }

                // Meta tag
                const meta = document.querySelector('meta[property="og:title"]');
                if (meta && meta.content) {
                    const match = meta.content.match(/@?(\\w[\\w.]{0,29})/);
                    if (match) return match[1];
                }

                // URL pattern /@username or /username/
                const url = window.location.href;
                const urlMatch = url.match(/instagram\\.com\\/([\\w.]+)\\//);
                if (urlMatch && !['accounts', 'explore', 'p', 'reel', 'stories'].includes(urlMatch[1])) {
                    return urlMatch[1];
                }

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
        result = ExtractionResult(platform="instagram", account_id=account_id)
        ctx = await self._browser.get_context("instagram", account_id)
        page = await ctx.new_page()

        try:
            resp = await page.goto(
                IG_INSIGHTS,
                wait_until="domcontentloaded",
                timeout=settings.browser_timeout,
            )

            challenge = await detect_challenge(page, resp)
            if challenge.detected:
                result.errors.append(f"Challenge detected: {challenge.challenge_type.value}")
                return result

            await page.wait_for_timeout(3000)

            if "/accounts/login" in page.url:
                result.errors.append("Not authenticated — login required")
                return result

            # Try Overview section first
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
                log.info("instagram_overview_extracted", metrics=len(dom_metrics))
            else:
                result.warnings.append("No overview metrics could be extracted")

            return result

        except PlaywrightTimeout:
            result.errors.append("Timeout navigating to Instagram Insights")
            return result
        except Exception as e:
            result.errors.append(f"Extraction error: {str(e)}")
            log.error("instagram_extraction_error", error=str(e))
            return result
        finally:
            await page.close()

    async def _extract_overview_dom(
        self, page: Page, account_id: str, date_start: str, date_end: str
    ) -> list[dict[str, Any]]:
        """Extract overview metrics from Instagram Insights DOM."""
        metrics: list[dict[str, Any]] = []

        # Instagram Insights uses specific patterns for metric cards
        metric_selectors = [
            {"selector": '[class*="accounts_reached"] [class*="value"], [aria-label*="Accounts reached"]', "name": "accounts_reached"},
            {"selector": '[class*="accounts_engaged"] [class*="value"], [aria-label*="Accounts engaged"]', "name": "accounts_engaged"},
            {"selector": '[class*="total_followers"] [class*="value"], [aria-label*="Total followers"]', "name": "total_followers"},
            {"selector": '[class*="content_interactions"] [class*="value"], [aria-label*="Content interactions"]', "name": "content_interactions"},
            {"selector": '[class*="profile_visits"] [class*="value"], [aria-label*="Profile visits"]', "name": "profile_visits"},
            {"selector": '[class*="website_clicks"] [class*="value"], [aria-label*="Website clicks"]', "name": "website_clicks"},
        ]

        for sel in metric_selectors:
            try:
                el = page.locator(sel["selector"]).first
                if await el.is_visible(timeout=2000):
                    text = (await el.text_content() or "").strip()
                    value = self._parse_metric_value(text)
                    if value is not None and not any(m["metric_name"] == sel["name"] for m in metrics):
                        metrics.append({
                            "platform": "instagram",
                            "account_id": account_id,
                            "metric_name": sel["name"],
                            "native_metric_name": sel["name"],
                            "metric_value": value,
                            "date_start": date_start,
                            "date_end": date_end,
                            "source_dashboard": "Instagram Insights Overview",
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
        """Generic extraction of metric cards from Instagram Insights."""
        metrics: list[dict[str, Any]] = []
        try:
            cards = await page.evaluate("""() => {
                const results = [];

                // Instagram uses div-based cards with label + value pairs
                const containers = document.querySelectorAll(
                    '[class*="card"], [class*="metric"], [class*="stat"], [class*="kpi"], [class*="insight"]'
                );
                for (const el of containers) {
                    const label = el.querySelector(
                        '[class*="label"], [class*="title"], [class*="name"], [class*="heading"], span[dir="auto"]'
                    );
                    const value = el.querySelector(
                        '[class*="value"], [class*="number"], [class*="count"], [class*="num"]'
                    );
                    if (label && value && label !== value) {
                        const lText = label.textContent?.trim();
                        const vText = value.textContent?.trim();
                        if (lText && vText && lText.length < 50 && lText !== vText) {
                            results.push({label: lText, value: vText});
                        }
                    }
                }

                // Also look for sections with heading + large number
                const sections = document.querySelectorAll('section, [role="region"]');
                for (const section of sections) {
                    const heading = section.querySelector('h2, h3, h4');
                    const bigNum = section.querySelector('[class*="value"], [class*="number"]');
                    if (heading && bigNum) {
                        const hText = heading.textContent?.trim();
                        const nText = bigNum.textContent?.trim();
                        if (hText && nText && hText.length < 50 && hText !== nText) {
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
                        "platform": "instagram",
                        "account_id": account_id,
                        "metric_name": name,
                        "native_metric_name": card.get("label", ""),
                        "metric_value": value,
                        "date_start": date_start,
                        "date_end": date_end,
                        "source_dashboard": "Instagram Insights Overview",
                        "extraction_method": "dom_generic",
                    })

        except Exception as e:
            log.warning("instagram_generic_extraction_error", error=str(e))

        return metrics

    # ── Content Metrics Extraction ────────────────────────────────

    async def extract_content_metrics(
        self, account_id: str, date_start: str, date_end: str
    ) -> ExtractionResult:
        result = ExtractionResult(platform="instagram", account_id=account_id)
        ctx = await self._browser.get_context("instagram", account_id)
        page = await ctx.new_page()

        try:
            resp = await page.goto(
                IG_INSIGHTS,
                wait_until="domcontentloaded",
                timeout=settings.browser_timeout,
            )

            challenge = await detect_challenge(page, resp)
            if challenge.detected:
                result.errors.append(f"Challenge: {challenge.challenge_type.value}")
                return result

            await page.wait_for_timeout(3000)

            # Navigate to Content section
            content_tab = page.locator(
                'a:has-text("Content you shared"), [role="tab"]:has-text("Content"), a:has-text("Content")'
            ).first
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
        """Extract content performance from Instagram Insights."""
        records: list[dict[str, Any]] = []
        try:
            items = await page.evaluate("""() => {
                const results = [];
                // Instagram content insights shows posts/reels with thumbnails + stats
                const rows = document.querySelectorAll(
                    '[class*="post-item"], [class*="content-item"], [class*="media-item"], article'
                );
                for (const row of rows) {
                    const captionEl = row.querySelector(
                        '[class*="caption"], [class*="title"], [class*="text"], img[alt]'
                    );
                    const statEls = row.querySelectorAll(
                        '[class*="value"], [class*="count"], [class*="number"], span[dir="auto"]'
                    );
                    let title = '';
                    if (captionEl?.tagName === 'IMG') {
                        title = captionEl.alt || '';
                    } else {
                        title = captionEl?.textContent?.trim() || '';
                    }
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
                if "reel" in title.lower():
                    content_type = "reel"
                elif "story" in title.lower():
                    content_type = "story"

                records.append({
                    "platform": "instagram",
                    "account_id": account_id,
                    "title": title,
                    "content_type": content_type,
                    "date_start": date_start,
                    "date_end": date_end,
                    "source_dashboard": "Instagram Insights Content",
                    "extraction_method": "dom",
                    "raw_values": item.get("values", []),
                })

        except Exception as e:
            log.warning("instagram_content_list_error", error=str(e))

        return records

    # ── Audience Metrics ──────────────────────────────────────────

    async def extract_audience_metrics(
        self, account_id: str, date_start: str, date_end: str
    ) -> ExtractionResult:
        result = ExtractionResult(platform="instagram", account_id=account_id)
        ctx = await self._browser.get_context("instagram", account_id)
        page = await ctx.new_page()

        try:
            resp = await page.goto(
                IG_INSIGHTS,
                wait_until="domcontentloaded",
                timeout=settings.browser_timeout,
            )

            challenge = await detect_challenge(page, resp)
            if challenge.detected:
                result.errors.append(f"Challenge: {challenge.challenge_type.value}")
                return result

            await page.wait_for_timeout(3000)

            # Navigate to Audience / Followers section
            audience_tab = page.locator(
                'a:has-text("Your audience"), a:has-text("Followers"), [role="tab"]:has-text("Audience")'
            ).first
            try:
                if await audience_tab.is_visible(timeout=3000):
                    await audience_tab.click()
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
        """Extract audience demographics from Instagram Insights."""
        data: list[dict[str, Any]] = []
        try:
            demo_info = await page.evaluate("""() => {
                const results = [];
                // Instagram shows age ranges, gender split, and top locations
                const sections = document.querySelectorAll(
                    '[class*="gender"], [class*="age"], [class*="location"], [class*="city"], [class*="country"], [class*="demographic"]'
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
                        "platform": "instagram",
                        "account_id": account_id,
                        "metric_name": "audience_distribution",
                        "dimension": item.get("dimension", "unknown"),
                        "dimension_value": item.get("dimension_value", ""),
                        "metric_value": val,
                        "date_start": date_start,
                        "date_end": date_end,
                    })

        except Exception as e:
            log.warning("instagram_audience_extraction_error", error=str(e))

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

        # Handle plus sign for positive changes
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
            "accounts reached": "accounts_reached",
            "accounts engaged": "accounts_engaged",
            "total followers": "total_followers",
            "followers": "total_followers",
            "follower growth": "followers_change",
            "content interactions": "content_interactions",
            "profile visits": "profile_visits",
            "profile activity": "profile_activity",
            "website clicks": "website_clicks",
            "external link taps": "external_link_taps",
            "impressions": "impressions",
            "reach": "accounts_reached",
            "engagement": "engagement",
            "saves": "saves",
            "shares": "shares",
            "likes": "likes",
            "comments": "comments",
            "plays": "plays",
            "reels plays": "reels_plays",
            "reels interactions": "reels_interactions",
        }
        if name in replacements:
            return replacements[name]
        name = re.sub(r"[^a-z0-9]+", "_", name)
        return name.strip("_")
