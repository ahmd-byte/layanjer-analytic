"""YouTube Studio extraction worker.

Extracts analytics from YouTube Studio (studio.youtube.com) using
Playwright browser automation. Prioritizes native CSV export, then
falls back to DOM extraction for metrics not available in exports.
"""
from __future__ import annotations

import csv
import io
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from playwright.async_api import BrowserContext, Page, TimeoutError as PlaywrightTimeout

from layan_engine.browser.challenge import detect_challenge
from layan_engine.browser.session import BrowserSession
from layan_engine.config import settings
from layan_engine.logging import get_logger
from layan_engine.platforms.base import ExtractionResult, PlatformWorker

log = get_logger(__name__)

STUDIO_URL = "https://studio.youtube.com"
STUDIO_ANALYTICS_URL = "https://studio.youtube.com/channel/{channel_id}/analytics"
ANALYTICS_TAB_OVERVIEW = "tab-overview"
ANALYTICS_TAB_CONTENT = "tab-content"
ANALYTICS_TAB_AUDIENCE = "tab-audience"

_PERIOD_CHIPS = {7: "7 days", 28: "28 days", 90: "90 days"}

# Studio (2026) renders each KPI value alone in a ytcp-simple-metric-view-model; its label
# is the nearest non-numeric, non-date text line in an ancestor (before it, or after it on chart cards).
_STUDIO_METRICS_JS = r"""() => {
  const DATE = /^[A-Z][a-z]{2} \d{1,2}, \d{4}$/;
  const isNoise = s => !s || /^[\d.,%+\-−KMB\s]+$/i.test(s) || DATE.test(s);
  const metrics = [];
  for (const el of document.querySelectorAll('ytcp-simple-metric-view-model')) {
    const value = el.innerText.trim();
    let n = el.parentElement, label = null;
    for (let d = 0; n && d < 20 && !label; d++, n = n.parentElement) {
      const lines = n.innerText.split('\n').map(s => s.trim()).filter(Boolean);
      const i = lines.indexOf(value);
      if (i < 0) continue;
      for (let j = i - 1; j >= 0 && !label; j--) if (!isNoise(lines[j])) label = lines[j];
      for (let j = i + 1; j < lines.length && !label; j++) if (!isNoise(lines[j])) label = lines[j];
    }
    metrics.push({label, value});
  }
  const dates = document.body.innerText.split('\n').map(s => s.trim()).filter(s => DATE.test(s)).slice(0, 2);
  return {metrics, dates};
}"""


