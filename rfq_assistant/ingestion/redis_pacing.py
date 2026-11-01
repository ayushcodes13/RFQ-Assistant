"""Redis-backed request-start pacing shared by all Luna worker processes.

Redis owns the schedule, so separate application processes do not each spend
the full configured provider quota. Redis failures degrade to the existing
process-local limiter; operators should alert on the sanitized fallback log.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from typing import Any, Callable

from rfq_assistant.ingestion.provider_resilience import ProviderCallRejected

log = logging.getLogger(__name__)

_TAKE_TURN = """
local time = redis.call('TIME')
local now = tonumber(time[1]) * 1000000 + tonumber(time[2])
local free = tonumber(redis.call('GET', KEYS[1]) or '0') or 0
local held = redis.call('PTTL', KEYS[2])
local turn = math.max(free, now)
if held > 0 then turn = math.max(turn, now + held * 1000) end
local budget = tonumber(ARGV[3])
if budget >= 0 and turn - now > budget then return '-1' end
local next = turn + tonumber(ARGV[1])
local ttl = math.ceil((next - now) / 1000) + tonumber(ARGV[2])
redis.call('SET', KEYS[1], string.format('%.0f', next), 'PX', string.format('%.0f', ttl))
return string.format('%.0f', turn - now)
"""

_HOLD = """
if redis.call('PTTL', KEYS[1]) < tonumber(ARGV[1]) then
  redis.call('SET', KEYS[1], '1', 'PX', tonumber(ARGV[1]))
end
return 1
"""


class RedisSharedPacer:
    """Atomic Redis schedule with bounded waits and local fallback on Redis errors."""

    def __init__(
        self,
        client: Any,
        *,
        requests_per_minute: int,
        prefix: str = "{rfq-luna}:provider",
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
        outage_cooldown_seconds: float = 30.0,
        late_turn_seconds: float = 0.1,
        clock_ttl_seconds: int = 60,
    ) -> None:
        if requests_per_minute < 1:
            raise ValueError("requests_per_minute must be positive")
        if (
            outage_cooldown_seconds <= 0
            or late_turn_seconds < 0
            or clock_ttl_seconds < 1
        ):
            raise ValueError("Redis pacing timing settings are invalid")
        self.client = client
        self.interval_microseconds = round(60_000_000 / requests_per_minute)
        self.next_key = f"{prefix}:next"
        self.hold_key = f"{prefix}:hold"
        self.clock_ttl_seconds = clock_ttl_seconds
        self._clock = clock
        self._sleeper = sleeper
        self._outage_cooldown_seconds = outage_cooldown_seconds
        self._late_turn_seconds = late_turn_seconds
        self._down_until = 0.0
        self._warned_at: float | None = None
        self._lock = threading.Lock()

    @classmethod
    def from_url(
        cls, url: str, *, requests_per_minute: int, prefix: str
    ) -> "RedisSharedPacer":
        """Build a Redis client with short socket timeouts; import redis only when enabled."""
        try:
            import redis
        except ImportError as exc:
            raise RuntimeError(
                "RFQ_LLM_REDIS_URL is set but the 'production' extra is not installed"
            ) from exc
        client = redis.Redis.from_url(
            url,
            socket_connect_timeout=0.75,
            socket_timeout=0.75,
            retry_on_timeout=False,
            decode_responses=True,
        )
        return cls(client, requests_per_minute=requests_per_minute, prefix=prefix)

    def acquire(self, timeout_seconds: float) -> bool:
        """Wait for a shared turn, return False to use local pacing after Redis failure."""
        now = self._clock()
        if now < self._down_until:
            return False
        deadline = now + timeout_seconds
        while True:
            remaining = max(0.0, deadline - self._clock())
            budget_microseconds = math.floor(remaining * 1_000_000)
            call_started = self._clock()
            try:
                wait_microseconds = int(
                    self.client.eval(
                        _TAKE_TURN,
                        2,
                        self.next_key,
                        self.hold_key,
                        self.interval_microseconds,
                        self.clock_ttl_seconds * 1000,
                        budget_microseconds,
                    )
                )
            except Exception as exc:  # noqa: BLE001 — local pacing remains available during Redis outages
                self._fallback_after_error(exc)
                return False

            if wait_microseconds < 0:
                raise ProviderCallRejected("Shared provider pacing queue is full.")
            delay = wait_microseconds / 1_000_000
            turn_at = call_started + delay
            sleep_for = max(0.0, turn_at - self._clock())
            if sleep_for:
                self._sleeper(sleep_for)
            lateness = self._clock() - turn_at
            if lateness <= self._late_turn_seconds:
                return True
            if self._clock() >= deadline:
                raise ProviderCallRejected("Shared provider pacing queue is full.")
            # Do not let a delayed worker use a stale turn and create a burst.

    def hold(self, seconds: float) -> None:
        """Pause future turns globally after a provider throttle response."""
        hold_ms = max(1, min(300_000, round(seconds * 1000)))
        try:
            self.client.eval(_HOLD, 1, self.hold_key, hold_ms)
        except Exception as exc:  # noqa: BLE001
            self._fallback_after_error(exc)

    def _fallback_after_error(self, exc: Exception) -> None:
        now = self._clock()
        with self._lock:
            self._down_until = now + self._outage_cooldown_seconds
            if self._warned_at is None or now - self._warned_at >= 60.0:
                log.warning(
                    "[rfq_provider_pacing] shared_limiter=unavailable fallback=process_local error=%s",
                    type(exc).__name__,
                )
                self._warned_at = now
