"""Offline ingestion helper — run the REAL pipeline on local lecture files.

Runs the exact same pipeline the backend uses (database/src/ingest_service.ingest_lecture)
against files already on disk, so you can push lectures into Qdrant from your machine and
hold a couple back to test the online /api/ingest flow.

Prereqs
-------
1. Populate backend/.env with QDRANT_URL, QDRANT_API_KEY, GEMINI_API_KEY, HF_TOKEN.
2. Install the pipeline deps:  pip install -r requirements.txt
3. STRONGLY recommended: target a throwaway collection so you don't pollute production:
       --collection COURSERA_MIP_TEST
   (defaults to whatever QDRANT_COLLECTION is set to, else the live collection.)

Examples
--------
# Push one lecture into a test collection
python scripts/ingest_local.py --lecture-id lec01 \
    --slides assets/bio/lec01_slides.pdf \
    --captions assets/bio/lec01.vtt \
    --transcript assets/bio/lec01_transcript.pdf \
    --course-id biology-7016 --collection COURSERA_MIP_TEST

# Dry run (extract -> Gemini -> embed, but DON'T upsert)
python scripts/ingest_local.py --lecture-id lec02 \
    --slides ... --captions ... --collection COURSERA_MIP_TEST --no-push
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv


BACKEND_ROOT = Path(__file__).resolve().parents[1]
DATABASE_DIR = BACKEND_ROOT / "database"
REQUIRED_CREDS = ("QDRANT_URL", "QDRANT_API_KEY", "GEMINI_API_KEY")


def _progress(stage: str, pct: float, message: str) -> None:
    # Prints a single progress line per pipeline stage so the run is easy to follow.
    print(f"[{pct*100:5.1f}%] {stage:16} {message}")


def main() -> int:
    # Parses args, checks creds, and runs the real ingest_lecture pipeline on local files.
    parser = argparse.ArgumentParser(description="Offline lecture ingestion into Qdrant.")
    parser.add_argument("--lecture-id", required=True, help="e.g. lec01")
    parser.add_argument("--slides", required=True, type=Path, help="slides PDF path")
    parser.add_argument("--captions", required=True, type=Path, help="captions .vtt/.srt path")
    parser.add_argument("--transcript", type=Path, default=None, help="transcript PDF path (optional)")
    parser.add_argument("--course-id", default="biology-7016", help="course id stored on records")
    parser.add_argument("--collection", default=None, help="override QDRANT_COLLECTION (use a test collection!)")
    parser.add_argument("--no-push", action="store_true", help="run the pipeline but skip the Qdrant upsert")
    args = parser.parse_args()

    load_dotenv(BACKEND_ROOT / ".env")

    # Set the target collection BEFORE importing the pipeline (read at import time).
    if args.collection:
        os.environ["QDRANT_COLLECTION"] = args.collection

    missing = [c for c in REQUIRED_CREDS if not os.getenv(c)]
    if not (os.getenv("HF_TOKEN") or os.getenv("HF_TOKEN_EMBEDDING")):
        missing.append("HF_TOKEN")
    if missing:
        print(f"ERROR: missing credentials in backend/.env: {', '.join(missing)}")
        return 2

    for path in (args.slides, args.captions, *( (args.transcript,) if args.transcript else () )):
        if not path.exists():
            print(f"ERROR: file not found: {path}")
            return 2

    sys.path.insert(0, str(DATABASE_DIR))
    from src.ingest_service import ingest_lecture  # noqa: E402

    work_dir = BACKEND_ROOT / ".data" / "ingest_local" / args.lecture_id
    work_dir.mkdir(parents=True, exist_ok=True)

    print(f"Ingesting {args.lecture_id} -> collection '{os.getenv('QDRANT_COLLECTION', '(default)')}' "
          f"(push={'no' if args.no_push else 'yes'})\n")

    result = ingest_lecture(
        work_dir=work_dir,
        lecture_id=args.lecture_id,
        caption_path=args.captions,
        slide_path=args.slides,
        transcript_path=args.transcript,
        course_id=args.course_id,
        progress=_progress,
        push=not args.no_push,
    )

    print("\nResult:")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
