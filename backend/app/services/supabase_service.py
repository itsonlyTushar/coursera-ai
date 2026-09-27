"""Supabase (PostgREST) persistence for the human-in-the-loop RAG pipeline."""
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

from fastapi import HTTPException

from app.core.config import Settings, get_settings
from app.schemas import (
    ConversationCreateRequest,
    ConversationResponse,
    CurateRecommendationRequest,
    CurateRecommendationResponse,
    DashboardSummaryResponse,
    FeedbackCreateRequest,
    FeedbackResponse,
    InteractionSaveRequest,
    InteractionSaveResponse,
    ReviewFeedbackRequest,
)
from app.integrations.supabase.interaction_persistence import SupabaseInteractionService
from app.integrations.supabase.postgrest_client import PostgrestClient


class SupabaseService:
    def __init__(self, settings: Settings) -> None:
        # Shares one configured transport across the facade's persistence workflows.
        self.settings = settings
        self._postgrest = PostgrestClient(settings)
        self._interactions = SupabaseInteractionService(self._postgrest)

    # --- Conversations --------------------------------------------------
    def create_conversation(self, request: ConversationCreateRequest) -> ConversationResponse:
        # Inserts a new conversation row so subsequent queries/responses have a parent to attach to.
        data = self._request(
            "POST",
            "/rest/v1/conversations",
            json={
                "session_id": request.session_id,
                "title": request.title,
                "user_id": request.user_id,
                "metadata": request.metadata or {},
            },
            prefer="return=representation",
        )
        return ConversationResponse(**data[0])

    def list_conversations(self, limit: int) -> list[ConversationResponse]:
        # Returns recent conversations newest-first so the frontend can populate the chat history list.
        data = self._request(
            "GET",
            f"/rest/v1/conversations?select=*&order=started_at.desc&limit={limit}",
        )
        return [ConversationResponse(**item) for item in data]

    def get_conversation_messages(self, conversation_id: str) -> list[dict[str, Any]]:
        # Fetches a conversation's queries with nested responses/evidence/recs in one embedded read for the transcript.
        data = self._request(
            "GET",
            f"/rest/v1/user_queries?conversation_id=eq.{conversation_id}"
            "&select=*,generated_responses(*,retrieval_evidence(*),recommendations(*))"
            "&order=created_at.asc",
        )
        return data or []

    # --- Interactions ---------------------------------------------------
    def save_interaction(self, request: InteractionSaveRequest) -> InteractionSaveResponse:
        return self._interactions.save_interaction(request)

    # --- Recommendations (human-curated) --------------------------------
    def curate_recommendation(
        self, request: CurateRecommendationRequest
    ) -> CurateRecommendationResponse:
        # Saves a human-approved recommendation and flips its response to "pending" so it enters the review queue.
        result = self._request(
            "POST",
            "/rest/v1/recommendations",
            json={
                "response_id": request.insight_id,
                "recommendation_type": request.category,
                "recommendation_text": request.recommendation_text,
                "priority": request.priority,
                "metadata": {
                    **request.metadata,
                    "title": request.title,
                    "curated_at": datetime.now(timezone.utc).isoformat(),
                },
            },
            prefer="return=representation",
        )
        rec_id = result[0]["recommendation_id"] if result else "created"

        self._request(
            "PATCH",
            f"/rest/v1/generated_responses?response_id=eq.{request.insight_id}",
            json={"response_status": "pending"},
            prefer="return=minimal",
        )

        return CurateRecommendationResponse(
            recommendation_id=rec_id,
            insight_id=request.insight_id,
        )

    def list_curated_recommendations(self, limit: int = 12, offset: int = 0) -> list[dict[str, Any]]:
        # Returns paginated recommendations with their source response/query/evidence, plus any
        # review decision (user_feedback.approval) so the UI can show a persisted accepted/rejected
        # state instead of just the response's own status (which never reflects a review decision).
        return self._request(
            "GET",
            "/rest/v1/recommendations?select=*,generated_responses(query_id,generated_answer,"
            "response_status,user_queries(query_text),retrieval_evidence(qdrant_record_id,"
            "content_type,evidence_text,similarity_score,retrieval_rank),"
            "user_feedback(approval,created_at))"
            f"&order=created_at.desc&limit={limit}&offset={offset}",
        )

    # --- Feedback -------------------------------------------------------
    def save_feedback(self, request: FeedbackCreateRequest) -> FeedbackResponse:
        # Records a rating/approval for a generated response so quality and review decisions are tracked.
        data = self._request(
            "POST",
            "/rest/v1/user_feedback",
            json={
                "response_id": request.response_id,
                "user_id": request.user_id,
                "rating": request.rating,
                "is_helpful": request.is_helpful,
                "approval": request.approval,
                "feedback_text": request.feedback_text,
            },
            prefer="return=representation",
        )
        return FeedbackResponse(**data[0])

    def save_review_feedback(self, request: ReviewFeedbackRequest) -> FeedbackResponse:
        # Adapts a reviewer's decision into a feedback row so the review UI and feedback store share one path.
        response_id = request.response_id or request.insight_id
        if not response_id:
            raise HTTPException(
                status_code=422, detail="Either response_id or insight_id is required."
            )
        return self.save_feedback(
            FeedbackCreateRequest(
                response_id=response_id,
                user_id=request.user_id,
                rating=request.rating,
                is_helpful=request.is_helpful,
                approval=request.decision,
                feedback_text=request.notes,
            )
        )

    # --- Dashboard ------------------------------------------------------
    def dashboard_summary(self) -> DashboardSummaryResponse:
        # Aggregates the precomputed dashboard views into one payload so the frontend loads the dashboard in a single call.
        return DashboardSummaryResponse(
            activity_summary=self._select_first("dashboard_activity_summary"),
            feedback_summary=self._select_first("dashboard_feedback_summary"),
            popular_topics=self._select_many("dashboard_popular_topics", "query_count.desc", 10),
            evidence_usage=self._select_many("dashboard_evidence_usage", "evidence_usage_count.desc", 10),
            lecture_usage=self._select_many("dashboard_lecture_usage", "evidence_usage_count.desc", 10),
        )

    def _select_first(self, table: str) -> dict[str, Any]:
        # Reads a single summary row from a view, returning {} when empty so callers avoid None checks.
        data = self._request("GET", f"/rest/v1/{table}?select=*&limit=1")
        return data[0] if data else {}

    def _select_many(self, table: str, order: str, limit: int) -> list[dict[str, Any]]:
        # Reads an ordered, limited slice of a view so each dashboard section gets its top-N rows.
        return self._request("GET", f"/rest/v1/{table}?select=*&order={order}&limit={limit}")

    # --- HTTP -----------------------------------------------------------
    def _request(
        self,
        method: str,
        path: str,
        *,
        json: Any | None = None,
        prefer: str | None = None,
    ) -> Any:
        return self._postgrest.request(method, path, json=json, prefer=prefer)


@lru_cache
def get_supabase_service() -> SupabaseService:
    # Provides a cached singleton service as a FastAPI dependency so the pooled client is shared across requests.
    return SupabaseService(get_settings())
