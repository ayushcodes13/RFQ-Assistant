"""CORS stays explicit and supports deployment-configured frontend origins."""

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from rfq_assistant.api.cors import DEFAULT_CORS_ORIGINS, configured_cors_origins


def test_cors_defaults_to_existing_local_origins(monkeypatch):
    monkeypatch.delenv("RFQ_CORS_ORIGINS", raising=False)
    assert configured_cors_origins() == list(DEFAULT_CORS_ORIGINS)


def test_cors_environment_origins_are_used_by_middleware(monkeypatch):
    monkeypatch.setenv(
        "RFQ_CORS_ORIGINS", "https://demo.example.invalid, http://localhost:3010"
    )
    app = FastAPI()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=configured_cors_origins(),
        allow_credentials=True,
        allow_methods=["GET"],
        allow_headers=["authorization"],
    )
    response = TestClient(app).options(
        "/api/rfqs",
        headers={
            "Origin": "http://localhost:3010",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3010"


@pytest.mark.parametrize(
    "value",
    [
        "*",
        "https://demo.example.invalid/path",
        "ftp://demo.example.invalid",
        "http://localhost:invalid",
        "not-an-origin",
    ],
)
def test_cors_rejects_non_origin_values(monkeypatch, value):
    monkeypatch.setenv("RFQ_CORS_ORIGINS", value)
    with pytest.raises(ValueError, match="RFQ_CORS_ORIGINS"):
        configured_cors_origins()
