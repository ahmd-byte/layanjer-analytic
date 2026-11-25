"""AI-assisted DOM metric extraction — fallback when deterministic selectors fail.

Sanitizes page content before sending to AI: strips scripts, styles, auth tokens,
and limits snippet size.  Never sends passwords, cookies, or session data.
"""
from __future__ import annotations

import re
from typing import Any

from playwright.async_api import Page

from layan_engine.ai.recovery import RecoveryEngine, RecoveryResult
from layan_engine.logging import get_logger

log = get_logger(__name__)

_STRIP_TAGS = re.compile(r"<(script|style|noscript|iframe)[^>]*>[\s\S]*?</\1>", re.I)
_STRIP_ATTRS = re.compile(
    r'\s+(data-token|data-session|data-csrf|data-auth|'
    r'data-cookie|data-nonce|data-secret|'
    r'access.?token|api.?key|session.?id)="[^"]*"',
    re.I,
)
_COLLAPSE_WS = re.compile(r"\s{3,}")


def sanitize_dom(html: str, max_chars: int = 4000) -> str:
    """Remove scripts, styles, and sensitive attributes from DOM HTML."""
    cleaned = _STRIP_TAGS.sub("", html)
    cleaned = _STRIP_ATTRS.sub("", cleaned)
    cleaned = _COLLAPSE_WS.sub("  ", cleaned)
    return cleaned[:max_chars]


async def get_page_dom_snippet(page: Page, selector: str = "main, [role='main'], .content, body") -> str:
    """Extract a sanitized DOM snippet from the page for AI consumption."""
    try:
        html = await page.evaluate(
            """(sel) => {
                const el = document.querySelector(sel) || document.body;
                return el ? el.innerHTML : '';
            }""",
            selector,
        )
        return sanitize_dom(html)
    except Exception as e:
        log.warning("dom_snippet_extraction_failed", error=str(e))
        return ""


async def get_simplified_dom_tree(page: Page, max_depth: int = 4) -> str:
    """Get a simplified tag-structure view of the page for selector recovery."""
    try:
        tree = await page.evaluate(
            """(maxDepth) => {
                function walk(el, depth) {
                    if (depth > maxDepth || !el || !el.tagName) return '';
                    const tag = el.tagName.toLowerCase();
                    const cls = el.className && typeof el.className === 'string'
                        ? '.' + el.className.trim().split(/\\s+/).slice(0, 2).join('.')
                        : '';
                    const id = el.id ? '#' + el.id : '';
                    const data = Array.from(el.attributes || [])
                        .filter(a => a.name.startsWith('data-') && !a.name.includes('token')
                            && !a.name.includes('session') && !a.name.includes('csrf'))
                        .map(a => `[${a.name}]`).join('');
                    const indent = '  '.repeat(depth);
                    let result = indent + '<' + tag + id + cls + data + '>\\n';
                    const kids = el.children;
                    if (kids && kids.length <= 20) {
                        for (const child of kids) {
                            result += walk(child, depth + 1);
                        }
                    } else if (kids && kids.length > 20) {
                        result += indent + '  <!-- ' + kids.length + ' children -->\\n';
                    }
                    return result;
                }
                return walk(document.querySelector('main') || document.body, 0);
            }""",
            max_depth,
        )
        return tree[:4000]
    except Exception as e:
        log.warning("dom_tree_extraction_failed", error=str(e))
        return ""


async def ai_extract_metrics(
    page: Page, platform: str, engine: RecoveryEngine | None = None
) -> RecoveryResult:
    """Use AI to extract metrics from the current page when selectors fail."""
    if engine is None:
        engine = RecoveryEngine()
    if not engine.is_configured:
        return RecoveryResult(error="AI provider not configured")

    snippet = await get_page_dom_snippet(page)
    if not snippet:
        return RecoveryResult(error="Could not extract DOM snippet")

    return await engine.extract_metrics_from_dom(platform, snippet)


async def ai_recover_selector(
    page: Page,
    platform: str,
    failed_selector: str,
    target_description: str,
    engine: RecoveryEngine | None = None,
) -> RecoveryResult:
    """Ask AI for alternative selectors when one fails."""
    if engine is None:
        engine = RecoveryEngine()
    if not engine.is_configured:
        return RecoveryResult(error="AI provider not configured")

    dom_tree = await get_simplified_dom_tree(page)
    if not dom_tree:
        return RecoveryResult(error="Could not extract DOM tree")

    return await engine.suggest_selectors(
        platform=platform,
        failed_selector=failed_selector,
        dom_structure=dom_tree,
        url=page.url,
        target_description=target_description,
    )
