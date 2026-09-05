"""Supabase (PostgREST) persistence for the human-in-the-loop RAG pipeline."""
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

from fastapi import HTTPException
import httpx

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.schemas import (
    ConversationCreateRequest,
    ConversationResponse,
    CurateRecommendationRequest,
    CurateRecommendationResponse,
    DashboardSummaryResponse,
    EvidenceSaveItem,
    FeedbackCreateRequest,
    FeedbackResponse,
    InteractionSaveRequest,
    InteractionSaveResponse,
    ReviewFeedbackRequest,
)


logger = get_logger(__name__)


class SupabaseService:
    def __init__(self, settings: Settings) -> None:
        # Sets up a single pooled HTTP client (only when configured) so PostgREST calls reuse one keep-alive connection.
        self.settings = settings
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
        # Persists a query + its generated answer + evidence as one unit, rolling back the query if a later write fails.
        query_id: str | None = None
        try:
            query = self._request(
                "POST",
                "/rest/v1/user_queries",
                json={
                    "conversation_id": request.conversation_id,
                    "query_text": request.query_text,
                    "normalized_topic": request.normalized_topic,
                    "detected_intent": request.detected_intent,
                    "metadata": request.metadata or {},
                },
                prefer="return=representation",
            )[0]
            query_id = query["query_id"]

            response = self._request(
                "POST",
                "/rest/v1/generated_responses",
                json={
                    "query_id": query_id,
                    "generated_answer": request.generated_answer,
                    "model_name": request.model_name,
                    "model_provider": request.model_provider,
                    "prompt_version": request.prompt_version,
                    "response_status": "completed",
                    "latency_ms": request.latency_ms,
                    "input_token_count": request.input_token_count,
                    "metadata": request.metadata or {},
                },
                prefer="return=representation",
            )[0]
            response_id = response["response_id"]

            evidence_records: list[dict[str, Any]] = []
            seen_qdrant_ids: set[str] = set()
            for rank, item in enumerate(request.evidence, start=1):
                payload = _evidence_payload(item, response_id, rank)
                if payload["qdrant_record_id"] in seen_qdrant_ids:
                    continue
                seen_qdrant_ids.add(payload["qdrant_record_id"])
                evidence_records.append(payload)
            if evidence_records:
                self._request(
                    "POST",
                    "/rest/v1/retrieval_evidence",
                    json=evidence_records,
                    prefer="return=minimal",
                )

            self._request(
                "PATCH",
                f"/rest/v1/conversations?conversation_id=eq.{request.conversation_id}",
                json={"last_activity_at": datetime.now(timezone.utc).isoformat()},
                prefer="return=minimal",
            )

            return InteractionSaveResponse(
                conversation_id=request.conversation_id,
                query_id=query_id,
                response_id=response_id,
                evidence_count=len(evidence_records),
            )
        except Exception:
            if query_id:
                # Best-effort rollback of the orphaned query row.
                self._request(
                    "DELETE",
                    f"/rest/v1/user_queries?query_id=eq.{query_id}",
                    prefer="return=minimal",
                )
            raise

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
        # Returns paginated recommendations with their source response/query/evidence so the UI can show full context.
        return self._request(
            "GET",
            "/rest/v1/recommendations?select=*,generated_responses(query_id,generated_answer,"
            "response_status,user_queries(query_text),retrieval_evidence(qdrant_record_id,"
            "content_type,evidence_text,similarity_score,retrieval_rank))"
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
        # Centralizes every PostgREST call so pooling, timeouts, logging, and error sanitization happen in one place.
        if not self.enabled or self._client is None:
            raise HTTPException(status_code=503, detail="Supabase is not configured.")

        headers = {"Prefer": prefer} if prefer else None
        try:
            response = self._client.request(method, path, headers=headers, json=json)
        except httpx.HTTPError as exc:
            logger.error("Supabase request failed (%s %s): %s", method, path, exc)
            raise HTTPException(status_code=502, detail="Persistence backend is unreachable.") from exc

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
                detail="Persistence backend rejected the request.",
            )

        if not response.content:
            return None
        return response.json()


def _evidence_payload(item: EvidenceSaveItem, response_id: str, rank: int) -> dict[str, Any]:
    # Maps an evidence item to a retrieval_evidence row (resolving id/score/text aliases) so inserts match the schema.
    qdrant_record_id = item.qdrant_record_id or item.point_id
    if not qdrant_record_id:
        raise HTTPException(status_code=422, detail="Evidence item needs a Qdrant ID.")

    return {
        "response_id": response_id,
        "qdrant_record_id": qdrant_record_id,
        "content_type": item.content_type,
        "lecture_id": item.lecture_id,
        "module_id": item.module_id,
        "similarity_score": item.similarity_score
        if item.similarity_score is not None
        else item.score,
        "retrieval_rank": item.retrieval_rank or rank,
        "evidence_text": item.evidence_text or item.text,
        "asset_path": item.asset_path,
        "timestamp_seconds": item.timestamp_seconds,
        "metadata": item.metadata or {},
    }


@lru_cache
def get_supabase_service() -> SupabaseService:
    # Provides a cached singleton service as a FastAPI dependency so the pooled client is shared across requests.
    return SupabaseService(get_settings())
