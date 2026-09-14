"""Per-lecture online ingestion runner.

The rest of the ``database`` package is a whole-course batch pipeline that scans
fixed folders and aggregates every lecture at once. This module exposes a single
callable that ingests ONE lecture (or lecture-like unit, e.g. "readings" or
"syllabus") from whichever assets were actually provided — extract → Gemini
visual analysis (slides only) → API embeddings → Qdrant upsert — writing only
inside a caller-provided working directory. The backend calls it as a
background job.

It deliberately reuses the granular, path-parameterized building blocks
(extraction sub-functions, ``analyse_image``, ``combine_searchable_fields`` and
the Qdrant helpers) so the points it upserts are identical in id and payload
shape to the batch pipeline's.

Scope: captions (.vtt/.srt), slides (.pdf), transcript (.pdf/.md/.txt),
discussion notes (.md/.txt), and a quiz/exam question set with its solutions
(.pdf/.md/.txt each) — ALL optional, but at least one is required. The
project's purpose is finding where students struggle, which means the full
course surface matters, not just lecture content: not every course ships
slides + synced captions, and exam/assignment questions plus their official
solutions are exactly the kind of evidence (expected answer vs. discussion
confusion) the RAG layer needs. Quiz questions and solutions both use the
``quiz`` content_type (already valid end to end — Qdrant payload, the RAG
service's normalizer, and the Supabase DB constraint) and are distinguished
by a ``role`` payload field ("question"/"solution") rather than a separate
content_type, since the DB only allows a fixed set of values. No video —
video/frame handling is out of scope for the online tool (it stays in the
offline batch pipeline). Slide images are kept on local disk for this job;
uploading them to the private HF visual dataset is a separate step.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable, Optional

import pandas as pd
from qdrant_client.models import PointStruct

from src.config import COURSE_ID, EMBEDDING_MODEL, normalize_lecture_id
from src.embedding_client import embed_texts
from src.extraction import (
    create_caption_chunks,
    extract_slide_text,
    extract_transcript_text,
    extract_vtt_captions,
)
from src.qdrant_db import (
    COLLECTION_NAME,
    clean_payload_value,
    create_point_id,
    create_qdrant_client,
    create_qdrant_collection,
    upload_points,
)
from src.visual_database import combine_searchable_fields


ProgressCallback = Callable[[str, float, str], None]

# Words per chunk for plain-text assets (transcript/discussion) — similar
# granularity to caption chunking so each embedding stays a focused, citable unit.
TEXT_CHUNK_WORDS = 220


def _noop_progress(stage: str, pct: float, message: str) -> None:
    # Default progress sink so callers may omit a callback without extra guards.
    pass


def _slugify_lecture_id(value: str) -> str:
    # Numbered lectures (lec2, lecture_02, ...) normalize to lecNN as before; named
    # units (readings, syllabus, ...) pass through as a clean, safe slug instead of
    # requiring a digit (normalize_lecture_id raises without one).
    if re.search(r"\d", value):
        return normalize_lecture_id(value)
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    if not slug:
        raise ValueError(f"Invalid lecture id: {value!r}")
    return slug


def _read_text_file(path: Path) -> str:
    # Reads a plain-text/markdown asset (discussion notes, a markdown transcript) as UTF-8.
    return Path(path).read_text(encoding="utf-8", errors="ignore")


def _chunk_plain_text(text: str, target_words: int = TEXT_CHUNK_WORDS) -> list[str]:
    # Splits long text into ~target_words chunks so each embedding stays a focused, retrievable unit.
    words = text.split()
    if not words:
        return []
    return [" ".join(words[i : i + target_words]) for i in range(0, len(words), target_words)]


def _extract_plain_text(lecture_id: str, path: Path, extracted_dir: Path) -> str:
    # Extracts full text from any document asset (transcript, quiz question set, quiz
    # solutions): PDFs use the existing page-based extractor (also detects the instructor
    # as a side effect, harmless for non-transcript uses); markdown/text files are read directly.
    path = Path(path)
    if path.suffix.lower() == ".pdf":
        text_df, _instructor = extract_transcript_text(lecture_id, path, extracted_dir)
        return "\n\n".join(text_df["text"].fillna("").astype(str))
    return _read_text_file(path)


def _build_caption_records(
    caption_chunk_df: pd.DataFrame, lecture_id: str, course_id: str
) -> list[dict[str, Any]]:
    # Turns caption chunks into caption records matching build_caption_database so payloads stay consistent.
    slug = lecture_id.upper()
    records: list[dict[str, Any]] = []
    for _, row in caption_chunk_df.iterrows():
        records.append(
            {
                "record_id": row["chunk_id"],
                "chunk_id": row["chunk_id"],
                "asset_id": f"VIDEO_{slug}",
                "course_id": course_id,
                "module_id": f"MOD_{slug}",
                "lecture_id": lecture_id,
                "start_caption_id": int(row["start_caption_id"]),
                "end_caption_id": int(row["end_caption_id"]),
                "start_time": row["start_time"],
                "end_time": row["end_time"],
                "start_seconds": float(row["start_seconds"]),
                "end_seconds": float(row["end_seconds"]),
                "text": row["text"],
                "word_count": int(row["word_count"]),
                "duration_seconds": float(row["duration_seconds"]),
                "content_type": "caption",
                "_embedding_text": str(row["text"] or ""),
            }
        )
    return records


def _build_text_records(
    text: str,
    lecture_id: str,
    course_id: str,
    content_type: str,
    *,
    id_prefix: Optional[str] = None,
    role: Optional[str] = None,
) -> list[dict[str, Any]]:
    # Chunks plain text (transcript, discussion notes, or quiz question/solution text) into
    # records of the given content_type, embedded and upserted exactly like captions/slides —
    # not just extracted and discarded. `id_prefix` lets two asset kinds share one content_type
    # (quiz questions vs. solutions) without colliding record ids; `role` tags which is which.
    slug = lecture_id.upper()
    prefix = (id_prefix or content_type).upper()
    chunks = _chunk_plain_text(text)
    records = []
    for index, chunk in enumerate(chunks, start=1):
        record = {
            "record_id": f"{prefix}_{slug}_{index:03d}",
            "content_type": content_type,
            "course_id": course_id,
            "module_id": f"MOD_{slug}",
            "lecture_id": lecture_id,
            "chunk_index": index,
            "text": chunk,
            "_embedding_text": chunk,
        }
        if role:
            record["role"] = role
        records.append(record)
    return records


def _build_slide_records(
    slide_df: pd.DataFrame,
    slide_image_df: pd.DataFrame,
    lecture_id: str,
    course_id: str,
    progress: ProgressCallback,
) -> list[dict[str, Any]]:
    # Runs Gemini per slide image and assembles slide records matching build_slide_database.
    from src.visual_analysis import analyse_image  # lazy: needs GEMINI_API_KEY

    slug = lecture_id.upper()
    manifest = slide_df.merge(
        slide_image_df, on=["lecture_id", "slide_no"], how="inner", validate="one_to_one"
    )
    total = len(manifest)
    unavailable: set[str] = set()
    records: list[dict[str, Any]] = []

    for position, (_, row) in enumerate(manifest.iterrows(), start=1):
        slide_no = int(row["slide_no"])
        analysis = analyse_image(
            image_path=Path(row["image_file_path"]),
            source_type="slide",
            lecture_id=lecture_id,
            record_label=f"slide {slide_no}",
            unavailable_models=unavailable,
        )
        record = {
            "record_id": f"SLIDE_{slug}_{slide_no:03d}",
            "content_type": "slide",
            "course_id": course_id,
            "module_id": f"MOD_{slug}",
            "lecture_id": lecture_id,
            "slide_no": slide_no,
            "image_file_name": row.get("image_file_name"),
            "image_file_path": row.get("image_file_path"),
            "image_width": row.get("image_width"),
            "image_height": row.get("image_height"),
            "image_size_bytes": row.get("image_size_bytes"),
            "text": row.get("text"),
            "lecture_title": row.get("lecture_title"),
            "lecture_topic": row.get("lecture_topic"),
            **analysis,
        }
        record["searchable_text"] = combine_searchable_fields(pd.Series(record))
        record["_embedding_text"] = record["searchable_text"]
        records.append(record)
        progress("visual_analysis", position / max(total, 1), f"analysed slide {position}/{total}")

    return records


def _to_points(records: list[dict[str, Any]]) -> list[PointStruct]:
    # Embeds each record's text via the API and packs id/vector/payload exactly like the batch uploader.
    # Skip records with no embeddable text (e.g. blank/title slides) so the API never sees empty input.
    usable = [record for record in records if str(record.get("_embedding_text") or "").strip()]
    if not usable:
        return []

    vectors = embed_texts([record["_embedding_text"] for record in usable])
    if len(vectors) != len(usable):
        raise ValueError(f"Embedding count {len(vectors)} != record count {len(usable)}")

    points: list[PointStruct] = []
    for record, vector in zip(usable, vectors):
        payload = {
            key: clean_payload_value(value)
            for key, value in record.items()
            if key != "_embedding_text"
        }
        payload["embedding_model"] = EMBEDDING_MODEL
        points.append(
            PointStruct(
                id=create_point_id(str(record["record_id"])),
                vector=vector.tolist(),
                payload=payload,
            )
        )
    return points


def ingest_lecture(
    *,
    work_dir: Path,
    lecture_id: str,
    caption_path: Optional[Path] = None,
    slide_path: Optional[Path] = None,
    transcript_path: Optional[Path] = None,
    discussion_path: Optional[Path] = None,
    quiz_path: Optional[Path] = None,
    quiz_solution_path: Optional[Path] = None,
    course_id: str = COURSE_ID,
    progress: Optional[ProgressCallback] = None,
) -> dict[str, Any]:
    # Ingests whichever assets were provided for one lecture/unit and upserts their points into Qdrant.
    report = progress or _noop_progress
    provided = [caption_path, slide_path, transcript_path, discussion_path, quiz_path, quiz_solution_path]
    if not any(provided):
        raise ValueError(
            "At least one asset is required: captions, slides, transcript, discussion, "
            "quiz, or quiz_solution."
        )

    lecture_id = _slugify_lecture_id(lecture_id)
    extracted_dir = Path(work_dir) / "extracted"
    extracted_dir.mkdir(parents=True, exist_ok=True)

    caption_records: list[dict[str, Any]] = []
    transcript_records: list[dict[str, Any]] = []
    discussion_records: list[dict[str, Any]] = []
    slide_records: list[dict[str, Any]] = []
    quiz_records: list[dict[str, Any]] = []
    quiz_solution_records: list[dict[str, Any]] = []

    if caption_path:
        report("extract", 0.05, f"extracting {lecture_id} captions")
        caption_df = extract_vtt_captions(lecture_id, Path(caption_path), extracted_dir)
        caption_chunk_df = create_caption_chunks(caption_df, extracted_dir)
        caption_records = _build_caption_records(caption_chunk_df, lecture_id, course_id)

    if transcript_path:
        report("extract", 0.2, "extracting transcript")
        transcript_text = _extract_plain_text(lecture_id, Path(transcript_path), extracted_dir)
        transcript_records = _build_text_records(transcript_text, lecture_id, course_id, "transcript")

    if discussion_path:
        report("extract", 0.3, "extracting discussion notes")
        discussion_text = _read_text_file(Path(discussion_path))
        discussion_records = _build_text_records(discussion_text, lecture_id, course_id, "discussion")

    if quiz_path:
        report("extract", 0.4, "extracting quiz/exam questions")
        quiz_text = _extract_plain_text(lecture_id, Path(quiz_path), extracted_dir)
        quiz_records = _build_text_records(
            quiz_text, lecture_id, course_id, "quiz", id_prefix="QUIZ", role="question"
        )

    if quiz_solution_path:
        report("extract", 0.45, "extracting quiz/exam solutions")
        solution_text = _extract_plain_text(lecture_id, Path(quiz_solution_path), extracted_dir)
        quiz_solution_records = _build_text_records(
            solution_text, lecture_id, course_id, "quiz", id_prefix="QUIZSOLUTION", role="solution"
        )

    if slide_path:
        report("extract", 0.5, "extracting slides")
        slide_df, slide_image_df = extract_slide_text(lecture_id, Path(slide_path), extracted_dir)
        report("visual_analysis", 0.55, f"analysing {len(slide_image_df)} slides via Gemini")
        slide_records = _build_slide_records(slide_df, slide_image_df, lecture_id, course_id, report)

    report("embedding", 0.8, "embedding records via API")
    points = (
        _to_points(caption_records)
        + _to_points(slide_records)
        + _to_points(transcript_records)
        + _to_points(discussion_records)
        + _to_points(quiz_records)
        + _to_points(quiz_solution_records)
    )

    report("upsert", 0.9, f"upserting {len(points)} points to Qdrant")
    client = create_qdrant_client()
    create_qdrant_collection(client)
    upload_points(client, points)

    report("done", 1.0, "ingestion complete")
    return {
        "lecture_id": lecture_id,
        "course_id": course_id,
        "caption_records": len(caption_records),
        "slide_records": len(slide_records),
        "transcript_records": len(transcript_records),
        "discussion_records": len(discussion_records),
        "quiz_records": len(quiz_records),
        "quiz_solution_records": len(quiz_solution_records),
        "points_upserted": len(points),
        "collection": COLLECTION_NAME,
    }
