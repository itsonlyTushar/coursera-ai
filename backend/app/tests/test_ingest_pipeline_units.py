"""Unit tests for the pure, credential-free parts of the online ingestion pipeline
(database/src/ingest_service.py) — lecture-id slugging and plain-text chunking for
transcript/discussion assets. No Gemini/Qdrant/HF calls involved.
"""
import sys
from pathlib import Path

import pytest

DATABASE_DIR = Path(__file__).resolve().parents[2] / "database"
if str(DATABASE_DIR) not in sys.path:
    sys.path.insert(0, str(DATABASE_DIR))

# ingest_service imports the (optional, ingestion-only) langchain-huggingface stack at
# module level, so skip this whole file on a dev/test env that only has the base
# requirements installed — matches the project's convention of not requiring ML deps
# to run the test suite.
try:
    from src.ingest_service import (
        _build_text_records,
        _chunk_plain_text,
        _slugify_lecture_id,
    )
except ModuleNotFoundError as exc:
    pytest.skip(
        f"skipping ingestion pipeline unit tests: {exc} (install requirements.txt to run these)",
        allow_module_level=True,
    )


# Asserts numbered lecture ids still normalize the existing way (lec2 -> lec02).
def test_slugify_numbered_lecture_id():
    assert _slugify_lecture_id("lec2") == "lec02"
    assert _slugify_lecture_id("lecture_09") == "lec09"


# Asserts named units (no digits) become a clean, safe slug instead of raising.
def test_slugify_named_unit():
    assert _slugify_lecture_id("readings") == "readings"
    assert _slugify_lecture_id("Course Syllabus!") == "course-syllabus"


# Asserts a fully invalid value (empty after slugging) still raises.
def test_slugify_rejects_empty():
    with pytest.raises(ValueError):
        _slugify_lecture_id("---")


# Asserts short text becomes exactly one chunk, and long text splits into multiple.
def test_chunk_plain_text():
    assert _chunk_plain_text("just a few words") == ["just a few words"]

    long_text = " ".join(f"word{i}" for i in range(500))
    chunks = _chunk_plain_text(long_text, target_words=220)
    assert len(chunks) == 3
    assert sum(len(c.split()) for c in chunks) == 500


# Asserts empty text produces no records at all (nothing to embed).
def test_chunk_plain_text_empty():
    assert _chunk_plain_text("") == []


# Asserts transcript/discussion records get a distinct, deterministic id per chunk and
# carry the requested content_type, course_id, and lecture_id.
def test_build_text_records():
    records = _build_text_records("alpha beta gamma", "readings", "bio-101", "discussion")

    assert len(records) == 1
    record = records[0]
    assert record["content_type"] == "discussion"
    assert record["course_id"] == "bio-101"
    assert record["lecture_id"] == "readings"
    assert record["record_id"] == "DISCUSSION_READINGS_001"
    assert record["_embedding_text"] == "alpha beta gamma"


# Asserts no text produces no records (nothing to embed, nothing upserted).
def test_build_text_records_empty_text():
    assert _build_text_records("", "lec01", "bio-101", "transcript") == []


# Asserts a quiz question set and its solutions share content_type="quiz" but get distinct,
# non-colliding record ids (via id_prefix) and a role tag distinguishing question vs. solution.
def test_build_text_records_quiz_question_and_solution_dont_collide():
    question = _build_text_records(
        "What is X?", "exam-1", "bio-101", "quiz", id_prefix="QUIZ", role="question"
    )
    solution = _build_text_records(
        "X is Y.", "exam-1", "bio-101", "quiz", id_prefix="QUIZSOLUTION", role="solution"
    )

    assert question[0]["content_type"] == "quiz"
    assert solution[0]["content_type"] == "quiz"
    assert question[0]["role"] == "question"
    assert solution[0]["role"] == "solution"
    assert question[0]["record_id"] != solution[0]["record_id"]
    assert question[0]["record_id"] == "QUIZ_EXAM-1_001"
    assert solution[0]["record_id"] == "QUIZSOLUTION_EXAM-1_001"


# Asserts transcript/discussion records are unaffected by the new id_prefix/role params
# (both default to producing the exact same shape as before).
def test_build_text_records_backward_compatible_without_role():
    records = _build_text_records("hello world", "lec01", "bio-101", "transcript")

    assert "role" not in records[0]
    assert records[0]["record_id"] == "TRANSCRIPT_LEC01_001"
