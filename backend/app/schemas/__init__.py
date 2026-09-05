"""Pydantic request/response schemas, grouped by domain.

Re-exported here so callers can use ``from app.schemas import X`` regardless of
which module a schema lives in.
"""
from app.schemas.conversation import (
    ConversationCreateRequest,
    ConversationResponse,
    EvidenceSaveItem,
    FeedbackCreateRequest,
    FeedbackResponse,
    InteractionSaveRequest,
    InteractionSaveResponse,
)
from app.schemas.dashboard import (
    CollectionResponse,
    DashboardSummaryResponse,
    MetricsResponse,
)
from app.schemas.health import HealthResponse
from app.schemas.rag import (
    Citation,
    CurateRecommendationRequest,
    CurateRecommendationResponse,
    EvidenceContext,
    ReviewFeedbackRequest,
    SynthesizeRequest,
    SynthesizeResponse,
)


__all__ = [
    "ConversationCreateRequest",
    "ConversationResponse",
    "EvidenceSaveItem",
    "FeedbackCreateRequest",
    "FeedbackResponse",
    "InteractionSaveRequest",
    "InteractionSaveResponse",
    "CollectionResponse",
    "DashboardSummaryResponse",
    "MetricsResponse",
    "HealthResponse",
    "Citation",
    "CurateRecommendationRequest",
    "CurateRecommendationResponse",
    "EvidenceContext",
    "ReviewFeedbackRequest",
    "SynthesizeRequest",
    "SynthesizeResponse",
]
