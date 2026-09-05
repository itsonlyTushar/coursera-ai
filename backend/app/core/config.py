"""Application configuration.

Typed settings loaded from environment variables / ``backend/.env`` via
``pydantic-settings``. A single cached :class:`Settings` instance is exposed
through :func:`get_settings`, which is used as a FastAPI dependency.
"""
from functools import lru_cache
import os
from pathlib import Path
from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Qdrant ---------------------------------------------------------
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "COURSEERA_ALMAX_MULTIMODAL"
    qdrant_api_key: str | None = None
    backend_key: str | None = None
    qdrant_backend_key: str | None = None
    qdrant_distance: str = "Cosine"

    # --- Embeddings -----------------------------------------------------
    embedding_model: str = "BAAI/bge-base-en-v1.5"
    embedding_dimensions: int = 768
    hf_home: str = str(BACKEND_ROOT / ".cache" / "huggingface")

    # --- Supabase -------------------------------------------------------
    supabase_url: str | None = None
    supabase_publishable_key: str | None = None
    supabase_secret_key: str | None = None
    supabase_jwks_url: str | None = None
    supabase_jwt_audience: str = "authenticated"

    # --- LLM (Groq) -----------------------------------------------------
    groq_api_key: str | None = None
    groq_model: str = "openai/gpt-oss-120b"

    # --- HuggingFace tokens --------------------------------------------
    hf_token: str | None = None
    hf_token_original: str | None = None
    hf_token_embedding: str | None = None

    # --- CORS -----------------------------------------------------------
    frontend_origins: str = (
        "http://localhost:3000,http://127.0.0.1:3000,https://coursera-mip.vercel.app"
    )

    # --- Observability --------------------------------------------------
    log_level: str = "INFO"

    # --- Derived values -------------------------------------------------
    @property
    def resolved_qdrant_api_key(self) -> str | None:
        # Picks the first Qdrant key across the accepted env-var aliases so callers read one source.
        return self.qdrant_api_key or self.backend_key or self.qdrant_backend_key

    @property
    def resolved_hf_token_embedding(self) -> str | None:
        # Picks the first available HuggingFace token so embedding calls always get a credential when one exists.
        return self.hf_token_embedding or self.hf_token_original or self.hf_token

    @property
    def cors_origins(self) -> list[str]:
        # Parses the comma-separated origins string into a clean list for the CORS middleware.
        return [origin.strip() for origin in self.frontend_origins.split(",") if origin.strip()]

    @property
    def supabase_configured(self) -> bool:
        # Reports whether persistence is usable so services can fail fast instead of half-working.
        return bool(self.supabase_url and self.supabase_secret_key)

    @property
    def auth_configured(self) -> bool:
        # Reports whether JWT verification can run so auth code can distinguish misconfig from bad tokens.
        return bool(self.supabase_jwks_url)

    def model_post_init(self, __context: Any) -> None:
        # Normalizes HF_HOME and exports env vars the standalone rag pipeline reads directly, so both layers agree.
        hf_home_path = Path(self.hf_home)
        if not hf_home_path.is_absolute():
            hf_home_path = BACKEND_ROOT / hf_home_path
        object.__setattr__(self, "hf_home", str(hf_home_path))

        os.environ.setdefault("HF_HOME", self.hf_home)
        os.environ.setdefault(
            "SENTENCE_TRANSFORMERS_HOME", str(hf_home_path / "sentence-transformers")
        )
        if self.resolved_qdrant_api_key:
            os.environ.setdefault("QDRANT_API_KEY", self.resolved_qdrant_api_key)
        if self.resolved_hf_token_embedding:
            os.environ.setdefault("HF_TOKEN_EMBEDDING", self.resolved_hf_token_embedding)


@lru_cache
def get_settings() -> Settings:
    # Builds the Settings once and caches it so every dependency shares a single parsed config.
    return Settings()
