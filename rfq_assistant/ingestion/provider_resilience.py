"""Admission control for remote extraction-model calls.

Concurrency and the circuit breaker are process-local. Request starts can use
an optional shared provider pacer; without it, or during its outage, pacing is
process-local as well.
"""

from __future__ import annotations

import threading
import time
from contextlib import AbstractContextManager
from typing import Callable, Optional, Protocol


class ProviderCallRejected(RuntimeError):
    """A model call was rejected by provider pacing or circuit-breaker policy."""


class SharedProviderPacer(Protocol):
    """Optional cross-process request-start pacing backed by shared infrastructure."""

    def acquire(self, timeout_seconds: float) -> bool: ...

    def hold(self, seconds: float) -> None: ...


class ProviderPermit(AbstractContextManager):
    def __init__(self, gate: "ProviderCallGate", is_probe: bool):
        self._gate = gate
        self._is_probe = is_probe
        self._reported = False

    def report_success(self) -> None:
        self._gate._report_success()
        self._reported = True

    def report_transient_failure(self) -> None:
        self._gate._report_transient_failure(self._is_probe)
        self._reported = True

    def report_non_transient_failure(self) -> None:
        # HTTP 4xx responses still prove that the provider is reachable.
        self.report_success()

    def __exit__(self, exc_type, exc_value, traceback) -> Optional[bool]:
        try:
            if self._is_probe and not self._reported:
                self._gate._release_unreported_probe()
        finally:
            self._gate._semaphore.release()
        return None


class ProviderCallGate:
    """Bound request concurrency/rate and trip a short-lived local breaker."""

    def __init__(
        self,
        *,
        max_concurrent: int = 2,
        requests_per_minute: int = 60,
        failure_threshold: int = 4,
        open_seconds: float = 30.0,
        admission_timeout_seconds: float = 10.0,
        shared_pacer: Optional[SharedProviderPacer] = None,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ):
        if max_concurrent < 1 or requests_per_minute < 1 or failure_threshold < 1:
            raise ValueError("Provider gate limits must be positive")
        if open_seconds <= 0 or admission_timeout_seconds < 0:
            raise ValueError("Provider gate timing settings are invalid")
        self._semaphore = threading.BoundedSemaphore(max_concurrent)
        self._interval_seconds = 60.0 / requests_per_minute
        self._failure_threshold = failure_threshold
        self._open_seconds = open_seconds
        self._admission_timeout_seconds = admission_timeout_seconds
        self._shared_pacer = shared_pacer
        self._clock = clock
        self._sleeper = sleeper
        self._lock = threading.Lock()
        self._next_request_at = 0.0
        self._consecutive_failures = 0
        self._open_until = 0.0
        self._half_open_probe = False

    def acquire(self) -> ProviderPermit:
        """Acquire one paced wire-call permit or fail promptly for human review."""
        started = self._clock()
        globally_paced = False
        if self._shared_pacer is not None:
            globally_paced = self._shared_pacer.acquire(self._admission_timeout_seconds)
        if not globally_paced:
            with self._lock:
                now = self._clock()
                scheduled = max(now, self._next_request_at)
                delay = scheduled - now
                if delay > self._admission_timeout_seconds:
                    raise ProviderCallRejected("Provider request pacing queue is full.")
                self._next_request_at = scheduled + self._interval_seconds

            if delay:
                self._sleeper(delay)
        remaining = max(0.0, self._admission_timeout_seconds - (self._clock() - started))
        if not self._semaphore.acquire(timeout=remaining):
            raise ProviderCallRejected("Provider concurrency limit is busy.")

        try:
            with self._lock:
                now = self._clock()
                if self._open_until and now < self._open_until:
                    raise ProviderCallRejected("Provider circuit breaker is open after repeated failures.")
                is_probe = False
                if self._open_until:
                    if self._half_open_probe:
                        raise ProviderCallRejected("Provider circuit breaker is awaiting its recovery probe.")
                    self._half_open_probe = True
                    is_probe = True
                return ProviderPermit(self, is_probe)
        except Exception:
            self._semaphore.release()
            raise

    def hold(self, seconds: float) -> None:
        """Share a bounded provider cooldown after a 429 when Redis pacing is enabled."""
        if self._shared_pacer is not None and seconds > 0:
            self._shared_pacer.hold(seconds)

    def _report_success(self) -> None:
        with self._lock:
            self._consecutive_failures = 0
            self._open_until = 0.0
            self._half_open_probe = False

    def _report_transient_failure(self, is_probe: bool) -> None:
        with self._lock:
            self._consecutive_failures += 1
            if is_probe or self._consecutive_failures >= self._failure_threshold:
                self._open_until = self._clock() + self._open_seconds
            self._half_open_probe = False

    def _release_unreported_probe(self) -> None:
        with self._lock:
            self._half_open_probe = False

