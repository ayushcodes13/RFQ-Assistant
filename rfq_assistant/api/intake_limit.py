"""Bound memory and admission rates before expensive local RFQ intake.

A single-process local prototype guard, NOT a multi-instance/global quota.
Deployments require a shared, authenticated ingress limiter upstream.
"""
from __future__ import annotations

from collections import deque
from threading import Lock
import time
from typing import Callable


class IntakeRateLimiter:
    def __init__(self, limit: int, period_seconds: float = 60, clock: Callable[[], float] = time.monotonic):
        if not 1 <= limit <= 1000 or period_seconds <= 0:
            raise ValueError("Intake rate limit must be 1..1000 requests per positive window.")
        self.limit = limit
        self.period_seconds = period_seconds
        self.clock = clock
        self._timestamps: deque[float] = deque(maxlen=limit)
        self._lock = Lock()

    def allow(self) -> tuple[bool, int]:
        """Atomic admission; return (allowed, retry_after_seconds)."""
        with self._lock:
            now = self.clock()
            while self._timestamps and now - self._timestamps[0] >= self.period_seconds:
                self._timestamps.popleft()
            if len(self._timestamps) >= self.limit:
                remaining = max(1, int(self.period_seconds - (now - self._timestamps[0]) + 0.999))
                return False, remaining
            self._timestamps.append(now)
            return True, 0
