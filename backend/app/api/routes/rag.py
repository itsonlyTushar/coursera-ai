from fastapi import APIRouter, Depends, Query

from app.schemas import (
    CurateRecommendationRequest,
    CurateRecommendationResponse,
    FeedbackResponse,
    ReviewFeedbackRequest,
    SynthesizeRequest,
    SynthesizeResponse,
)
from app.services.rag_service import RagService, get_rag_service
from app.services.supabase_service import SupabaseService, get_supabase_service


router = APIRouter(prefix="/api", tags=["rag"])


@router.post("/synthesize", response_model=SynthesizeResponse)
def synthesize(
    request: SynthesizeRequest,
    rag_service: RagService = Depends(get_rag_service),
    supabase_service: SupabaseService = Depends(get_supabase_service),
) -> SynthesizeResponse:
    # Delegates the run-then-persist orchestration to the service layer, keeping the route
    # itself focused on validation and dependency injection only.
    return rag_service.synthesize_and_record(request, supabase_service)


@router.post("/recommendations", response_model=CurateRecommendationResponse)
def curate_recommendation(
    request: CurateRecommendationRequest,
    service: SupabaseService = Depends(get_supabase_service),
) -> CurateRecommendationResponse:
    # Saves a human-curated recommendation so approved insights move into the review/curation queue.
    return service.curate_recommendation(request)


@router.get("/recommendations", response_model=list[dict])
def list_recommendations(
    limit: int = Query(default=12, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    service: SupabaseService = Depends(get_supabase_service),
) -> list[dict]:
    # Returns paginated curated recommendations so the recommendations page can list them with context.
    return service.list_curated_recommendations(limit=limit, offset=offset)


@router.post("/review-feedback", response_model=FeedbackResponse)
def review_feedback(
    request: ReviewFeedbackRequest,
    service: SupabaseService = Depends(get_supabase_service),
) -> FeedbackResponse:
    # Records a reviewer's approve/reject decision so the human-in-the-loop outcome is stored against the response.
    return service.save_review_feedback(request)
