"""Regression tests for fail-closed authentication environment handling."""

import logging

import pytest
from fastapi.testclient import TestClient

from rfq_assistant import auth
from rfq_assistant.api.app import app


@pytest.fixture(autouse=True)
def clear_auth_key_cache():
    auth._parse_configured_keys.cache_clear()
    yield
    auth._parse_configured_keys.cache_clear()


@pytest.mark.parametrize("flag", ["1", "true", "yes", "on", " YES ", "On"])
def test_truthy_auth_values_reject_anonymous_requests(monkeypatch, flag):
    monkeypatch.setenv("REQUIRE_AUTH", flag)
    monkeypatch.setenv("PILOT_API_KEYS", "r2-synthetic-admin-key-0001:admin:Reviewer")

    response = TestClient(app).get("/api/rfqs")

    assert response.status_code == 401


def test_unset_auth_flag_keeps_the_local_demo_fallback(monkeypatch):
    monkeypatch.delenv("REQUIRE_AUTH", raising=False)
    monkeypatch.delenv("PILOT_API_KEYS", raising=False)

    assert TestClient(app).get("/api/rfqs").status_code == 200


def test_configured_keys_are_parsed_once_for_the_startup_value(monkeypatch):
    monkeypatch.setenv("REQUIRE_AUTH", "on")
    monkeypatch.setenv("PILOT_API_KEYS", "r2-synthetic-admin-key-0002:admin:Reviewer")

    auth.initialize_authentication()
    startup_cache = auth._parse_configured_keys.cache_info()
    assert startup_cache.misses == 1

    auth.load_configured_keys()
    auth.load_configured_keys()

    after_requests = auth._parse_configured_keys.cache_info()
    assert after_requests.misses == startup_cache.misses
    assert after_requests.hits == startup_cache.hits + 2


def test_key_validation_uses_fixed_length_constant_time_comparison_for_every_key(
    monkeypatch,
):
    monkeypatch.setenv("REQUIRE_AUTH", "yes")
    monkeypatch.setenv(
        "PILOT_API_KEYS",
        "r2-synthetic-admin-key-0003:admin:Admin,"
        "r2-synthetic-reviewer-key-0003:reviewer:Reviewer",
    )
    calls = []
    original_compare = auth.hmac.compare_digest

    def record_compare(candidate, configured):
        calls.append((candidate, configured))
        return original_compare(candidate, configured)

    monkeypatch.setattr(auth.hmac, "compare_digest", record_compare)
    response = TestClient(app).get(
        "/api/rfqs", headers={"X-API-Key": "r2-synthetic-reviewer-key-0003"}
    )

    assert response.status_code == 200
    assert len(calls) == 2
    assert all(len(candidate) == len(configured) == 32 for candidate, configured in calls)


def test_malformed_keys_fail_during_application_startup(monkeypatch):
    monkeypatch.setenv("REQUIRE_AUTH", "on")
    monkeypatch.setenv("PILOT_API_KEYS", "invalid-entry")

    with pytest.raises(RuntimeError, match="Invalid pilot authentication configuration"):
        with TestClient(app):
            pass


def test_configured_keys_with_auth_disabled_emit_startup_warning(monkeypatch, caplog):
    monkeypatch.delenv("REQUIRE_AUTH", raising=False)
    monkeypatch.setenv("PILOT_API_KEYS", "r2-synthetic-admin-key-0004:admin:Reviewer")

    with caplog.at_level(logging.WARNING, logger="rfq_assistant.auth"):
        auth.initialize_authentication()

    assert "REQUIRE_AUTH is disabled" in caplog.text
