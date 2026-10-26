"""Lightweight authentication and authorization boundary for customer pilot deployments.

Enforces:
- API key verification via X-API-Key or Authorization: Bearer <token>.
- Role-based access control (admin, reviewer, viewer).
- Authoritative actor attribution (never trusting arbitrary client-supplied actor strings).
- Fail-closed security when REQUIRE_AUTH=true, with convenient local demo fallback when false.
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


# Default pilot keys for testing and deployment
DEFAULT_PILOT_KEYS: Dict[str, PilotUser] = {
    "pilot-admin-key": PilotUser(user_id="usr-admin", name="Authorized Administrator", role="admin"),
    "pilot-reviewer-key": PilotUser(user_id="usr-reviewer", name="Authorized Reviewer", role="reviewer"),
    "pilot-viewer-key": PilotUser(user_id="usr-viewer", name="Read-Only Auditor", role="viewer"),
}


def is_auth_required() -> bool:
    """Returns True if authentication is strictly enforced."""
    return os.environ.get("REQUIRE_AUTH", "").lower() in ("1", "true")


def load_configured_keys() -> Dict[str, PilotUser]:
    """Loads configured API keys from environment or defaults."""
    env_keys = os.environ.get("PILOT_API_KEYS", "").strip()
    if not env_keys:
        return DEFAULT_PILOT_KEYS

    users: Dict[str, PilotUser] = {}
    for entry in env_keys.split(","):
        parts = entry.strip().split(":")
        if len(parts) >= 3:
            key, role, name = parts[0].strip(), parts[1].strip(), parts[2].strip()
            user_id = f"usr-{name.lower().replace(' ', '-')}"
            users[key] = PilotUser(user_id=user_id, name=name, role=role)
    return users or DEFAULT_PILOT_KEYS


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

    valid_keys = load_configured_keys()

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
