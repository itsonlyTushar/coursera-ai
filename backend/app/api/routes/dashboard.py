from fastapi import APIRouter, Depends

from app.schemas import DashboardSummaryResponse
from app.services.supabase_service import SupabaseService, get_supabase_service


router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/dashboard/summary", response_model=DashboardSummaryResponse)
def dashboard_summary(
    service: SupabaseService = Depends(get_supabase_service),
) -> DashboardSummaryResponse:
    # Returns the aggregated dashboard summary so the frontend renders all cards from one request.
    return service.dashboard_summary()