class YouTubeWorker(PlatformWorker):
    platform = "youtube"

    def __init__(self, browser_session: BrowserSession):
        self._browser = browser_session
        self._channel_id: str | None = None

    # ── Authentication ────────────────────────────────────────────

    async def verify_auth(self) -> bool:
        ctx = await self._browser.get_context("youtube", self._channel_id or "default")
        page = await ctx.new_page()
        try:
            resp = await page.goto(STUDIO_URL, wait_until="domcontentloaded", timeout=settings.browser_timeout)
            challenge = await detect_challenge(page, resp)
            if challenge.detected:
                log.warning("youtube_auth_challenge", challenge=challenge.challenge_type.value)
                return False

            await page.wait_for_timeout(2000)
            url = page.url

            if "accounts.google.com" in url:
                log.info("youtube_not_authenticated", url=url)
                return False

            if "studio.youtube.com" in url:
                channel_id = await self._detect_channel_id(page)
                if channel_id:
                    self._channel_id = channel_id
                    log.info("youtube_authenticated", channel_id=channel_id)
                    return True

            log.warning("youtube_auth_unknown_state", url=url)
            return False
        except PlaywrightTimeout:
            log.error("youtube_auth_timeout")
            return False
        finally:
            await page.close()

    async def login(self, account_id: str = "default") -> bool:
        """Open a browser window for the user to log in manually."""
        self._channel_id = account_id
        ctx = await self._browser.get_context("youtube", account_id)
        page = await ctx.new_page()
        try:
            await page.goto(STUDIO_URL, wait_until="domcontentloaded", timeout=settings.browser_timeout)
            log.info("youtube_login_opened", message="Waiting for user to authenticate...")

            # Wait up to 5 minutes for the user to complete login
            try:
                await page.wait_for_url(
                    "**/studio.youtube.com/**",
                    timeout=300_000,
                )
            except PlaywrightTimeout:
                log.warning("youtube_login_timeout")
                return False

            await page.wait_for_timeout(3000)
            channel_id = await self._detect_channel_id(page)

            if channel_id:
                self._channel_id = channel_id
                await self._browser.save_context("youtube", account_id)
                log.info("youtube_login_success", channel_id=channel_id)
                return True

            log.warning("youtube_login_failed_no_channel")
            return False
        finally:
            await page.close()

    async def _resolve_channel_id(self, page: Page, account_id: str) -> str:
        """account_id is the saved-profile key (e.g. "default"); Studio URLs need the UC… channel ID."""
        if account_id.startswith("UC"):
            return account_id
        await page.goto(STUDIO_URL, wait_until="domcontentloaded", timeout=settings.browser_timeout)
        await page.wait_for_timeout(3000)
        return await self._detect_channel_id(page) or account_id

    async def _detect_channel_id(self, page: Page) -> str | None:
        """Extract the channel ID from YouTube Studio page URL or DOM."""
        url = page.url
        # URL pattern: studio.youtube.com/channel/UCxxxxxx
        if "/channel/" in url:
            parts = url.split("/channel/")
            if len(parts) > 1:
                cid = parts[1].split("/")[0].split("?")[0]
                if cid.startswith("UC"):
                    return cid

        # Try extracting from page script data
        try:
            cid = await page.evaluate("""() => {
                // ytInitialData or yt config
                const meta = document.querySelector('meta[name="channel_id"]');
                if (meta) return meta.content;

                // Check URL in canonical link
                const canon = document.querySelector('link[rel="canonical"]');
                if (canon && canon.href && canon.href.includes('/channel/')) {
                    return canon.href.split('/channel/')[1].split('/')[0];
                }

                // Check ytcfg
                if (typeof ytcfg !== 'undefined' && ytcfg.get) {
                    const id = ytcfg.get('CHANNEL_ID');
                    if (id) return id;
                }
                return null;
            }""")
            if cid and cid.startswith("UC"):
                return cid
        except Exception:
            pass

        return None

    # ── Account Metrics Extraction ────────────────────────────────

    async def extract_account_metrics(
        self, account_id: str, date_start: str, date_end: str
    ) -> ExtractionResult:
        result = ExtractionResult(platform="youtube", account_id=account_id)
        ctx = await self._browser.get_context("youtube", account_id)
        page = await ctx.new_page()

        try:
            # Navigate to analytics overview
            channel_id = await self._resolve_channel_id(page, account_id)
            analytics_url = f"{STUDIO_URL}/channel/{channel_id}/analytics/tab-overview"
            resp = await page.goto(analytics_url, wait_until="domcontentloaded", timeout=settings.browser_timeout)

            challenge = await detect_challenge(page, resp)
            if challenge.detected:
                result.errors.append(f"Challenge detected: {challenge.challenge_type.value}")
                return result
            if "accounts.google.com" in page.url:
                result.errors.append("YouTube session expired — click Connect Account to sign in again")
                return result

            try:
                await page.wait_for_selector("ytcp-simple-metric-view-model", timeout=25000)
            except PlaywrightTimeout:
                log.warning("youtube_metric_cards_not_rendered", url=page.url)
            await page.wait_for_timeout(1500)
            await self._select_period(page, date_start, date_end)

            # Try native CSV export first
            export_result = await self._try_export_analytics(page, account_id, date_start, date_end)
            if export_result and export_result.get("metrics"):
                result.metrics = export_result["metrics"]
                result.extraction_method = "native_export"
                result.success = True
                log.info("youtube_export_success", metrics=len(result.metrics))
                return result

            # Fall back to DOM extraction
            dom_metrics = await self._extract_overview_dom(page, account_id, date_start, date_end)
            if dom_metrics:
                result.metrics = dom_metrics
                result.extraction_method = "dom"
                result.success = True
                log.info("youtube_dom_extraction", metrics=len(result.metrics))
            else:
                result.warnings.append("No metrics could be extracted from overview")

            return result

        except PlaywrightTimeout:
            result.errors.append("Timeout navigating to YouTube Studio analytics")
            return result
        except Exception as e:
            result.errors.append(f"Extraction error: {str(e)}")
            log.error("youtube_extraction_error", error=str(e))
            return result
        finally:
            await page.close()

    async def _try_export_analytics(
        self, page: Page, account_id: str, date_start: str, date_end: str
    ) -> dict[str, Any] | None:
        """Attempt to download the native analytics CSV export from YouTube Studio."""
        try:
            # Look for the export/download button in the analytics page
            # YouTube Studio uses "SEE MORE" or export icon
            export_btn = page.locator('[aria-label="Export current view"]').first
            if not await export_btn.is_visible(timeout=5000):
                # Try alternative selectors
                export_btn = page.locator('ytcp-button:has-text("Export")').first
                if not await export_btn.is_visible(timeout=3000):
                    log.info("youtube_export_button_not_found")
                    return None

            # Set up download handler
            download_dir = Path(settings.app_data_dir) / "downloads" / "youtube"
            download_dir.mkdir(parents=True, exist_ok=True)

            async with page.expect_download(timeout=30000) as download_info:
                await export_btn.click()
                # May need to confirm format selection
                csv_option = page.locator('text="Comma-separated values (.csv)"')
                if await csv_option.is_visible(timeout=3000):
                    await csv_option.click()

            download = await download_info.value
            filename = f"yt_analytics_{account_id}_{date_start}_{date_end}.csv"
            filepath = download_dir / filename
            await download.save_as(str(filepath))

            log.info("youtube_csv_downloaded", path=str(filepath))
            return self._parse_analytics_csv(filepath, account_id, date_start, date_end)

        except PlaywrightTimeout:
            log.info("youtube_export_timeout")
            return None
        except Exception as e:
            log.warning("youtube_export_failed", error=str(e))
            return None

    def _parse_analytics_csv(
        self, filepath: Path, account_id: str, date_start: str, date_end: str
    ) -> dict[str, Any] | None:
        """Parse a YouTube Studio analytics CSV export into structured metrics."""
        try:
            content = filepath.read_text(encoding="utf-8-sig")
            reader = csv.DictReader(io.StringIO(content))
            metrics = []

            for row in reader:
                date = row.get("Date", "")
                for col_name, value in row.items():
                    if col_name == "Date":
                        continue
                    parsed = self._parse_metric_value(value)
                    if parsed is not None:
                        metrics.append({
                            "platform": "youtube",
                            "account_id": account_id,
                            "metric_name": self._normalize_metric_name(col_name),
                            "native_metric_name": col_name,
                            "metric_value": parsed,
                            "date_start": date or date_start,
                            "date_end": date or date_end,
                            "source_dashboard": "YouTube Studio Export",
                            "extraction_method": "native_export",
                        })

            return {"metrics": metrics} if metrics else None

        except Exception as e:
            log.error("youtube_csv_parse_error", error=str(e), path=str(filepath))
            return None

    async def _extract_overview_dom(
        self, page: Page, account_id: str, date_start: str, date_end: str
    ) -> list[dict[str, Any]]:
        """Extract overview metrics from YouTube Studio DOM."""
        metrics = await self._extract_studio_metric_models(page, account_id, date_start, date_end)
        if metrics:
            return metrics

        # YouTube Studio analytics cards show key metrics as large numbers
        # They use specific element patterns
        metric_selectors = [
            # Main metric cards on overview tab
            {"selector": "#overview-metric-views .metric-value", "name": "views"},
            {"selector": "#overview-metric-watchtime .metric-value", "name": "watch_time_hours"},
            {"selector": "#overview-metric-subscribers .metric-value", "name": "subscribers_change"},
            # Alternative selectors for different YouTube Studio versions
            {"selector": 'yta-metric-card[metric-id="VIEWS"] .metric-value', "name": "views"},
            {"selector": 'yta-metric-card[metric-id="WATCH_TIME"] .metric-value', "name": "watch_time_hours"},
            {"selector": 'yta-metric-card[metric-id="SUBSCRIBERS_NET_CHANGE"] .metric-value', "name": "subscribers_change"},
        ]

        for sel in metric_selectors:
            try:
                el = page.locator(sel["selector"]).first
                if await el.is_visible(timeout=2000):
                    text = (await el.text_content() or "").strip()
                    value = self._parse_metric_value(text)
                    if value is not None:
                        # Avoid duplicates from alternative selectors
                        if not any(m["metric_name"] == sel["name"] for m in metrics):
                            metrics.append({
                                "platform": "youtube",
                                "account_id": account_id,
                                "metric_name": sel["name"],
                                "native_metric_name": sel["name"],
                                "metric_value": value,
                                "date_start": date_start,
                                "date_end": date_end,
                                "source_dashboard": "YouTube Studio Overview",
                                "extraction_method": "dom",
                            })
            except (PlaywrightTimeout, Exception):
                continue

        # Try a broader approach: find all visible metric cards
        if not metrics:
            metrics = await self._extract_metric_cards_generic(page, account_id, date_start, date_end)

        return metrics

    async def _select_period(self, page: Page, date_start: str, date_end: str) -> None:
        """Click the Studio period chip (7/28/90 days) closest to the requested range."""
        try:
            span = (datetime.fromisoformat(date_end) - datetime.fromisoformat(date_start)).days + 1
        except ValueError:
            return
        days = min(_PERIOD_CHIPS, key=lambda d: abs(d - span))
        try:
            await page.get_by_text(_PERIOD_CHIPS[days], exact=True).first.click(timeout=8000)
            await page.wait_for_timeout(4000)
        except Exception as e:
            log.warning("youtube_period_select_failed", days=days, error=str(e).splitlines()[0][:200])

    async def _extract_studio_metric_models(
        self, page: Page, account_id: str, date_start: str, date_end: str
    ) -> list[dict[str, Any]]:
        """Read Studio's ytcp-simple-metric-view-model cards, stamped with the range the page shows."""
        try:
            found = await page.evaluate(_STUDIO_METRICS_JS)
        except Exception:
            return []

        shown = found.get("dates") or []
        if len(shown) == 2:
            try:
                date_start, date_end = (datetime.strptime(d, "%b %d, %Y").date().isoformat() for d in shown)
            except ValueError:
                pass

        metrics: list[dict[str, Any]] = []
        for card in found.get("metrics", []):
            name = self._normalize_metric_name(card.get("label") or "")
            value = self._parse_metric_value(card.get("value") or "")
            if not name or value is None or any(m["metric_name"] == name for m in metrics):
                continue
            metrics.append({
                "platform": "youtube",
                "account_id": account_id,
                "metric_name": name,
                "native_metric_name": card["label"],
                "metric_value": value,
                "date_start": date_start,
                "date_end": date_end,
                "source_dashboard": "YouTube Studio Overview",
                "extraction_method": "dom",
            })
        return metrics

    async def _extract_metric_cards_generic(
        self, page: Page, account_id: str, date_start: str, date_end: str
    ) -> list[dict[str, Any]]:
        """Generic extraction of metric cards from YouTube Studio analytics."""
        metrics = []
        try:
            # YouTube Studio renders metric cards with labels and values
            cards = await page.evaluate("""() => {
                const results = [];

                // Look for metric card patterns
                const metricElements = document.querySelectorAll(
                    'yta-metric-card, .metric-card, [class*="metric"], [class*="kpi"]'
                );
                for (const el of metricElements) {
                    const label = el.querySelector(
                        '.metric-label, .label, [class*="label"], [class*="title"]'
                    );
                    const value = el.querySelector(
                        '.metric-value, .value, [class*="value"], [class*="number"]'
                    );
                    if (label && value) {
                        const labelText = label.textContent?.trim();
                        const valueText = value.textContent?.trim();
                        if (labelText && valueText) {
                            results.push({label: labelText, value: valueText});
                        }
                    }
                }

                // Also check for aria-labelled stat elements
                const statEls = document.querySelectorAll('[role="status"], [aria-label*="metric"]');
                for (const el of statEls) {
                    const ariaLabel = el.getAttribute('aria-label') || '';
                    const text = el.textContent?.trim() || '';
                    if (ariaLabel && text) {
                        results.push({label: ariaLabel, value: text});
                    }
                }

                return results;
            }""")

            seen_names = set()
            for card in cards:
                name = self._normalize_metric_name(card.get("label", ""))
                if not name or name in seen_names:
                    continue
                value = self._parse_metric_value(card.get("value", ""))
                if value is not None:
                    seen_names.add(name)
                    metrics.append({
                        "platform": "youtube",
                        "account_id": account_id,
                        "metric_name": name,
                        "native_metric_name": card.get("label", ""),
                        "metric_value": value,
                        "date_start": date_start,
                        "date_end": date_end,
                        "source_dashboard": "YouTube Studio Overview",
                        "extraction_method": "dom_generic",
                    })

        except Exception as e:
            log.warning("youtube_generic_extraction_error", error=str(e))

        return metrics

    # ── Content Metrics Extraction ────────────────────────────────

    async def extract_content_metrics(
        self, account_id: str, date_start: str, date_end: str
    ) -> ExtractionResult:
        result = ExtractionResult(platform="youtube", account_id=account_id)
        ctx = await self._browser.get_context("youtube", account_id)
        page = await ctx.new_page()

        try:
            channel_id = await self._resolve_channel_id(page, account_id)
            content_url = f"{STUDIO_URL}/channel/{channel_id}/analytics/tab-content"
            resp = await page.goto(content_url, wait_until="domcontentloaded", timeout=settings.browser_timeout)

            challenge = await detect_challenge(page, resp)
            if challenge.detected:
                result.errors.append(f"Challenge: {challenge.challenge_type.value}")
                return result

            await page.wait_for_timeout(3000)

            # Extract content table data
            content_data = await self._extract_content_table(page, account_id, date_start, date_end)
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

    async def _extract_content_table(
        self, page: Page, account_id: str, date_start: str, date_end: str
    ) -> list[dict[str, Any]]:
        """Extract the content performance table from YouTube Studio."""
        records = []
        try:
            table_data = await page.evaluate("""() => {
                const results = [];
                // YouTube Studio content tab shows a table of videos
                const rows = document.querySelectorAll(
                    'ytcp-video-row, tr[class*="video"], [class*="content-row"]'
                );
                for (const row of rows) {
                    const titleEl = row.querySelector(
                        '.video-title, [class*="title"] a, [class*="title"] span'
                    );
                    const cells = row.querySelectorAll('td, [class*="cell"], [class*="metric"]');
                    const title = titleEl?.textContent?.trim() || '';
                    const values = Array.from(cells).map(c => c.textContent?.trim() || '');

                    if (title) {
                        results.push({title, values});
                    }
                }
                return results;
            }""")

            for item in table_data:
                record = {
                    "platform": "youtube",
                    "account_id": account_id,
                    "title": item.get("title", ""),
                    "content_type": "video",
                    "date_start": date_start,
                    "date_end": date_end,
                    "source_dashboard": "YouTube Studio Content",
                    "extraction_method": "dom",
                    "raw_values": item.get("values", []),
                }
                records.append(record)

        except Exception as e:
            log.warning("youtube_content_table_error", error=str(e))

        return records

    # ── Audience Metrics ──────────────────────────────────────────

    async def extract_audience_metrics(
        self, account_id: str, date_start: str, date_end: str
    ) -> ExtractionResult:
        result = ExtractionResult(platform="youtube", account_id=account_id)
        ctx = await self._browser.get_context("youtube", account_id)
        page = await ctx.new_page()

        try:
            channel_id = await self._resolve_channel_id(page, account_id)
            audience_url = f"{STUDIO_URL}/channel/{channel_id}/analytics/tab-audience"
            resp = await page.goto(audience_url, wait_until="domcontentloaded", timeout=settings.browser_timeout)

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
        """Extract audience demographic data from YouTube Studio."""
        data = []
        try:
            audience_info = await page.evaluate("""() => {
                const results = [];
                // Look for demographic sections
                const sections = document.querySelectorAll(
                    '[class*="demographic"], [class*="audience"], [class*="geography"]'
                );
                for (const section of sections) {
                    const heading = section.querySelector('h3, h4, [class*="heading"]');
                    const items = section.querySelectorAll('[class*="row"], [class*="item"], li');
                    const sectionName = heading?.textContent?.trim() || 'unknown';

                    for (const item of items) {
                        const label = item.querySelector('[class*="label"], [class*="name"]');
                        const value = item.querySelector('[class*="value"], [class*="percent"]');
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

            for item in audience_info:
                val = self._parse_metric_value(item.get("metric_value", ""))
                if val is not None:
                    data.append({
                        "platform": "youtube",
                        "account_id": account_id,
                        "metric_name": "audience_distribution",
                        "dimension": item.get("dimension", "unknown"),
                        "dimension_value": item.get("dimension_value", ""),
                        "metric_value": val,
                        "date_start": date_start,
                        "date_end": date_end,
                    })

        except Exception as e:
            log.warning("youtube_audience_extraction_error", error=str(e))

        return data

    # ── Helpers ────────────────────────────────────────────────────

    @staticmethod
    def _parse_metric_value(text: str) -> float | None:
        """Parse a metric value string into a float, handling K/M/B suffixes."""
        if not text:
            return None
        text = text.strip().replace(",", "").replace(" ", "")

        # Handle percentage
        if text.endswith("%"):
            text = text[:-1]

        # Handle suffixes
        multipliers = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}
        for suffix, mult in multipliers.items():
            if text.upper().endswith(suffix):
                try:
                    return float(text[:-1]) * mult
                except ValueError:
                    return None

        # Handle time formats like "1:23:45" (hours:minutes:seconds)
        if ":" in text:
            parts = text.split(":")
            try:
                if len(parts) == 3:
                    return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
                elif len(parts) == 2:
                    return int(parts[0]) * 60 + int(parts[1])
            except ValueError:
                return None

        # Handle negative numbers
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
            "watch time (hours)": "watch_time_hours",
            "watch time": "watch_time_hours",
            "subscribers": "subscribers_change",
            "subscribers gained": "subscribers_gained",
            "subscribers lost": "subscribers_lost",
            "estimated revenue": "estimated_revenue",
            "impressions click-through rate": "ctr",
            "click-through rate": "ctr",
            "average view duration": "avg_view_duration",
            "average percentage viewed": "avg_percent_viewed",
            "unique viewers": "unique_viewers",
            "returning viewers": "returning_viewers",
            "new viewers": "new_viewers",
        }
        if name in replacements:
            return replacements[name]

        # Generic normalization
        import re
        name = re.sub(r"[^a-z0-9]+", "_", name)
        return name.strip("_")
