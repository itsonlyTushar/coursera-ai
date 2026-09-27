"""Conversions between RAG pipeline chunks and API persistence schemas."""
from typing import Any

from app.schemas import EvidenceContext, EvidenceSaveItem


_ALLOWED_CONTENT_TYPES = {"caption", "slide", "frame", "transcript", "quiz", "discussion"}


def _chunk_to_context(chunk: dict[str, Any]) -> EvidenceContext:
    source_id = _optional_str(chunk.get("source_id"))
    content_type = _content_type(chunk.get("modality"))
    return EvidenceContext(
        point_id=str(chunk.get("segment_id", "")),
        score=float(chunk.get("score", 0.0)),
        source_id=source_id,
        asset_id=source_id,
        content_type=content_type,
        lecture_id=source_id,
        timestamp=_optional_str(chunk.get("timestamp")),
        text=str(chunk.get("excerpt", "")),
        payload={
            "source_id": chunk.get("source_id"),
            "content_type": content_type,
            "timestamp": chunk.get("timestamp"),
        },
    )


def _context_to_chunk(item: EvidenceContext) -> dict[str, Any]:
    return {
        "segment_id": item.point_id,
        "source_id": item.source_id or item.asset_id or item.lecture_id or item.point_id,
        "modality": item.content_type or "text",
        "timestamp": item.timestamp or "",
        "excerpt": item.text,
        "score": item.score or 0.0,
    }


def _context_to_evidence(item: EvidenceContext, rank: int) -> EvidenceSaveItem:
    payload = item.payload or {}
    return EvidenceSaveItem(
        point_id=item.point_id,
        content_type=_content_type(item.content_type),
        lecture_id=item.lecture_id,
        module_id=_optional_str(payload.get("module_id")),
        score=item.score,
        retrieval_rank=rank,
        text=item.text,
        asset_path=_optional_str(payload.get("asset_path")),
        timestamp_seconds=_timestamp_seconds(payload),
        metadata={
            "source_id": item.source_id,
            "asset_id": item.asset_id,
            "course_id": item.course_id,
            "provider": "rag",
        },
    )


def _preview(value: str, limit: int) -> str:
    text = " ".join((value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _optional_str(value: Any) -> str | None:
    return None if value is None else str(value)


def _content_type(value: Any) -> str:
    content_type = str(value) if value is not None else ""
    return content_type if content_type in _ALLOWED_CONTENT_TYPES else "caption"


def _timestamp_seconds(payload: dict[str, Any]) -> float | None:
    value = payload.get("timestamp_seconds") or payload.get("start_seconds")
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None