"""Shared Qdrant client/point/payload helpers used across the batch pipeline scripts.

Single source of truth for what used to be copy-pasted (with drifting constants)
across qdrant_db.py, quiz_discussion_qdrant.py, and visual_asset_qdrant.py.
"""
import ast
import os
import uuid
from typing import Any

import pandas as pd
from dotenv import load_dotenv
from qdrant_client import QdrantClient

from src.config import EMBEDDING_DIMENSIONS, EMBEDDING_MODEL, PROJECT_ROOT

# Loaded before any os.getenv() calls below, so QDRANT_COLLECTION etc. actually resolve
# from backend/.env instead of always falling back to the hardcoded default.
load_dotenv(PROJECT_ROOT / ".env")

COLLECTION_NAME = os.getenv("QDRANT_COLLECTION", "COURSEERA_ALMAX_MULTIMODAL")
QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")

# The embedding model/dimensions are project-wide constants owned by src.config;
# re-exported here so Qdrant-facing modules have one place to import them from.
MODEL_NAME = EMBEDDING_MODEL
VECTOR_DIMENSIONS = EMBEDDING_DIMENSIONS


def create_client() -> QdrantClient:

    if not QDRANT_URL:
        raise ValueError("QDRANT_URL is missing from environment (.env)")

    if not QDRANT_API_KEY:
        raise ValueError("QDRANT_API_KEY is missing from environment (.env)")

    return QdrantClient(url=QDRANT_URL,
                        api_key=QDRANT_API_KEY,
                        timeout=120)

def create_point_id(record_id: str) -> str:

    return str(uuid.uuid5(uuid.NAMESPACE_URL, record_id))

def parse_serialized_value(value: Any) -> Any:

    if value is None:
        return None

    if isinstance(value, (list, dict)):
        return value

    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass

    if not isinstance(value, str):
        return value

    value = value.strip()

    if not value:
        return None

    if value.startswith(('[', '{')):
        try:
            return ast.literal_eval(value)
        except (SyntaxError, ValueError):
            return value

    return value


def clean_payload_value(value: Any) -> Any:

    if value is None:
        return None

    if isinstance(value, dict):
        return {
            str(key): clean_payload_value(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple)):
        return [
            clean_payload_value(item)
            for item in value
        ]

    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass

    if isinstance(value, (bool, int, float, str)):
        return value

    if hasattr(value, "item"):
        return value.item()

    return str(value).strip()
