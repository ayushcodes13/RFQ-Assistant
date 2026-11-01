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


def test_workspace_identity_is_bound_to_each_configured_key(monkeypatch):
    monkeypatch.setenv("REQUIRE_AUTH", "true")
    monkeypatch.setenv(
        "PILOT_API_KEYS",
        "workspace-admin-secret-0001:admin:usr-admin:ws-north:North Admin,"
        "workspace-reviewer-secret-0001:reviewer:usr-reviewer:ws-north:North Reviewer",
    )

    users = auth.load_configured_keys()

    assert users["workspace-admin-secret-0001"].workspace_id == "ws-north"
    assert users["workspace-reviewer-secret-0001"].workspace_id == "ws-north"
    response = TestClient(app).get(
        "/api/session", headers={"X-API-Key": "workspace-admin-secret-0001"}
    )
    assert response.json()["workspace_id"] == "ws-north"


def test_legacy_key_formats_use_the_single_workspace_compatibility_id(monkeypatch):
    monkeypatch.setenv(
        "PILOT_API_KEYS", "legacy-key-secret-000001:admin:Legacy Operator"
    )

    user = next(iter(auth.load_configured_keys().values()))

    assert user.workspace_id == "ws-default"


def test_multiple_workspace_credentials_are_rejected_until_isolation_is_implemented(
    monkeypatch,
):
    monkeypatch.setenv("REQUIRE_AUTH", "true")
    monkeypatch.setenv(
        "PILOT_API_KEYS",
        "workspace-a-secret-000001:admin:usr-admin-a:ws-alpha:Alpha Admin,"
        "workspace-b-secret-000001:admin:usr-admin-b:ws-bravo:Bravo Admin",
    )

    with pytest.raises(ValueError, match="supports one workspace only"):
        auth.load_configured_keys()
    response = TestClient(app).get("/api/rfqs")
    assert response.status_code == 503


def test_key_validation_uses_constant_time_comparison_for_every_key(
    monkeypatch,
):
    monkeypatch.setenv("REQUIRE_AUTH", "yes")
    monkeypatch.setenv(
        "PILOT_API_KEYS",
        "r2-synthetic-admin-key-0003000:admin:Admin,"
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
    assert all(isinstance(candidate, bytes) for candidate, _ in calls)
    assert all(isinstance(configured, bytes) for _, configured in calls)
    assert len({len(configured) for _, configured in calls}) == 1


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
