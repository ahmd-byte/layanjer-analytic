"""Centralized browser challenge detection and management."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from playwright.async_api import Page, Response

from layan_engine.logging import get_logger

log = get_logger(__name__)


class ChallengeType(str, Enum):
    CAPTCHA = "captcha"
    CLOUDFLARE = "cloudflare"
    RECAPTCHA = "recaptcha"
    HCAPTCHA = "hcaptcha"
    TURNSTILE = "turnstile"
    TWO_FACTOR = "two_factor"
    LOGIN_REDIRECT = "login_redirect"
    SECURITY_CHECKPOINT = "security_checkpoint"
    RATE_LIMIT = "rate_limit"
    ACCESS_DENIED = "access_denied"
    SUSPICIOUS_ACTIVITY = "suspicious_activity"
    SESSION_EXPIRED = "session_expired"
    EMPTY_RESPONSE = "empty_response"
    UNKNOWN = "unknown"


@dataclass
class ChallengeDetection:
    detected: bool = False
    challenge_type: ChallengeType = ChallengeType.UNKNOWN
    platform: str = ""
    description: str = ""
    detected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    requires_human: bool = False


# Matched against the page's visible text and URL only. Raw HTML is not used:
# dashboard JS bundles routinely contain words like "recaptcha" or "2fa".
_CHALLENGE_PATTERNS = {
    ChallengeType.CLOUDFLARE: [
        r"checking your browser",
        r"challenges\.cloudflare\.com",
        r"/cdn-cgi/challenge-platform",
    ],
    ChallengeType.CAPTCHA: [
        r"i'?m not a robot",
        r"verify (that )?you are (a )?human",
        r"complete the (security )?captcha",
        r"drag the (puzzle|slider)",
    ],
    ChallengeType.TWO_FACTOR: [
        r"\btwo.?factor authentication\b",
        r"\benter (the )?(6.digit |security |verification |login )?code\b",
        r"\bverification code\b",
        r"/two_step_verification",
        r"/two_factor",
        r"/challenge/(totp|sms|ipp|az)",
    ],
    ChallengeType.LOGIN_REDIRECT: [
        r"accounts\.google\.com/signin",
        r"login\.tiktok\.com",
        r"www\.facebook\.com/login",
        r"www\.instagram\.com/accounts/login",
    ],
    ChallengeType.SECURITY_CHECKPOINT: [
        r"facebook\.com/checkpoint",
        r"instagram\.com/challenge",
        r"\bsecurity check\b",
        r"\bverify (it'?s you|your identity)\b",
        r"\bsuspicious login\b",
    ],
    ChallengeType.SUSPICIOUS_ACTIVITY: [
        r"\bunusual (traffic|activity)\b",
        r"\bsuspicious activity\b",
        r"\bautomated (behaviou?r|requests|queries)\b",
    ],
}


async def detect_challenge(page: Page, response: Response | None = None) -> ChallengeDetection:
    result = ChallengeDetection()

    if response:
        if response.status == 403:
            result.detected = True
            result.challenge_type = ChallengeType.ACCESS_DENIED
            result.description = "HTTP 403 Forbidden"
            result.requires_human = True
            return result
        if response.status == 429:
            result.detected = True
            result.challenge_type = ChallengeType.RATE_LIMIT
            result.description = "HTTP 429 Rate Limited"
            return result

    try:
        url = page.url
        text = await page.evaluate("() => document.body ? document.body.innerText : ''")
    except Exception:
        return result

    haystack = f"{url}\n{text}".lower()
    for challenge_type, patterns in _CHALLENGE_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, haystack):
                result.detected = True
                result.challenge_type = challenge_type
                result.description = f"Matched pattern: {pattern}"
                result.requires_human = challenge_type in {
                    ChallengeType.CAPTCHA,
                    ChallengeType.RECAPTCHA,
                    ChallengeType.HCAPTCHA,
                    ChallengeType.TURNSTILE,
                    ChallengeType.TWO_FACTOR,
                    ChallengeType.SECURITY_CHECKPOINT,
                    ChallengeType.CLOUDFLARE,
                }
                log.warning(
                    "challenge_detected",
                    type=challenge_type.value,
                    url=url,
                    requires_human=result.requires_human,
                )
                return result

    return result


async def validate_analytics_response(page: Page, platform: str) -> bool:
    """Check that the page contains actual analytics content, not a challenge."""
    challenge = await detect_challenge(page)
    if challenge.detected:
        log.warning("analytics_blocked", platform=platform, challenge=challenge.challenge_type.value)
        return False
    return True
