"""Shared HTTP transport for Supabase PostgREST requests."""
from typing import Any

from fastapi import HTTPException
import httpx

from app.core.config import Settings
from app.core.logging import get_logger


logger = get_logger(__name__)


class PostgrestClient:
    def __init__(self, settings: Settings) -> None:
        self.enabled = settings.supabase_configured
        if not self.enabled:
            self.base_url = ""
            self._client: httpx.Client | None = None
            return

        self.base_url = settings.supabase_url.rstrip("/")  # type: ignore[union-attr]
        self._client = httpx.Client(
            base_url=self.base_url,
            headers={
                "apikey": settings.supabase_secret_key,  # type: ignore[dict-item]
                "Authorization": f"Bearer {settings.supabase_secret_key}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(30.0),
        )

    def request(
        self,
        method: str,
        path: str,
        *,
        json: Any | None = None,
        prefer: str | None = None,
    ) -> Any:
        if not self.enabled or self._client is None:
            raise HTTPException(status_code=503, detail="Supabase is not configured.")

        headers = {"Prefer": prefer} if prefer else None
        try:
            response = self._client.request(method, path, headers=headers, json=json)
        except httpx.HTTPError as exc:
            logger.error("Supabase request failed (%s %s): %s", method, path, exc)
            raise HTTPException(
                status_code=502,
                detail=f"Persistence backend is unreachable: {exc}",
            ) from exc

        if response.status_code >= 400:
            logger.error(
                "Supabase error (%s %s) -> %s: %s",
                method,
                path,
                response.status_code,
                response.text,
            )
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Persistence backend rejected the request ({response.status_code}): {response.text}",
            )

        if not response.content:
            return None
        return response.json()