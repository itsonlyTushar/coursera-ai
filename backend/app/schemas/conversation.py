from typing import Any

from pydantic import BaseModel, Field


class ConversationCreateRequest(BaseModel):
    session_id: str = Field(..., min_length=1)
    title: str | None = None
    user_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConversationResponse(BaseModel):
    conversation_id: str
    session_id: str | None = None
    title: str | None = None
    user_id: str | None = None
    started_at: str | None = None
    last_activity_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceSaveItem(BaseModel):
    qdrant_record_id: str | None = None
    point_id: str | None = None
    content_type: str
    lecture_id: str | None = None
    module_id: str | None = None
    similarity_score: float | None = None
    score: float | None = None
    retrieval_rank: int | None = None
    evidence_text: str | None = None
    text: str | None = None
    asset_path: str | None = None
    timestamp_seconds: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class InteractionSaveRequest(BaseModel):
    conversation_id: str
    query_text: str = Field(..., min_length=1)
    generated_answer: str = Field(..., min_length=1)
    normalized_topic: str | None = None
    detected_intent: str | None = None
    model_name: str | None = None
    model_provider: str | None = None
    prompt_version: str | None = None
    latency_ms: int | None = Field(default=None, ge=0)
    input_token_count: int | None = Field(default=None, ge=0)
    evidence: list[EvidenceSaveItem] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class InteractionSaveResponse(BaseModel):
    conversation_id: str
    query_id: str
    response_id: str
    evidence_count: int


class FeedbackCreateRequest(BaseModel):
    response_id: str
    user_id: str | None = None
    rating: int | None = Field(default=None, ge=1, le=5)
    is_helpful: bool | None = None
    approval: str | None = "pending"
    feedback_text: str | None = None


class FeedbackResponse(BaseModel):
    feedback_id: str
    response_id: str
    rating: int | None = None
    is_helpful: bool | None = None
    approval: str | None = None
