"""
Per-provider rate limit tracking.

Tracks RPM (requests per minute) and RPD (requests per day)
for each provider based on their published limits.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Optional


@dataclass
class ProviderQuota:
    """Tracks usage for a single provider."""
    rpm_limit: int = 60
    rpd_limit: int = 10000
    tpd_limit: Optional[int] = None  # tokens per day
    
    # internal tracking
    _minute_requests: list[float] = field(default_factory=list)
    _day_requests: list[float] = field(default_factory=list)
    _day_tokens: int = 0
    _lock: Lock = field(default_factory=Lock)
    _exhausted_until: float = 0.0
    _error_count: int = 0
    _last_error_time: float = 0.0

    @property
    def minute_usage(self) -> int:
        now = time.time()
        self._minute_requests = [t for t in self._minute_requests if now - t < 60]
        return len(self._minute_requests)

    @property
    def day_usage(self) -> int:
        now = time.time()
        self._day_requests = [t for t in self._day_requests if now - t < 86400]
        return len(self._day_requests)

    @property
    def is_available(self) -> bool:
        if time.time() < self._exhausted_until:
            return False
        with self._lock:
            if self.minute_usage >= self.rpm_limit:
                return False
            if self.day_usage >= self.rpd_limit:
                return False
        return True

    @property
    def remaining_rpm(self) -> int:
        return max(0, self.rpm_limit - self.minute_usage)

    @property
    def remaining_rpd(self) -> int:
        return max(0, self.rpd_limit - self.day_usage)

    @property
    def score(self) -> float:
        """Higher score = more capacity available. Used for weighted routing."""
        if not self.is_available:
            return 0.0
        rpm_ratio = self.remaining_rpm / max(1, self.rpm_limit)
        rpd_ratio = self.remaining_rpd / max(1, self.rpd_limit)
        return rpm_ratio * rpd_ratio

    def record_request(self, tokens: int = 0):
        with self._lock:
            now = time.time()
            self._minute_requests.append(now)
            self._day_requests.append(now)
            if tokens > 0:
                self._day_tokens += tokens

    def record_error(self, status_code: int):
        """Record an error. Back off on 429s and 5xx."""
        with self._lock:
            now = time.time()
            self._error_count += 1
            self._last_error_time = now
            
            if status_code == 429:
                # back off 60s on rate limit
                self._exhausted_until = now + 60
            elif status_code >= 500:
                # back off 30s on server errors, exponential
                backoff = min(30 * (2 ** min(self._error_count, 4)), 300)
                self._exhausted_until = now + backoff
            elif status_code == 401 or status_code == 403:
                # auth errors - disable for 1 hour
                self._exhausted_until = now + 3600

    def reset_errors(self):
        with self._lock:
            self._error_count = 0
            self._exhausted_until = 0.0

    def to_dict(self) -> dict:
        return {
            "rpm_limit": self.rpm_limit,
            "rpm_used": self.minute_usage,
            "rpm_remaining": self.remaining_rpm,
            "rpd_limit": self.rpd_limit,
            "rpd_used": self.day_usage,
            "rpd_remaining": self.remaining_rpd,
            "is_available": self.is_available,
            "score": round(self.score, 3),
            "error_count": self._error_count,
            "exhausted_until": self._exhausted_until,
        }
