"""API-based text embeddings for the ingestion pipeline.

Replaces the heavy local ``sentence-transformers`` model with the Hugging Face
Inference API. This is the SAME model + client the backend uses for query
embeddings (``HuggingFaceEndpointEmbeddings`` on ``BAAI/bge-base-en-v1.5``), so
document vectors produced here stay directly comparable to backend query vectors
in Qdrant's cosine space — no local model download, no torch, works on any
machine with an ``HF_TOKEN``.
"""
import os
import time

import numpy as np
from dotenv import load_dotenv
from langchain_huggingface import HuggingFaceEndpointEmbeddings

from src.config import (
    API_RETRY_DELAY,
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
    MAX_API_RETRIES,
    PROJECT_ROOT,
)


load_dotenv(PROJECT_ROOT / ".env")

# Reuse whichever HF token is configured (the pipeline already needs one for the
# private visual dataset). HF_TOKEN_EMBEDDING mirrors the backend's naming.
_HF_TOKEN = (
    os.getenv("HF_TOKEN")
    or os.getenv("HF_TOKEN_EMBEDDING")
    or os.getenv("HUGGINGFACEHUB_API_TOKEN")
)

# Texts per Inference API request. One-time ingestion, so keep batches modest.
DEFAULT_BATCH_SIZE = 32

_embedder: HuggingFaceEndpointEmbeddings | None = None


def _get_embedder() -> HuggingFaceEndpointEmbeddings:
    # Lazily builds the HF Inference embedder so importing this module never blocks or fails without a token.
    global _embedder
    if _embedder is None:
        if not _HF_TOKEN:
            raise ValueError(
                "HF_TOKEN is required for API-based embeddings. Add it to database/.env."
            )
        _embedder = HuggingFaceEndpointEmbeddings(
            model=EMBEDDING_MODEL,
            huggingfacehub_api_token=_HF_TOKEN,
        )
    return _embedder


def _l2_normalize(vectors: list[list[float]]) -> np.ndarray:
    # L2-normalizes rows so new vectors match the existing corpus's unit norm (cosine ranking is unchanged either way).
    array = np.asarray(vectors, dtype=np.float32)
    norms = np.linalg.norm(array, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return array / norms


def embed_texts(texts: list[str], batch_size: int = DEFAULT_BATCH_SIZE) -> np.ndarray:
    # Embeds a list of texts via the HF Inference API in retried batches so a whole database can be encoded in one call.
    if not texts:
        return np.empty((0, EMBEDDING_DIMENSIONS), dtype=np.float32)

    embedder = _get_embedder()
    collected: list[list[float]] = []

    for batch_start in range(0, len(texts), batch_size):
        batch = texts[batch_start : batch_start + batch_size]
        vectors: list[list[float]] | None = None
        for attempt in range(1, MAX_API_RETRIES + 1):
            try:
                vectors = embedder.embed_documents(batch)
                break
            except Exception as exc:  # transient API/network errors -> retry
                if attempt == MAX_API_RETRIES:
                    raise RuntimeError(
                        f"Embedding API failed after {MAX_API_RETRIES} attempts: {exc}"
                    ) from exc
                print(f"[embedding_client] attempt {attempt} failed ({exc}); retrying...")
                time.sleep(API_RETRY_DELAY)
        collected.extend(vectors or [])

    normalized = _l2_normalize(collected)
    if normalized.shape[1] != EMBEDDING_DIMENSIONS:
        raise ValueError(
            f"Embedding API returned dimension {normalized.shape[1]}, "
            f"expected {EMBEDDING_DIMENSIONS}."
        )
    return normalized
