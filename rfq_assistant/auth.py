"""Lightweight authentication and authorization boundary for customer pilot deployments.

Enforces:
- API key verification via X-API-Key or Authorization: Bearer <token>.
- Role-based access control (admin, reviewer, viewer).
- Authoritative actor attribution (never trusting arbitrary client-supplied actor strings).
- Fail-closed security when REQUIRE_AUTH=true, with convenient local demo fallback when false.
- No built-in pilot API keys: deployment operators must configure their own long, secret keys.
"""

import os
from dataclasses import dataclass
from typing import Dict, List, Optional
from fastapi import Depends, Header, HTTPException, status


@dataclass(frozen=True)
class PilotUser:
    """Authenticated pilot user identity."""
    user_id: str
    name: str
    role: str  # "admin", "reviewer", "viewer"


def is_auth_required() -> bool:
    """Returns True if authentication is strictly enforced."""
    return os.environ.get("REQUIRE_AUTH", "").lower() in ("1", "true")


def load_configured_keys() -> Dict[str, PilotUser]:
    """Load explicitly configured pilot credentials; never ship usable default keys.

    PILOT_API_KEYS consists of comma-separated key:role:display_name entries.
    An invalid configuration is rejected in full rather than being partially applied.
    """
    env_keys = os.environ.get("PILOT_API_KEYS", "").strip()
    if not env_keys:
        return {}

    users: Dict[str, PilotUser] = {}
    for entry in env_keys.split(","):
        parts = [p.strip() for p in entry.strip().split(":", 2)]
        if len(parts) != 3:
            raise ValueError("Malformed PILOT_API_KEYS entry.")
        key, role, name = parts
        if len(key) < 16 or role not in {"admin", "reviewer", "viewer"} or not name or key in users:
            raise ValueError("Invalid PILOT_API_KEYS entry: use unique keys of at least 16 characters, a valid role, and a name.")
        user_id = f"usr-{name.lower().replace(' ', '-')}"
        users[key] = PilotUser(user_id=user_id, name=name, role=role)
    return users


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
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Pilot authentication configuration is invalid.",
        )

    if is_auth_required() and not valid_keys:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Pilot authentication is enabled but PILOT_API_KEYS is not configured.",
        )

    if token:
        user = valid_keys.get(token)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Unauthorized: Invalid pilot API key.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return user

    if is_auth_required():
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
