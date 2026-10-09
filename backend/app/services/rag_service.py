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
    ConversationCreateRequest,
    EvidenceSaveItem,
    InteractionSaveRequest,
    SynthesizeRequest,
    SynthesizeResponse,
)
from app.services.rag_mapping import (
    _chunk_to_context,
    _context_to_chunk,
    _context_to_evidence,
    _preview,
)
from app.services.supabase_service import SupabaseService


logger = get_logger(__name__)

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
            [_context_to_chunk(item) for item in request.retrieved_evidence]
            if request.retrieved_evidence
            else self.retrieve_chunks(query=request.query, top_k=request.top_k)
        )

        synthesize_insight = self._load_synthesis()
        try:
            insight = synthesize_insight(query=request.query, reranked_chunks=chunks)
        except Exception as exc:
            logger.error("RAG synthesis failed: %s", exc)
            raise HTTPException(status_code=503, detail=f"RAG synthesis failed: {exc}") from exc

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
        context_items = [_chunk_to_context(chunk) for chunk in chunks]
        evidence = [
            _context_to_evidence(item, rank)
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

    def synthesize_and_record(
        self, request: SynthesizeRequest, supabase_service: SupabaseService
    ) -> SynthesizeResponse:
        # Orchestrates the full /synthesize flow: run the RAG pipeline, then persist the
        # query/answer/evidence (creating a conversation if none was supplied). This keeps
        # the HTTP route thin, doing only validation and dependency injection.
        response, evidence, answer_text = self.synthesize(request)

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
                    "retrieval_provider": "rag.retrieval",
                    "synthesis_provider": "rag.synthesis",
                },
            )
        )

        response.insight_id = saved.response_id
        response.conversation_id = saved.conversation_id
        response.query_id = saved.query_id
        return response

    def retrieve_chunks(self, query: str, top_k: int) -> list[dict[str, Any]]:
        # Runs dense retrieval + rerank via the rag pipeline, converting pipeline failures into HTTP 503s.
        pipeline = self._load_pipeline()
        try:
            return pipeline.retrieve_and_rerank(query=query, top_k=top_k)
        except Exception as exc:
            logger.error("RAG retrieval failed: %s", exc)
            raise HTTPException(status_code=503, detail=f"RAG retrieval failed: {exc}") from exc

    # --- Lazy imports of the standalone rag package ---------------------
    def _load_pipeline(self) -> Any:
        # Imports and caches the retrieval pipeline on first use so startup stays fast and import errors surface as 503.
        if self._pipeline is not None:
            return self._pipeline

        self._prepare_rag_imports()
        self._assert_env("QDRANT_URL", "Qdrant vector store")
        if not (os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACEHUB_API_TOKEN")):
            raise HTTPException(
                status_code=503,
                detail="HF_TOKEN is required for RAG embeddings. Add it to backend/.env.",
            )
        try:
            from rag.retrieval import pipeline
        except Exception as exc:
            logger.error("Could not import rag retrieval pipeline: %s", exc)
            raise HTTPException(status_code=503, detail=f"Retrieval pipeline unavailable: {exc}") from exc

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
            raise HTTPException(status_code=503, detail=f"Synthesis pipeline unavailable: {exc}") from exc

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

@lru_cache
def get_rag_service() -> RagService:
    # Provides a cached singleton service as a FastAPI dependency so pipelines load once per process.
    return RagService(get_settings())
