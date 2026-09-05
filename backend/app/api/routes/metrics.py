from fastapi import APIRouter, Depends, Query

from app.schemas import MetricsResponse
from app.services.qdrant_service import QdrantService, get_qdrant_service


router = APIRouter(prefix="/api", tags=["metrics"])


@router.get("/metrics", response_model=MetricsResponse)
def metrics(
    scan_limit: int = Query(default=5000, ge=1, le=10000),
    service: QdrantService = Depends(get_qdrant_service),
) -> MetricsResponse:
    # Exposes live Qdrant collection metrics so the dashboard can show index health and content breakdowns.
    return service.metrics(scan_limit=scan_limit)
