from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings
from app.schemas import HealthResponse


router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    # Reports liveness and which integrations are configured so deploys/monitors can probe readiness.
    return HealthResponse(
        status="ok",
        qdrant_url_configured=bool(settings.qdrant_url),
        qdrant_collection=settings.qdrant_collection,
        embedding_model=settings.embedding_model,
        supabase_configured=settings.supabase_configured,
    )
