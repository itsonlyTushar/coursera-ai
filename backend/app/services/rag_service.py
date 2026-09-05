"""Bridges the standalone ``rag`` retrieval/synthesis pipeline into the API."""
from functools import lru_cache
import os
from pathlib import Path
import sys
from typing import Any

from fastapi import HTTPException

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.schemas import (
    Citation,
    EvidenceContext,
    EvidenceSaveItem,
    SynthesizeRequest,
    SynthesizeResponse,
)


logger = get_logger(__name__)

# retrieval_evidence.content_type has a DB CHECK constraint limited to this set,
# so any other modality must be normalized before it is persisted.
_ALLOWED_CONTENT_TYPES = {"caption", "slide", "frame", "transcript", "quiz", "discussion"}


class RagService:
    def __init__(self, settings: Settings) -> None:
        # Stores config and lazy pipeline handles so the heavy rag imports load only on first use.
        self.settings = settings
        self.backend_root = Path(__file__).resolve().parents[2]
        self._pipeline: Any = None
        self._synthesize_insight: Any = None

    def synthesize(
        self, request: SynthesizeRequest
    ) -> tuple[SynthesizeResponse, list[EvidenceSaveItem], str]:
        # Runs retrieval + LLM synthesis and shapes the result for the API and for persistence in one pass.
        chunks = (
            [self._context_to_chunk(item) for item in request.retrieved_evidence]
            if request.retrieved_evidence
            else self.retrieve_chunks(query=request.query, top_k=request.top_k)
        )

        synthesize_insight = self._load_synthesis()
        try:
            insight = synthesize_insight(query=request.query, reranked_chunks=chunks)
        except Exception as exc:
            logger.error("RAG synthesis failed: %s", exc)
            raise HTTPException(status_code=503, detail="RAG synthesis failed.") from exc

        answer_text = (
            f"Summary: {insight.summary}\n\n"
            f"Friction Diagnostic:\n{insight.friction_explanation}\n\n"
            f"Recommended Action:\n{insight.recommended_action}"
        )
        citations = [
            Citation(
                point_id=item.segment_id,
                content_type=item.modality,
                lecture_id=item.source_id,
                score=item.confidence,
                text_preview=_preview(item.excerpt, 180),
            )
            for item in insight.evidence
        ]
        context_items = [self._chunk_to_context(chunk) for chunk in chunks]
        evidence = [
            self._context_to_evidence(item, rank)
            for rank, item in enumerate(context_items, start=1)
        ]

        response = SynthesizeResponse(
            insight_id=insight.insight_id,
            conversation_id="",
            query_id="",
            answer_text=answer_text,
            recommended_action=insight.recommended_action,
            citations=citations,
            confidence=round(float(insight.confidence), 3),
            status="completed",
        )
        return response, evidence, answer_text

    def retrieve_chunks(self, query: str, top_k: int) -> list[dict[str, Any]]:
        # Runs dense retrieval + rerank via the rag pipeline, converting pipeline failures into HTTP 503s.
        pipeline = self._load_pipeline()
        try:
            return pipeline.retrieve_and_rerank(query=query, top_k=top_k)
        except Exception as exc:
            logger.error("RAG retrieval failed: %s", exc)
            raise HTTPException(status_code=503, detail="RAG retrieval failed.") from exc

    # --- Lazy imports of the standalone rag package ---------------------
    def _load_pipeline(self) -> Any:
        # Imports and caches the retrieval pipeline on first use so startup stays fast and import errors surface as 503.
        if self._pipeline is not None:
            return self._pipeline

        self._prepare_rag_imports()
        try:
            from rag.retreival import pipeline
        except Exception as exc:
            logger.error("Could not import rag retrieval pipeline: %s", exc)
            raise HTTPException(status_code=503, detail="Retrieval pipeline unavailable.") from exc

        self._pipeline = pipeline
        return self._pipeline

    def _load_synthesis(self) -> Any:
        # Imports and caches the synthesis function (after checking the LLM key) so misconfig fails clearly.
        self._assert_env("GROQ_API_KEY", "RAG LLM synthesis")
        if self._synthesize_insight is not None:
            return self._synthesize_insight

        self._prepare_rag_imports()
        try:
            from rag.synthesis import synthesize_insight
        except Exception as exc:
            logger.error("Could not import rag synthesis: %s", exc)
            raise HTTPException(status_code=503, detail="Synthesis pipeline unavailable.") from exc

        self._synthesize_insight = synthesize_insight
        return self._synthesize_insight

    def _prepare_rag_imports(self) -> None:
        # Ensures the backend root is importable so ``import rag.*`` works regardless of the launch directory.
        if str(self.backend_root) not in sys.path:
            sys.path.insert(0, str(self.backend_root))

    def _assert_env(self, name: str, purpose: str) -> None:
        # Fails fast with a clear message when a required credential is missing, instead of erroring deep in a call.
        if not os.getenv(name):
            raise HTTPException(
                status_code=503,
                detail=f"{name} is required for {purpose}. Add it to backend/.env.",
            )

    # --- Shape mapping --------------------------------------------------
    def _chunk_to_context(self, chunk: dict[str, Any]) -> EvidenceContext:
        # Converts a raw pipeline chunk into the API's EvidenceContext so responses have a stable schema.
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

    def _context_to_chunk(self, item: EvidenceContext) -> dict[str, Any]:
        # Converts client-supplied evidence back into a pipeline chunk so synthesis can reuse pre-fetched context.
        return {
            "segment_id": item.point_id,
            "source_id": item.source_id or item.asset_id or item.lecture_id or item.point_id,
            "modality": item.content_type or "text",
            "timestamp": item.timestamp or "",
            "excerpt": item.text,
            "score": item.score or 0.0,
        }

    def _context_to_evidence(self, item: EvidenceContext, rank: int) -> EvidenceSaveItem:
        # Maps evidence into the persistence shape (with rank) so it can be stored against the generated response.
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
    # Collapses whitespace and truncates text so citation previews stay short and single-line.
    text = " ".join((value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _optional_str(value: Any) -> str | None:
    # Stringifies a value while preserving None so optional fields don't become the literal "None".
    return None if value is None else str(value)


def _content_type(value: Any) -> str:
    # Coerces any modality to a DB-allowed content_type so persistence never violates the CHECK constraint.
    content_type = str(value) if value is not None else ""
    return content_type if content_type in _ALLOWED_CONTENT_TYPES else "caption"


def _timestamp_seconds(payload: dict[str, Any]) -> float | None:
    # Extracts a numeric timestamp from payload variants so evidence carries a usable start time when available.
    value = payload.get("timestamp_seconds") or payload.get("start_seconds")
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


@lru_cache
def get_rag_service() -> RagService:
    # Provides a cached singleton service as a FastAPI dependency so pipelines load once per process.
    return RagService(get_settings())
