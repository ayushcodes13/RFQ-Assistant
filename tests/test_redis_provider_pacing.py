"""Integration checks that Luna request pacing is shared across processes."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import time
import uuid

import httpx
import pytest

from rfq_assistant.ingestion.ai_extraction import OpenAICompatibleClient
from rfq_assistant.ingestion.provider_resilience import (
    ProviderCallGate,
    ProviderCallRejected,
)
from rfq_assistant.ingestion.redis_pacing import RedisSharedPacer


@pytest.fixture
def redis_client():
    redis = pytest.importorskip("redis")
    url = os.getenv("RFQ_TEST_REDIS_URL")
    process = None
    if not url:
        if not (redis_server := shutil.which("redis-server")):
            pytest.skip(
                "Set RFQ_TEST_REDIS_URL or install redis-server to run Redis pacing integration tests"
            )
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        process = subprocess.Popen(
            [
                redis_server,
                "--bind",
                "127.0.0.1",
                "--port",
                str(port),
                "--save",
                "",
                "--appendonly",
                "no",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        url = f"redis://127.0.0.1:{port}/15"
    client = redis.Redis.from_url(url, socket_connect_timeout=0.5, socket_timeout=0.5)
    try:
        deadline = time.monotonic() + 4
        while True:
            try:
                client.ping()
                break
            except redis.RedisError:
                if process is not None and process.poll() is not None:
                    pytest.fail("redis-server exited before becoming ready")
                if time.monotonic() >= deadline:
                    pytest.fail("Redis test service did not become ready")
                time.sleep(0.05)
        yield client
    finally:
        client.close()
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)


def _pacer(client, *, requests_per_minute: int, prefix: str) -> RedisSharedPacer:
    return RedisSharedPacer(
        client,
        requests_per_minute=requests_per_minute,
        prefix=f"{{{prefix}}}:provider",
    )


def test_independent_gate_instances_share_the_provider_rate_limit(redis_client):
    prefix = f"test-{uuid.uuid4().hex}"
    first = ProviderCallGate(
        requests_per_minute=1,
        admission_timeout_seconds=0.02,
        shared_pacer=_pacer(redis_client, requests_per_minute=1, prefix=prefix),
    )
    second = ProviderCallGate(
        requests_per_minute=1,
        admission_timeout_seconds=0.02,
        shared_pacer=_pacer(redis_client, requests_per_minute=1, prefix=prefix),
    )

    with first.acquire() as permit:
        permit.report_success()
    with pytest.raises(
        ProviderCallRejected, match="Shared provider pacing queue is full"
    ):
        second.acquire()


def test_provider_throttle_hold_is_shared_between_gate_instances(redis_client):
    prefix = f"test-{uuid.uuid4().hex}"
    first_pacer = _pacer(redis_client, requests_per_minute=60, prefix=prefix)
    second_pacer = _pacer(redis_client, requests_per_minute=60, prefix=prefix)
    first_pacer.hold(5)
    gate = ProviderCallGate(
        requests_per_minute=60,
        admission_timeout_seconds=0.02,
        shared_pacer=second_pacer,
    )

    with pytest.raises(
        ProviderCallRejected, match="Shared provider pacing queue is full"
    ):
        gate.acquire()


def test_http_429_retry_after_pauses_other_luna_workers(redis_client):
    prefix = f"test-{uuid.uuid4().hex}"
    source_gate = ProviderCallGate(
        requests_per_minute=60,
        admission_timeout_seconds=0.2,
        shared_pacer=_pacer(redis_client, requests_per_minute=60, prefix=prefix),
    )

    def throttle(_request):
        return httpx.Response(
            429, headers={"retry-after": "2"}, json={"error": "synthetic throttle"}
        )

    client = OpenAICompatibleClient(
        "synthetic-secret",
        "gpt-6-luna",
        "https://model.example.test/v1",
        transport=httpx.MockTransport(throttle),
        call_gate=source_gate,
        max_attempts=1,
        retry_max_delay_seconds=3,
    )
    other_worker_gate = ProviderCallGate(
        requests_per_minute=60,
        admission_timeout_seconds=0.02,
        shared_pacer=_pacer(redis_client, requests_per_minute=60, prefix=prefix),
    )
    try:
        with pytest.raises(httpx.HTTPStatusError):
            client.complete(system="synthetic", user="synthetic")
        with pytest.raises(
            ProviderCallRejected, match="Shared provider pacing queue is full"
        ):
            other_worker_gate.acquire()
    finally:
        client.close()


def test_redis_failure_falls_back_to_local_gate_without_exposing_error_text(caplog):
    class BrokenRedis:
        def eval(self, *_args):
            raise OSError("synthetic connection failure with private endpoint")

    pacer = RedisSharedPacer(
        BrokenRedis(),
        requests_per_minute=60,
        prefix=f"{{test-{uuid.uuid4().hex}}}:provider",
        sleeper=lambda _seconds: None,
    )
    assert pacer.acquire(0.1) is False
    assert "private endpoint" not in caplog.text
    assert "OSError" in caplog.text
    gate = ProviderCallGate(
        requests_per_minute=60,
        admission_timeout_seconds=0.1,
        shared_pacer=pacer,
        sleeper=lambda _seconds: None,
    )
    with gate.acquire() as permit:
        permit.report_success()


def test_initial_redis_outage_logs_even_before_first_minute(caplog):
    class BrokenRedis:
        def eval(self, *_args):
            raise OSError("private-synthetic-redis-address")

    pacer = RedisSharedPacer(
        BrokenRedis(),
        requests_per_minute=60,
        clock=lambda: 1.0,
        sleeper=lambda _seconds: None,
    )
    with caplog.at_level("WARNING"):
        assert pacer.acquire(0.01) is False
    assert "OSError" in caplog.text
    assert "private-synthetic-redis-address" not in caplog.text
