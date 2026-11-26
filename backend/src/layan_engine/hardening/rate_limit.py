"""Simple in-memory rate limiter for API endpoints.

Uses a sliding-window counter per IP. No external dependency — fits the
local-first architecture. Resets on server restart, which is acceptable
since the backend is single-user, bound to localhost.
"""
from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


@dataclass
class _Bucket:
    timestamps: list[float] = field(default_factory=list)


class RateLimiter:
    """Track request counts per key within a time window."""

    def __init__(self, max_requests: int = 60, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window = window_seconds
        self._buckets: dict[str, _Bucket] = defaultdict(_Bucket)

    def is_allowed(self, key: str) -> tuple[bool, int]:
        """Check if a request is allowed. Returns (allowed, remaining)."""
        now = time.monotonic()
        bucket = self._buckets[key]
        cutoff = now - self.window
        bucket.timestamps = [t for t in bucket.timestamps if t > cutoff]

        remaining = max(0, self.max_requests - len(bucket.timestamps))
        if len(bucket.timestamps) >= self.max_requests:
            return False, 0

        bucket.timestamps.append(now)
        return True, remaining - 1


_extraction_limiter = RateLimiter(max_requests=10, window_seconds=60)
_general_limiter = RateLimiter(max_requests=120, window_seconds=60)

_EXTRACTION_PREFIXES = (
    "/api/youtube/extract",
    "/api/tiktok/extract",
    "/api/instagram/extract",
    "/api/facebook/extract",
    "/api/scheduler/",
)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Apply rate limiting based on endpoint category."""

    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host if request.client else "unknown"
        path = request.url.path

        if any(path.startswith(p) for p in _EXTRACTION_PREFIXES) and request.method == "POST":
            limiter = _extraction_limiter
        else:
            limiter = _general_limiter

        allowed, remaining = limiter.is_allowed(client_ip)

        if not allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "rate_limited",
                    "message": "Too many requests",
                    "retry_after_seconds": limiter.window,
                },
                headers={"Retry-After": str(limiter.window)},
            )

        response: Response = await call_next(request)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response
