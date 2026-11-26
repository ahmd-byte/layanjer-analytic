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
FB_PAGES_YOU_MANAGE = f"{FB_BASE}/pages/?category=your_pages"
FB_SUITE_OVERVIEW = f"{FB_BUSINESS_SUITE}/latest/insights/overview?asset_id={{asset_id}}"

FB_ME = f"{FB_BASE}/me"

# Lists the Pages on "Pages you manage" and, for each wanted name, the Page's Business Suite
# asset_id (from the card's own asset_id link, else the Page id in its profile.php link).
_MANAGED_PAGES_JS = r"""(targets) => {
  const norm = s => (s || '').trim().toLowerCase();
  const anchors = [...document.querySelectorAll('a[href]')];
  const pageLinks = anchors.filter(a => /profile\.php\?id=\d+/.test(a.href) && a.innerText.trim());
  const pages = [...new Set(pageLinks.map(a => a.innerText.trim()))];
  const first = document.querySelector('a[href*="asset_id="]');
  const firstAsset = first ? (first.href.match(/asset_id=(\d+)/) || [])[1] || null : null;
  const matches = [];
  for (const t of targets) {
    const a = anchors.find(x => norm(x.innerText) === norm(t));
    if (!a) continue;
    const idm = a.href.match(/profile\.php\?id=(\d+)/);
    let asset = null;
    for (let el = a.parentElement; el; el = el.parentElement) {
      const ids = new Set([...el.querySelectorAll('a[href*="profile.php?id="]')]
        .map(x => (x.href.match(/id=(\d+)/) || [])[1]));
      if (ids.size > 1) break;  // walked past this Page's card
      const link = el.querySelector('a[href*="asset_id="]');
      if (link) { asset = (link.href.match(/asset_id=(\d+)/) || [])[1] || null; break; }
    }
    matches.push({target: t, name: a.innerText.trim(), asset_id: asset || (idm ? idm[1] : null)});
  }
  return {pages, first: {name: pages[0] || null, asset_id: firstAsset}, matches};
}"""

_PROFILE_JS = r"""() => {
  const m = location.href.match(/profile\.php\?id=(\d+)/);
  // 2026 profiles have no name heading (the only <h1> is "Chats"); the name is the line
  // right above the "N friends" / "N followers" count.
  const main = document.querySelector('[role="main"]');
  const lines = (main ? main.innerText : '').split('\n').map(s => s.trim()).filter(Boolean);
  const i = lines.findIndex(s => /^[\d.,]+[KM]?\s+(friends?|followers?)\b/i.test(s));
  const title = document.title.replace(/^\(\d+\+?\)\s*/, '').split(' | ')[0].trim();
  return {id: m ? m[1] : null, name: (i > 0 ? lines[i - 1] : null) || (title && title !== 'Facebook' ? title : null)};
}"""

