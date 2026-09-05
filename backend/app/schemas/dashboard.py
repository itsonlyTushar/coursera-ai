from typing import Any

from pydantic import BaseModel, Field


class CollectionResponse(BaseModel):
    """Qdrant collection status (used internally to build metrics)."""

    collection_name: str
    status: str | None = None
    vectors_count: int | None = None
    points_count: int | None = None
    indexed_vectors_count: int | None = None
    config: dict[str, Any] = Field(default_factory=dict)


class MetricsResponse(BaseModel):
    collection_name: str
    qdrant_status: str | None = None
    points_count: int | None = None
    scanned_records: int
    content_type_counts: dict[str, int] = Field(default_factory=dict)
    course_id_counts: dict[str, int] = Field(default_factory=dict)
    embedding_model_counts: dict[str, int] = Field(default_factory=dict)


class DashboardSummaryResponse(BaseModel):
    activity_summary: dict[str, Any] = Field(default_factory=dict)
    popular_topics: list[dict[str, Any]] = Field(default_factory=list)
    evidence_usage: list[dict[str, Any]] = Field(default_factory=list)
    lecture_usage: list[dict[str, Any]] = Field(default_factory=list)
    feedback_summary: dict[str, Any] = Field(default_factory=dict)
