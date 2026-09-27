"""Persistence workflow for generated responses and their retrieved evidence."""
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException

from app.schemas import (
    EvidenceSaveItem,
    InteractionSaveRequest,
    InteractionSaveResponse,
)
from app.integrations.supabase.postgrest_client import PostgrestClient


class SupabaseInteractionService:
    def __init__(self, client: PostgrestClient) -> None:
        self.client = client

    def save_interaction(self, request: InteractionSaveRequest) -> InteractionSaveResponse:
        query_id: str | None = None
        try:
            query = self.client.request(
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

            response = self.client.request(
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
                self.client.request(
                    "POST",
                    "/rest/v1/retrieval_evidence",
                    json=evidence_records,
                    prefer="return=minimal",
                )

            self.client.request(
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
                self.client.request(
                    "DELETE",
                    f"/rest/v1/user_queries?query_id=eq.{query_id}",
                    prefer="return=minimal",
                )
            raise


def _evidence_payload(item: EvidenceSaveItem, response_id: str, rank: int) -> dict[str, Any]:
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