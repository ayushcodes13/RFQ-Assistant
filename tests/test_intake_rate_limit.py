"""Admission-cap tests are synthetic; no uploaded customer documents."""
import importlib

from fastapi.testclient import TestClient

from rfq_assistant.api.intake_limit import IntakeRateLimiter


def test_limiter_bounded_window_and_retry_after():
    now = [100.0]
    limiter = IntakeRateLimiter(limit=2, period_seconds=60, clock=lambda: now[0])
    assert limiter.allow() == (True, 0)
    assert limiter.allow() == (True, 0)
    assert limiter.allow() == (False, 60)
    now[0] += 61.0
    assert limiter.allow() == (True, 0)


def test_single_host_limit_applies_before_upload_processing(monkeypatch):
    api = importlib.import_module("rfq_assistant.api.app")
    original = api.app.state.intake_rate_limiter
    api.app.state.intake_rate_limiter = IntakeRateLimiter(limit=1)
    try:
        client = TestClient(api.app)
        response = client.post("/api/rfqs", data={})
        assert response.status_code != 429
        blocked = client.post("/api/rfqs", data={})
        assert blocked.status_code == 429
        assert int(blocked.headers["retry-after"]) >= 1
        assert blocked.json()["detail"] == "Too many RFQ intake requests. Retry shortly."
        assert client.get("/api/health").status_code == 200
        assert client.post("/api/catalogs/import").status_code == 429
    finally:
        api.app.state.intake_rate_limiter = original


def test_invalid_rate_limit_is_not_silently_accepted():
    import pytest
    with pytest.raises(ValueError):
        IntakeRateLimiter(limit=0)
    with pytest.raises(ValueError):
        IntakeRateLimiter(limit=1001)
