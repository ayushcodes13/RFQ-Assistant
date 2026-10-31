"""Lightweight authentication and authorization boundary for customer pilot deployments.

Enforces:
- API key verification via X-API-Key or Authorization: Bearer <token>.
- Role-based access control (admin, reviewer, viewer).
- Authoritative actor attribution (never trusting arbitrary client-supplied actor strings).
- Fail-closed security when REQUIRE_AUTH=true, with convenient local demo fallback when false.
- No built-in pilot API keys: deployment operators must configure their own long, secret keys.
"""

import hashlib
import hmac
import logging
import os
from functools import lru_cache
from dataclasses import dataclass
from typing import Dict, List, Optional
from fastapi import Depends, Header, HTTPException, status


@dataclass(frozen=True)
class PilotUser:
    """Authenticated pilot user identity."""
    user_id: str
    name: str
    role: str  # "admin", "reviewer", "viewer"


log = logging.getLogger(__name__)
_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}


def env_flag(name: str, default: bool = False) -> bool:
    """Parse a boolean environment variable consistently and reject typos."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    value = raw.strip().casefold()
    if value in _TRUE_VALUES:
        return True
    if value in _FALSE_VALUES or not value:
        return False
    raise ValueError(
        f"Invalid boolean value for {name}; use one of 1/true/yes/on or 0/false/no/off."
    )


def is_auth_required() -> bool:
    """Returns True if authentication is strictly enforced."""
    return env_flag("REQUIRE_AUTH", default=False)


@lru_cache(maxsize=16)
def _parse_configured_keys(env_keys: str) -> Dict[str, PilotUser]:
    """Parse one immutable environment value once and cache its credentials."""
    if not env_keys:
        return {}

    users: Dict[str, PilotUser] = {}
    for entry in env_keys.split(","):
        parts = [p.strip() for p in entry.strip().split(":", 2)]
        if len(parts) != 3:
            raise ValueError("Malformed PILOT_API_KEYS entry.")
        key, role, name = parts
        if (
            len(key) < 16
            or not key.isascii()
            or role not in {"admin", "reviewer", "viewer"}
            or not name
            or key in users
        ):
            raise ValueError("Invalid PILOT_API_KEYS entry: use unique keys of at least 16 characters, a valid role, and a name.")
        user_id = f"usr-{name.lower().replace(' ', '-')}"
        users[key] = PilotUser(user_id=user_id, name=name, role=role)
    return users


def load_configured_keys() -> Dict[str, PilotUser]:
    """Load configured pilot credentials from the cached startup environment.

    PILOT_API_KEYS consists of comma-separated key:role:display_name entries.
    An invalid configuration is rejected in full rather than being partially applied.
    """
    env_keys = os.environ.get("PILOT_API_KEYS", "").strip()
    return _parse_configured_keys(env_keys)


def initialize_authentication() -> None:
    """Validate credentials during application startup without logging secrets."""
    try:
        configured_keys = load_configured_keys()
        auth_required = is_auth_required()
    except ValueError as exc:
        raise RuntimeError(f"Invalid pilot authentication configuration: {exc}") from exc

    if configured_keys and not auth_required:
        log.warning(
            "PILOT_API_KEYS are configured while REQUIRE_AUTH is disabled; "
            "the local anonymous fallback remains active."
        )


def get_current_user(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None),
) -> PilotUser:
    """
    Authenticates incoming request and returns authoritative PilotUser.
    Rejects unauthenticated requests when REQUIRE_AUTH=true.
    """
    token = None
    if x_api_key:
        token = x_api_key.strip()
    elif authorization and authorization.startswith("Bearer "):
        token = authorization[len("Bearer ") :].strip()

    try:
        valid_keys = load_configured_keys()
        auth_required = is_auth_required()
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Pilot authentication configuration is invalid.",
        )

    if auth_required and not valid_keys:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Pilot authentication is enabled but PILOT_API_KEYS is not configured.",
        )

    if token:
        token_digest = hashlib.sha256(token.encode("utf-8")).digest()
        user = None
        # Hash to a fixed length before constant-time comparison. Compare every
        # configured key so list position cannot control first-match timing.
        for configured_key, configured_user in valid_keys.items():
            configured_digest = hashlib.sha256(configured_key.encode("ascii")).digest()
            if hmac.compare_digest(token_digest, configured_digest):
                user = configured_user
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Unauthorized: Invalid pilot API key.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return user

    if auth_required:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please provide a valid pilot API key via X-API-Key or Authorization header.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Local development & demo fallback (convenient local synthetic mode)
    return PilotUser(
        user_id="usr-local-demo",
        name="Local Pilot Operator",
        role="admin",
    )


def require_role(allowed_roles: List[str]):
    """Enforces that authenticated user possesses one of the allowed roles."""
    def role_checker(user: PilotUser = Depends(get_current_user)) -> PilotUser:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Forbidden: User '{user.name}' with role '{user.role}' lacks required permissions ({', '.join(allowed_roles)}).",
            )
        return user

    return role_checker
