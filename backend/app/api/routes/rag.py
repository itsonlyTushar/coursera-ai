from fastapi import APIRouter, Depends, Query

from app.schemas import (
    ConversationCreateRequest,
    CurateRecommendationRequest,
    CurateRecommendationResponse,
    FeedbackResponse,
    InteractionSaveRequest,
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
    # Runs the RAG pipeline then persists the query/answer/evidence (creating a conversation if needed) so chat is durable.
    response, evidence, answer_text = rag_service.synthesize(request)

    conversation_id = request.conversation_id
    if not conversation_id:
        conversation = supabase_service.create_conversation(
            ConversationCreateRequest(
                session_id=request.session_id or f"synthesize:{request.query[:64]}",
                title=request.query[:80],
                metadata={"created_by": "api_synthesize"},
            )
        )
        conversation_id = conversation.conversation_id

    saved = supabase_service.save_interaction(
        InteractionSaveRequest(
            conversation_id=conversation_id,
            query_text=request.query,
            generated_answer=answer_text,
            normalized_topic=request.metadata.get("normalized_topic"),
            detected_intent=request.metadata.get("detected_intent", "synthesis"),
            model_name=request.model_name or "rag.synthesis",
            model_provider=request.model_provider or "groq",
            prompt_version=request.metadata.get("prompt_version"),
            evidence=evidence,
            metadata={
                **(request.metadata or {}),
                "status": "completed",
                "retrieval_provider": "rag.retreival",
                "synthesis_provider": "rag.synthesis",
            },
        )
    )

    response.insight_id = saved.response_id
    response.conversation_id = saved.conversation_id
    response.query_id = saved.query_id
    return response


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
