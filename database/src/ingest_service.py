"""Per-lecture online ingestion runner.

The rest of the ``database`` package is a whole-course batch pipeline that scans
fixed folders and aggregates every lecture at once. This module exposes a single
callable that ingests ONE lecture's uploaded assets end to end — extract →
Gemini visual analysis → API embeddings → Qdrant upsert — writing only inside a
caller-provided working directory. The backend calls it as a background job.

It deliberately reuses the granular, path-parameterized building blocks
(extraction sub-functions, ``analyse_image``, ``combine_searchable_feilds`` and
the Qdrant helpers) so the points it upserts are identical in id and payload
shape to the batch pipeline's.

Scope (v1): captions + slides. Video, if supplied, is used only for metadata;
caption-linked frame extraction is intentionally out of scope (it is disabled by
default in the batch pipeline too). Slide images are kept on local disk for this
job; uploading them to the private HF visual dataset is a separate step.
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
    extract_tarnscript_text,
    extract_video_metadata,
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
from src.visual_database import combine_searchable_feilds


ProgressCallback = Callable[[str, float, str], None]


def _noop_progress(stage: str, pct: float, message: str) -> None:
    # Default progress sink so callers may omit a callback without extra guards.
    pass


def _lecture_number(lecture_id: str) -> int:
    # Extracts the integer lecture number so ids like MOD_01 / VIDEO_LEC01 can be derived consistently.
    return int(re.search(r"\d+", lecture_id).group())


def _build_caption_records(
    caption_chunk_df: pd.DataFrame, lecture_id: str, course_id: str
) -> list[dict[str, Any]]:
    # Turns caption chunks into caption records matching build_caption_database so payloads stay consistent.
    number = _lecture_number(lecture_id)
    records: list[dict[str, Any]] = []
    for _, row in caption_chunk_df.iterrows():
        records.append(
            {
                "record_id": row["chunk_id"],
                "chunk_id": row["chunk_id"],
                "asset_id": f"VIDEO_LEC{number:02d}",
                "course_id": course_id,
                "module_id": f"MOD_{number:02d}",
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


def _build_slide_records(
    slide_df: pd.DataFrame,
    slide_image_df: pd.DataFrame,
    lecture_id: str,
    course_id: str,
    progress: ProgressCallback,
) -> list[dict[str, Any]]:
    # Runs Gemini per slide image and assembles slide records matching build_slide_database.
    from src.visual_analysis import analyse_image  # lazy: needs GEMINI_API_KEY

    number = _lecture_number(lecture_id)
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
            "record_id": f"SLIDE_LEC{number:02d}_{slide_no:03d}",
            "content_type": "slide",
            "course_id": course_id,
            "module_id": f"MOD_{number:02d}",
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
        record["searchable_text"] = combine_searchable_feilds(pd.Series(record))
        record["_embedding_text"] = record["searchable_text"]
        records.append(record)
        progress("visual_analysis", position / max(total, 1), f"analysed slide {position}/{total}")

    return records


def _to_points(records: list[dict[str, Any]]) -> list[PointStruct]:
    # Embeds each record's text via the API and packs id/vector/payload exactly like the batch uploader.
    texts = [record["_embedding_text"] for record in records]
    vectors = embed_texts(texts)
    if len(vectors) != len(records):
        raise ValueError(f"Embedding count {len(vectors)} != record count {len(records)}")

    points: list[PointStruct] = []
    for record, vector in zip(records, vectors):
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
    caption_path: Path,
    slide_path: Path,
    transcript_path: Optional[Path] = None,
    video_path: Optional[Path] = None,
    course_id: str = COURSE_ID,
    progress: Optional[ProgressCallback] = None,
) -> dict[str, Any]:
    # Ingests one lecture's uploaded assets end to end and upserts caption+slide points into Qdrant.
    report = progress or _noop_progress
    lecture_id = normalize_lecture_id(lecture_id)
    extracted_dir = Path(work_dir) / "extracted"
    extracted_dir.mkdir(parents=True, exist_ok=True)

    report("extract", 0.05, f"extracting {lecture_id} captions")
    caption_df = extract_vtt_captions(lecture_id, Path(caption_path), extracted_dir)
    caption_chunk_df = create_caption_chunks(caption_df, extracted_dir)

    if transcript_path:
        report("extract", 0.15, "extracting transcript")
        extract_tarnscript_text(lecture_id, Path(transcript_path), extracted_dir)

    if video_path:
        report("extract", 0.2, "reading video metadata")
        extract_video_metadata(lecture_id, Path(video_path), extracted_dir)

    report("extract", 0.25, "extracting slides")
    slide_df, slide_image_df = extract_slide_text(lecture_id, Path(slide_path), extracted_dir)

    caption_records = _build_caption_records(caption_chunk_df, lecture_id, course_id)
    report("visual_analysis", 0.3, f"analysing {len(slide_image_df)} slides via Gemini")
    slide_records = _build_slide_records(
        slide_df, slide_image_df, lecture_id, course_id, report
    )

    report("embedding", 0.75, "embedding records via API")
    points = _to_points(caption_records) + _to_points(slide_records)

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
        "points_upserted": len(points),
        "collection": COLLECTION_NAME,
    }