# Business Suite (2026) renders each metric as: label line, a zero-width-space line, value line.
_SUITE_METRICS_JS = r"""() => {
  const lines = document.body.innerText.split('\n').map(s => s.trim()).filter(Boolean);
  const start = lines.indexOf('Performance');
  const end = lines.findIndex((s, i) => i > start && /^Recent (ads|content)$/.test(s));
  const out = [];
  for (let i = Math.max(start, 1); i < (end > 0 ? end : lines.length) - 1; i++) {
    if (lines[i] !== '​') continue;
    const label = lines[i - 1], value = lines[i + 1];
    if (!label || label === '​' || /^From (non-)?followers$/.test(label)) continue;
    out.push({label, value});
  }
  const range = lines.find(s => /^Last \d+ days: /.test(s)) || null;
  return {metrics: out, range};
}"""


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
                    lambda url: "facebook.com" in url
                    and not any(s in url for s in ("/login", "/checkpoint", "two_step_verification", "/recover")),
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
            if not self._page_name:
                await self._resolve_managed_page(page)

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
            managed = await self._resolve_managed_page(page)
            if managed and managed.get("error"):
                result.errors.append(managed["error"])
                return result
            if managed and managed.get("asset_id"):
                resp = await page.goto(
                    FB_SUITE_OVERVIEW.format(asset_id=managed["asset_id"]),
                    wait_until="domcontentloaded",
                    timeout=settings.browser_timeout,
                )
                challenge = await detect_challenge(page, resp)
                if challenge.detected:
                    result.errors.append(f"Challenge detected: {challenge.challenge_type.value}")
                    return result
                await page.wait_for_timeout(8000)
                await self._select_suite_period(page, date_start, date_end)
                suite_metrics = await self._extract_suite_overview(page, account_id, date_start, date_end)
                if suite_metrics:
                    result.metrics = suite_metrics
                    result.extraction_method = "dom"
                    result.success = True
                    log.info("facebook_suite_extracted", page=managed.get("name"), metrics=len(suite_metrics))
                    return result
                if managed.get("kind") == "profile":
                    result.errors.append(
                        f"No insights for the profile '{managed['name']}'. Facebook only shows insights for "
                        "Pages and for profiles with professional mode on. Turn on professional mode "
                        "(facebook.com/professional_dashboard) or create the Page, then pull again."
                    )
                    return result
                if _parse_targets(settings.facebook_target_pages):
                    # A named target loaded but showed nothing; the legacy flow below would pick
                    # whichever business Meta defaults to, which may be a different Page.
                    result.errors.append(f"Business Suite showed no metrics for '{managed.get('name')}'")
                    return result
                result.warnings.append("Business Suite overview loaded but no metrics were parsed")

            # Older Business Suite entry point (redirects to a business picker in 2026)
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

    async def _resolve_managed_page(self, page: Page) -> dict[str, str | None] | None:
        """The Page (or professional profile) to pull: the first FACEBOOK_TARGET_PAGES name found,
        else, when no targets are set, the first Page the user manages.

        Returns {"name", "asset_id", "kind"} or {"error": ...} when no target exists.
        """
        targets = _parse_targets(settings.facebook_target_pages)
        try:
            await page.goto(FB_PAGES_YOU_MANAGE, wait_until="domcontentloaded", timeout=settings.browser_timeout)
            await page.wait_for_timeout(5000)
            found = await page.evaluate(_MANAGED_PAGES_JS, targets)
            profile: dict[str, str | None] = {}
            if targets:
                await page.goto(FB_ME, wait_until="domcontentloaded", timeout=settings.browser_timeout)
                try:
                    await page.get_by_text(re.compile(r"^[\d.,]+[KM]?\s+(friends?|followers?)\b", re.I)).first.wait_for(
                        timeout=15000
                    )
                except PlaywrightTimeout:
                    pass
                profile = await page.evaluate(_PROFILE_JS)
        except Exception as e:
            log.warning("facebook_managed_page_lookup_failed", error=str(e))
            return None

        chosen = _choose_target(targets, found, profile)
        if chosen.get("name"):
            self._page_name = chosen["name"]
        log.info("facebook_target_resolved", target=chosen.get("name"), kind=chosen.get("kind"),
                 managed_pages=len(found.get("pages", [])))
        return chosen

    async def _select_suite_period(self, page: Page, date_start: str, date_end: str) -> None:
        from datetime import date

        try:
            span = (date.fromisoformat(date_end) - date.fromisoformat(date_start)).days + 1
        except ValueError:
            return
        days = min((7, 28, 90), key=lambda d: abs(d - span))
        picker = page.get_by_role("button", name=re.compile(r"^Last \d+ days: ")).first
        try:
            if not await picker.is_enabled(timeout=3000):
                # Overview's range control is aria-disabled (fixed to 28 days) as of Nov 2026.
                log.info("facebook_period_fixed_by_page", requested_days=days)
                return
            await picker.click(timeout=4000)
            await page.wait_for_timeout(1500)
            await page.get_by_text(f"Last {days} days", exact=True).first.click(timeout=4000)
            await page.wait_for_timeout(1500)
            update = page.get_by_role("button", name=re.compile(r"^(Update|Apply)$"))
            if await update.count():
                await update.first.click(timeout=3000)
            await page.wait_for_timeout(6000)
        except Exception:
            await page.keyboard.press("Escape")
            log.warning("facebook_period_select_failed", days=days)

    async def _extract_suite_overview(
        self, page: Page, account_id: str, date_start: str, date_end: str
    ) -> list[dict[str, Any]]:
        from datetime import datetime

        found = await page.evaluate(_SUITE_METRICS_JS)
        shown = re.search(r"(\d{1,2} \w{3} \d{4}) - (\d{1,2} \w{3} \d{4})", found.get("range") or "")
        if shown:
            try:
                date_start, date_end = (datetime.strptime(d, "%d %b %Y").date().isoformat() for d in shown.groups())
            except ValueError:
                pass

        metrics: list[dict[str, Any]] = []
        for card in found.get("metrics", []):
            label, raw = card["label"], card["value"]
            name = self._normalize_metric_name(label)
            seconds = self._parse_duration_seconds(raw)
            if seconds is not None:
                name, value = f"{name}_seconds", seconds
            else:
                value = self._parse_metric_value(raw)
            if not name or value is None or any(m["metric_name"] == name for m in metrics):
                continue
            metrics.append({
                "platform": "facebook",
                "account_id": account_id,
                "metric_name": name,
                "native_metric_name": label,
                "metric_value": value,
                "date_start": date_start,
                "date_end": date_end,
                "source_dashboard": f"Meta Business Suite Insights ({self._page_name or 'Page'})",
                "extraction_method": "dom",
            })
        return metrics

    @staticmethod
    def _parse_duration_seconds(text: str) -> float | None:
        m = re.fullmatch(r"\s*(?:(\d+)h)?\s*(?:(\d+)m)?\s*(?:(\d+)s)?\s*", text or "")
        if not m or not any(m.groups()):
            return None
        h, mi, s = (int(g or 0) for g in m.groups())
        return float(h * 3600 + mi * 60 + s)

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


def _parse_targets(raw: str) -> list[str]:
    return [t.strip() for t in (raw or "").split(",") if t.strip()]


def _choose_target(targets: list[str], found: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    """Pick the first wanted name that exists: a managed Page, or the signed-in profile itself.

    With no targets, falls back to the first managed Page.
    """
    if not targets:
        first = found.get("first") or {}
        return {"name": first.get("name"), "asset_id": first.get("asset_id"), "kind": "page"}

    pages = {m["target"].lower(): m for m in found.get("matches", []) if m.get("asset_id")}
    profile_name = (profile.get("name") or "").strip().lower()
    for t in targets:
        if t.lower() in pages:
            m = pages[t.lower()]
            return {"name": m["name"], "asset_id": m["asset_id"], "kind": "page"}
        if profile_name and t.lower() == profile_name and profile.get("id"):
            return {"name": profile["name"], "asset_id": profile["id"], "kind": "profile"}

    managed = ", ".join(found.get("pages", [])) or "none"
    return {"error": (
        f"None of the Facebook targets ({', '.join(targets)}) were found. "
        f"Pages this login manages: {managed}. Create the Page or add it to this login, "
        "or change FACEBOOK_TARGET_PAGES in .env."
    )}
