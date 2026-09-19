"""
API authentication and rate limiting.

The assignment's Milestone 1 acceptance matrix requires both before the API can
be called public-ready, and Phase 5 later builds abuse detection on top of the
same counters.

Design notes:
  * Auth is an API-key header check, off by default so local development and
    the existing test suite keep working. Set ``AUTH_ENABLED=true`` and
    ``API_KEYS=key1,key2`` in ``.env`` to turn it on.
  * Keys are compared with ``hmac.compare_digest`` to avoid leaking a key
    through response timing.
  * The limiter is a per-identity token bucket held in process memory, which is
    correct for the single-process dev server. Known limitation: with several
    API workers each process keeps its own buckets, so the effective limit is
    ``RATE_LIMIT_RPM x worker_count``. A shared Redis bucket is the Phase 5
    follow-up, tracked in docs/context.md.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

API_KEY_HEADER = "X-API-Key"

# Paths that never require a key, so health checks and docs stay reachable.
PUBLIC_PATHS = {
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/favicon.ico",
}
PUBLIC_PREFIXES = ("/outputs/",)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class SecurityConfig:
    auth_enabled: bool
    api_keys: frozenset[str]
    rate_limit_enabled: bool
    requests_per_minute: int
    burst: int

    @classmethod
    def from_env(cls) -> "SecurityConfig":
        raw_keys = os.getenv("API_KEYS", "")
        keys = frozenset(k.strip() for k in raw_keys.split(",") if k.strip())
        rpm = _env_int("RATE_LIMIT_RPM", 120)
        return cls(
            auth_enabled=_env_bool("AUTH_ENABLED", False),
            api_keys=keys,
            rate_limit_enabled=_env_bool("RATE_LIMIT_ENABLED", True),
            requests_per_minute=max(1, rpm),
            # Allow a short burst so a UI that fires several polls at once is
            # not throttled, while the sustained rate stays at the limit.
            burst=max(1, _env_int("RATE_LIMIT_BURST", max(10, rpm // 4))),
        )


class TokenBucketLimiter:
    """
    Per-identity token bucket.

    Each identity accrues ``rate`` tokens per second up to ``capacity``. A
    request costs one token; when the bucket is empty the request is rejected
    with the number of seconds until the next token.
    """

    def __init__(self, requests_per_minute: int, burst: int):
        self.rate = requests_per_minute / 60.0
        self.capacity = float(max(burst, 1))
        self._buckets: Dict[str, Tuple[float, float]] = {}
        self._lock = threading.Lock()

    def check(self, identity: str, now: Optional[float] = None) -> Tuple[bool, float]:
        """Return (allowed, retry_after_seconds)."""
        now = time.monotonic() if now is None else now
        with self._lock:
            tokens, last = self._buckets.get(identity, (self.capacity, now))
            tokens = min(self.capacity, tokens + (now - last) * self.rate)
            if tokens >= 1.0:
                self._buckets[identity] = (tokens - 1.0, now)
                return True, 0.0
            self._buckets[identity] = (tokens, now)
            retry_after = (1.0 - tokens) / self.rate if self.rate > 0 else 60.0
            return False, retry_after

    def reset(self, identity: Optional[str] = None) -> None:
        with self._lock:
            if identity is None:
                self._buckets.clear()
            else:
                self._buckets.pop(identity, None)

    def tracked_identities(self) -> int:
        with self._lock:
            return len(self._buckets)


class SecurityGate:
    """Combines key auth and rate limiting behind one ``inspect`` call."""

    def __init__(self, config: Optional[SecurityConfig] = None):
        self.config = config or SecurityConfig.from_env()
        self.limiter = TokenBucketLimiter(
            self.config.requests_per_minute, self.config.burst
        )
        if self.config.auth_enabled and not self.config.api_keys:
            logger.error(
                "AUTH_ENABLED=true but API_KEYS is empty - every request will be "
                "rejected. Set API_KEYS in .env."
            )

    # ------------------------------------------------------------------

    @staticmethod
    def is_public(path: str) -> bool:
        return path in PUBLIC_PATHS or path.startswith(PUBLIC_PREFIXES)

    def verify_key(self, presented: Optional[str]) -> bool:
        if not self.config.auth_enabled:
            return True
        if not presented:
            return False
        return any(
            hmac.compare_digest(presented, known) for known in self.config.api_keys
        )

    def identity(self, api_key: Optional[str], client_host: Optional[str]) -> str:
        """
        Rate-limit bucket key: the API key when present, else the client IP.

        The key is hashed rather than truncated. A prefix would let two distinct
        keys that happen to share their first characters land in the same
        bucket and consume each other's quota.
        """
        if api_key:
            digest = hashlib.sha256(api_key.encode("utf-8")).hexdigest()
            return f"key:{digest[:32]}"
        return f"ip:{client_host or 'unknown'}"

    def inspect(
        self,
        path: str,
        api_key: Optional[str],
        client_host: Optional[str],
    ) -> Tuple[bool, int, dict]:
        """
        Evaluate one request.

        Returns ``(allowed, status_code, detail)``. ``status_code`` is 0 when
        allowed; ``detail`` carries the response body and any headers to add.
        """
        if self.is_public(path):
            return True, 0, {}

        if not self.verify_key(api_key):
            return False, 401, {
                "detail": (
                    f"Missing or invalid API key. Send it in the {API_KEY_HEADER} header."
                ),
                "headers": {"WWW-Authenticate": API_KEY_HEADER},
            }

        if self.config.rate_limit_enabled:
            allowed, retry_after = self.limiter.check(
                self.identity(api_key, client_host)
            )
            if not allowed:
                return False, 429, {
                    "detail": (
                        f"Rate limit exceeded: {self.config.requests_per_minute} "
                        "requests/minute."
                    ),
                    "headers": {"Retry-After": str(max(1, int(retry_after + 0.5)))},
                }

        return True, 0, {}

    def describe(self) -> dict:
        """Non-secret summary for /health and the UI."""
        return {
            "authEnabled": self.config.auth_enabled,
            "configuredKeys": len(self.config.api_keys),
            "rateLimitEnabled": self.config.rate_limit_enabled,
            "requestsPerMinute": self.config.requests_per_minute,
            "burst": self.config.burst,
            "apiKeyHeader": API_KEY_HEADER,
        }
