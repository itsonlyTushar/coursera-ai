import jwt
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.core import security
from app.core.config import Settings


# Builds fake bearer credentials so the auth dependency can be called directly in tests.
def _creds(token: str = "tok") -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


# Builds isolated Settings (ignoring any local .env) so auth tests control the JWKS configuration.
def _settings(jwks: str | None = "https://example.test/.well-known/jwks.json") -> Settings:
    # _env_file=None isolates the test from any local backend/.env
    return Settings(_env_file=None, supabase_jwks_url=jwks)


# Replaces the JWKS client with a stub so token tests never hit the network.
def _patch_signing_key(monkeypatch):
    class _Key:
        key = "signing-key"

    class _Client:
        def get_signing_key_from_jwt(self, _token):
            return _Key()

    monkeypatch.setattr(security, "_jwk_client", lambda _url: _Client())


# Asserts a missing JWKS config surfaces as 500 (server misconfig), not a client auth error.
def test_not_configured_raises_500():
    with pytest.raises(HTTPException) as exc:
        security.get_current_user(_creds(), _settings(jwks=None))
    assert exc.value.status_code == 500


# Asserts the optional dependency yields None with no token so public endpoints stay accessible.
def test_optional_user_is_none_without_credentials():
    assert security.get_optional_user(None, _settings()) is None


# Asserts a well-formed token is decoded into a CurrentUser so protected routes get the right principal.
def test_valid_token_returns_user(monkeypatch):
    _patch_signing_key(monkeypatch)
    monkeypatch.setattr(
        security.jwt,
        "decode",
        lambda *a, **k: {"sub": "user-1", "email": "e@x.com", "role": "authenticated"},
    )
    user = security.get_current_user(_creds(), _settings())
    assert user.id == "user-1"
    assert user.email == "e@x.com"
    assert user.role == "authenticated"


# Asserts a bad token maps to 401 so unauthorized callers are rejected cleanly.
def test_invalid_token_returns_401(monkeypatch):
    _patch_signing_key(monkeypatch)

    def _boom(*_a, **_k):
        raise jwt.InvalidTokenError("bad token")

    monkeypatch.setattr(security.jwt, "decode", _boom)
    with pytest.raises(HTTPException) as exc:
        security.get_current_user(_creds(), _settings())
    assert exc.value.status_code == 401
