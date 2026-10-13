"""Per-chat token-bucket rate limiting.

Cheap commands cost one token; commands that download a feed cost more, so one
chat cannot make the bot hammer a university server or burn the CPU.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(slots=True)
class _Bucket:
    tokens: float
    updated: float
    warned: bool = False


class RateLimiter:
    def __init__(
        self,
        *,
        burst: float = 8,
        per_minute: float = 20,
        clock: Callable[[], float] = time.monotonic,
        max_entries: int = 10_000,
    ) -> None:
        self.burst = burst
        self.rate = per_minute / 60
        self.clock = clock
        self.max_entries = max_entries
        self._buckets: dict[str, _Bucket] = {}

    def check(self, key: str, cost: float = 1) -> int:
        """Spend ``cost`` tokens; returns 0 if allowed, else seconds until it would be."""
        now = self.clock()
        bucket = self._buckets.get(key)
        if bucket is None:
            self._evict(now)
            bucket = self._buckets[key] = _Bucket(self.burst, now)
        bucket.tokens = min(self.burst, bucket.tokens + (now - bucket.updated) * self.rate)
        bucket.updated = now
        if bucket.tokens >= cost:
            bucket.tokens -= cost
            bucket.warned = False
            return 0
        if self.rate <= 0:
            return 3600
        return max(1, math.ceil((cost - bucket.tokens) / self.rate))

    def should_warn(self, key: str) -> bool:
        """True once per throttled burst, so the warning itself cannot be spammed."""
        bucket = self._buckets.get(key)
        if bucket is None or bucket.warned:
            return False
        bucket.warned = True
        return True

    def _evict(self, now: float) -> None:
        if len(self._buckets) < self.max_entries:
            return
        full_after = self.burst / self.rate if self.rate > 0 else 0
        stale = [k for k, b in self._buckets.items() if now - b.updated >= full_after]
        for key in stale or list(self._buckets)[: self.max_entries // 10]:
            del self._buckets[key]
