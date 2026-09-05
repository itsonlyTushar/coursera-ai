from typing import Any

from pydantic import BaseModel, Field


class EvidenceContext(BaseModel):
    point_id: str
    score: float | None = None
    source_id: str | None = None
    asset_id: str | None = None
    content_type: str | None = None
    course_id: str | None = None
    lecture_id: str | None = None
    timestamp: str | None = None
    text: str
    payload: dict[str, Any] = Field(default_factory=dict)


class Citation(BaseModel):
    point_id: str
    content_type: str | None = None
    lecture_id: str | None = None
    score: float | None = None
    text_preview: str = ""


class SynthesizeRequest(BaseModel):
    query: str = Field(..., min_length=1)
    conversation_id: str | None = None
    session_id: str | None = None
    retrieved_evidence: list[EvidenceContext] = Field(default_factory=list)
    top_k: int = Field(default=5, ge=1, le=25)
    filters: dict[str, Any] = Field(default_factory=dict)
    model_name: str | None = "rag.synthesis"
    model_provider: str | None = "groq"
    metadata: dict[str, Any] = Field(default_factory=dict)


class SynthesizeResponse(BaseModel):
    insight_id: str
    conversation_id: str
    query_id: str
    answer_text: str
    recommended_action: str | None = None
    citations: list[Citation]
    confidence: float
    status: str = "pending_review"


class ReviewFeedbackRequest(BaseModel):
    insight_id: str | None = None
    response_id: str | None = None
    decision: str = Field(default="pending")
    notes: str | None = None
    rating: int | None = Field(default=None, ge=1, le=5)
    is_helpful: bool | None = None
    user_id: str | None = None


class CurateRecommendationRequest(BaseModel):
    insight_id: str
    title: str = Field(..., min_length=1)
    category: str = "content_review"
    recommendation_text: str
    priority: int = 1
    metadata: dict[str, Any] = Field(default_factory=dict)


class CurateRecommendationResponse(BaseModel):
    recommendation_id: str
    insight_id: str
    status: str = "curated"
    message: str = "Recommendation added to curation list successfully"
