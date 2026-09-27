"""Shared CSV database / embedding-JSON loading used across the batch pipeline scripts.

Single source of truth for what used to be several near-identical load_database /
load_embeddings implementations across qdrant_db.py, quiz_discussion_qdrant.py,
visual_asset_qdrant.py, embeddings.py, quiz_discussion_embedding.py, and validation.py.
"""
import json

import pandas as pd

from src.config import PROCESSED_DIR

DATABASE_DIR = PROCESSED_DIR / "databases"
EMBEDDING_DIR = PROCESSED_DIR / "embeddings"


def load_database(
    database_name: str,
    *,
    required_columns: set[str] | None = None,
    expected_count: int | None = None,
    require_lecture_id: bool = False,
) -> pd.DataFrame:
    """Load a database CSV with the standard record_id integrity checks.

    Always checks: file exists, not empty, record_id present (no nulls), record_id
    unique. `required_columns`, `expected_count`, and `require_lecture_id` opt into
    the additional checks some callers previously ran ad hoc.
    """

    database_path = DATABASE_DIR / f"{database_name}.csv"

    if not database_path.exists():
        raise FileNotFoundError(f"Database file not found: {database_path}")

    database_df = pd.read_csv(database_path)

    if database_df.empty:
        raise ValueError(f"Database is empty: {database_name}")

    if required_columns:
        missing_columns = required_columns - set(database_df.columns)
        if missing_columns:
            raise ValueError(f"Missing columns in {database_name} database: {missing_columns}")

    if expected_count is not None and len(database_df) != expected_count:
        raise ValueError(
            f"Expected {expected_count} records in {database_name} database, found {len(database_df)}"
        )

    if database_df['record_id'].isna().any():
        raise ValueError(f"Missing record_id in {database_name} database")

    if database_df['record_id'].duplicated().any():
        raise ValueError(f"Duplicate record_id in {database_name} database")

    if require_lecture_id and database_df['lecture_id'].isna().any():
        raise ValueError(f"Missing lecture_id in {database_name} database")

    return database_df

def load_embeddings(database_name: str, expected_count: int | None = None) -> list[dict]:

    embedding_path = EMBEDDING_DIR / f"{database_name}_embeddings.json"

    if not embedding_path.exists():
        raise FileNotFoundError(f"Embedding file not found: {embedding_path}")

    with open(embedding_path, 'r', encoding='utf-8') as file:
        embedding_records = json.load(file)

    if expected_count is not None and len(embedding_records) != expected_count:
        raise ValueError(
            f"Expected {expected_count} records in {database_name} database, found {len(embedding_records)}"
        )

    return embedding_records
