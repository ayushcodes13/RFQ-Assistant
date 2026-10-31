"""Deterministic tests for local model-provider admission and recovery."""

from __future__ import annotations

import pytest
import httpx
import threading

from rfq_assistant.ingestion.ai_extraction import OpenAICompatibleClient
from rfq_assistant.ingestion.provider_resilience import (
    ProviderCallGate,
    ProviderCallRejected,
)


def test_request_starts_are_spaced_by_configured_rate_without_real_sleep():
    now = [100.0]
    delays = []

    def sleep(seconds):
        delays.append(seconds)
        now[0] += seconds

    gate = ProviderCallGate(
        requests_per_minute=60,
        clock=lambda: now[0],
        sleeper=sleep,
    )
    with gate.acquire() as permit:
        permit.report_success()
    with gate.acquire() as permit:
        permit.report_success()

    assert delays == [1.0]
    assert now[0] == 101.0


def test_concurrency_limit_holds_the_second_request_until_the_first_finishes():
    gate = ProviderCallGate(
        max_concurrent=1,
        requests_per_minute=60000,
        sleeper=lambda _seconds: None,
    )
    started = threading.Event()
    acquired = threading.Event()

    def second_request():
        started.set()
        with gate.acquire() as permit:
            acquired.set()
            permit.report_success()

    with gate.acquire() as first:
        thread = threading.Thread(target=second_request)
        thread.start()
        assert started.wait(timeout=1)
        assert not acquired.wait(timeout=0.02)
        first.report_success()

    assert acquired.wait(timeout=1)
    thread.join(timeout=1)
    assert not thread.is_alive()


def test_repeated_transient_failures_open_breaker_until_one_recovery_probe():
    now = [10.0]
    gate = ProviderCallGate(
        requests_per_minute=600,
        failure_threshold=2,
        open_seconds=5,
        clock=lambda: now[0],
        sleeper=lambda _seconds: None,
    )

    for _ in range(2):
        with gate.acquire() as permit:
            permit.report_transient_failure()

    with pytest.raises(ProviderCallRejected, match="circuit breaker is open"):
        gate.acquire()

    now[0] += 5
    with gate.acquire() as probe:
        with pytest.raises(ProviderCallRejected, match="awaiting its recovery probe"):
            gate.acquire()
        probe.report_success()

    with gate.acquire() as permit:
        permit.report_success()


def test_failed_recovery_probe_reopens_breaker():
    now = [0.0]
    gate = ProviderCallGate(
        requests_per_minute=600,
        failure_threshold=1,
        open_seconds=5,
        clock=lambda: now[0],
        sleeper=lambda _seconds: None,
    )
    with gate.acquire() as permit:
        permit.report_transient_failure()
    now[0] = 5
    with gate.acquire() as probe:
        probe.report_transient_failure()

    now[0] = 9.9
    with pytest.raises(ProviderCallRejected, match="circuit breaker is open"):
        gate.acquire()
    now[0] = 10
    with gate.acquire() as probe:
        probe.report_success()


def test_non_transient_provider_error_does_not_open_breaker():
    gate = ProviderCallGate(
        requests_per_minute=600,
        failure_threshold=1,
        sleeper=lambda _seconds: None,
    )
    with gate.acquire() as permit:
        permit.report_non_transient_failure()
    with gate.acquire() as permit:
        permit.report_success()


def test_rate_queue_over_budget_is_rejected_without_waiting():
    now = [0.0]
    gate = ProviderCallGate(
        requests_per_minute=1,
        admission_timeout_seconds=2,
        clock=lambda: now[0],
        sleeper=lambda seconds: now.__setitem__(0, now[0] + seconds),
    )
    with gate.acquire() as permit:
        permit.report_success()

    with pytest.raises(ProviderCallRejected, match="pacing queue is full"):
        gate.acquire()


def test_http_client_stops_retrying_when_breaker_opens_and_resumes_after_probe():
    now = [0.0]
    attempts = []
    gate = ProviderCallGate(
        requests_per_minute=600,
        failure_threshold=1,
        open_seconds=5,
        clock=lambda: now[0],
        sleeper=lambda seconds: now.__setitem__(0, now[0] + seconds),
    )

    def respond(request):
        attempts.append(request)
        if len(attempts) == 1:
            return httpx.Response(503, json={"error": "synthetic outage"})
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    client = OpenAICompatibleClient(
        "synthetic-secret",
        "gpt-6-luna",
        "https://example.invalid",
        transport=httpx.MockTransport(respond),
        call_gate=gate,
        max_attempts=3,
        retry_base_seconds=0.1,
        retry_max_delay_seconds=1,
        sleeper=lambda seconds: now.__setitem__(0, now[0] + seconds),
    )
    try:
        with pytest.raises(ProviderCallRejected, match="circuit breaker is open"):
            client.complete(system="system", user="synthetic")
        assert len(attempts) == 1

        with pytest.raises(ProviderCallRejected, match="circuit breaker is open"):
            client.complete(system="system", user="synthetic")
        assert len(attempts) == 1

        now[0] += 5
        assert client.complete(system="system", user="synthetic") == "ok"
        assert len(attempts) == 2
    finally:
        client.close()
