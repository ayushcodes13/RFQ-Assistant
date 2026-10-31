"""Environment-backed CORS origin configuration."""

import os
from urllib.parse import urlsplit


DEFAULT_CORS_ORIGINS = (
    "http://localhost",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:8000",
)


def configured_cors_origins() -> list[str]:
    """Return explicit browser origins, rejecting wildcard and malformed values."""
    raw = os.environ.get("RFQ_CORS_ORIGINS")
    if raw is None:
        return list(DEFAULT_CORS_ORIGINS)
    origins = [
        origin.strip().rstrip("/") for origin in raw.split(",") if origin.strip()
    ]
    for origin in origins:
        parsed = urlsplit(origin)
        try:
            _ = parsed.port  # Validate that an optional port is numeric and in range.
        except ValueError as exc:
            raise ValueError(
                "RFQ_CORS_ORIGINS must be a comma-separated list of explicit http(s) origins."
            ) from exc
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path
            or parsed.query
            or parsed.fragment
            or "*" in origin
        ):
            raise ValueError(
                "RFQ_CORS_ORIGINS must be a comma-separated list of explicit http(s) origins."
            )
    return list(dict.fromkeys(origins))
