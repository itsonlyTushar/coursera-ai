"""Authentication utilities for Supabase-issued JWTs.

IMPLEMENTED BUT NOT WIRED. No route depends on these helpers yet; every
endpoint is currently public. To protect an endpoint, add the dependency::

    from app.core.security import CurrentUser, get_current_user

    @router.get("/api/private")
    def private(user: CurrentUser = Depends(get_current_user)):
        return {"user_id": user.id}

Verification model
------------------
Supabase (asymmetric signing) publishes a JWKS document at
``SUPABASE_JWKS_URL``. Tokens are verified against that key set (RS256/ES256)
and the ``authenticated`` audience. The signing keys are cached by
``PyJWKClient`` and refreshed automatically on rotation.
"""
from functools import lru_cache
from typing import Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from pydantic import BaseModel, Field

from app.core.config import Settings, get_settings
from app.core.logging import get_logger


logger = get_logger(__name__)

_ALGORITHMS = ["RS256", "ES256"]
_required_bearer = HTTPBearer(auto_error=True)
_optional_bearer = HTTPBearer(auto_error=False)


class CurrentUser(BaseModel):
    """The authenticated principal extracted from a verified JWT."""

    id: str
    email: str | None = None
    role: str | None = None
    claims: dict[str, Any] = Field(default_factory=dict)


@lru_cache
def _jwk_client(jwks_url: str) -> PyJWKClient:
    # Caches one JWKS client per URL so signing keys are fetched once and reused across requests.
    return PyJWKClient(jwks_url)


def _decode(token: str, settings: Settings) -> dict[str, Any]:
    # Verifies a token's signature/audience against the JWKS and returns its claims, raising 401/500 on failure.
    if not settings.supabase_jwks_url:
        # Misconfiguration, not a client error.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication is not configured (SUPABASE_JWKS_URL missing).",
        )
    try:
        signing_key = _jwk_client(settings.supabase_jwks_url).get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=_ALGORITHMS,
            audience=settings.supabase_jwt_audience,
            options={"require": ["exp", "sub"], "verify_aud": True},
        )
    except jwt.PyJWTError as exc:
        logger.warning("JWT verification failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def _to_user(payload: dict[str, Any]) -> CurrentUser:
    # Maps raw JWT claims into a typed CurrentUser so routes get a stable principal shape.
    return CurrentUser(
        id=str(payload["sub"]),
        email=payload.get("email"),
        role=payload.get("role"),
        claims=payload,
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_required_bearer),
    settings: Settings = Depends(get_settings),
) -> CurrentUser:
    # Requires a valid bearer token so a protected route only runs for an authenticated user.
    """Require a valid bearer token; raise 401 otherwise."""
    return _to_user(_decode(credentials.credentials, settings))


def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_optional_bearer),
    settings: Settings = Depends(get_settings),
) -> CurrentUser | None:
    # Returns the user when a token is present so an endpoint can personalize without forcing login.
    """Return the user when a valid token is present, else ``None``."""
    if credentials is None:
        return None
    return _to_user(_decode(credentials.credentials, settings))
