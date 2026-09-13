"""Batch-ingest a folder of course material through the real /api/ingest endpoint.

Drives the backend's actual online ingestion path over HTTP (the same one the
/register page uses), one unit at a time, and polls each job to completion
before moving to the next. Nothing here talks to Qdrant/Gemini/HF directly —
it just automates what a human would do by hand in the UI, so ingested points
are identical either way.

The project's purpose is finding where students struggle, so this covers the
whole course surface, not just lecture content: captions, slides, transcripts,
discussion threads, and quiz/exam questions with their solutions.

Two folder shapes are recognized, and both fall out of ONE discovery pass:

1. Per-unit folders — one subfolder per lecture (or lecture-like unit, e.g.
   "readings", "syllabus"), with recognized files inside:

       <assets-dir>/<lecture_id>/
           slides.*          captions.*          transcript.*
           discussion.*      quiz.*              solution.*

   All optional; a folder needs at least one to be picked up.

2. Flat quiz/exam containers — a subfolder (e.g. "assignments", "exams") with
   NO recognized per-unit files, but a flat pile of question/solution PDFs
   named so the solution is the question's filename plus a "solution" suffix:

       assignments/Assignment1.pdf
       assignments/Assignment1_SOLUTION.pdf
       assignments/Assignment2.pdf
       ...

   Each pair (or lone question/solution) becomes its own unit, ingested as
   quiz content — exactly the "quiz + student answers" evidence the app
   needs, without requiring one folder per item.

See backend/database/courses/README.md for the full convention. Default
--assets-dir is backend/database/courses/<course-id>.

Usage
-----
    # Start the backend first, in another terminal:
    #   cd backend && uvicorn app.main:app --port 8000

    python scripts/batch_ingest.py --course-id bio-101
    python scripts/batch_ingest.py --course-id bio-101 --dry-run
    python scripts/batch_ingest.py --course-id bio-101 --lecture lec02
    python scripts/batch_ingest.py --course-id bio-101 --exclude lec34,lec35
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path
from typing import Optional

import httpx


BACKEND_ROOT = Path(__file__).resolve().parents[1]

# Recognized per-unit asset filename prefixes (exact "kind.<ext>" match, case-insensitive).
ASSET_KINDS = ("slides", "captions", "transcript", "discussion", "quiz", "solution")
DOCUMENT_EXTENSIONS = (".pdf", ".md", ".txt")

# Backend multipart field names these map to (see app/api/routes/ingest.py).
FORM_FIELD_BY_KIND = {
    "slides": "slides",
    "captions": "captions",
    "transcript": "transcript",
    "discussion": "discussion",
    "quiz": "quiz",
    "solution": "quiz_solution",
}

# Matches a trailing "solution" suffix on a filename stem, any of the separators/casing
# a course might use: "_SOLUTION", "-Solution", " solution", etc.
_SOLUTION_SUFFIX_RE = re.compile(r"[\s_\-]*solution$", re.IGNORECASE)


def _slug(value: str) -> str:
    # Turns an arbitrary name into a safe, readable unit-id fragment.
    return re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")


def _sort_key(name: str) -> tuple[int, str]:
    # Numbered names (lec1, lec2, lec10, Exam_1, ...) sort numerically first — so "lec10"
    # doesn't sort before "lec2" — then alphabetically for named units (readings, syllabus).
    match = re.search(r"\d+", name)
    number = int(match.group()) if match else 10**9
    return (number, name.lower())


def find_asset(folder: Path, kind: str) -> Optional[Path]:
    # Finds the file whose name is exactly "<kind>.<ext>", case-insensitively.
    matches = sorted(
        p for p in folder.iterdir() if p.is_file() and p.name.lower().startswith(f"{kind}.")
    )
    return matches[0] if matches else None


def discover_quiz_pairs(folder: Path) -> list[tuple[str, Optional[Path], Optional[Path]]]:
    # Pairs sibling files in a flat folder (assignments/, exams/, ...) into
    # (item_id, question_path, solution_path) by stripping a trailing "solution" suffix
    # from each filename's stem — no per-item subfolder required.
    docs = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in DOCUMENT_EXTENSIONS]
    pairs: dict[str, dict[str, Path]] = {}
    for path in docs:
        base, replaced = _SOLUTION_SUFFIX_RE.subn("", path.stem)
        role = "solution" if replaced else "question"
        pairs.setdefault(base, {})[role] = path

    return [
        (base, slot.get("question"), slot.get("solution"))
        for base, slot in sorted(pairs.items(), key=lambda item: _sort_key(item[0]))
    ]


def discover_units(
    assets_dir: Path, only: Optional[str], exclude: set[str]
) -> list[tuple[str, dict[str, Path]]]:
    # One pass over every subfolder: folders with recognized per-unit files become a single
    # unit each; folders with none (but with documents in them) are treated as a flat
    # quiz/exam container and expanded into one unit per question/solution pair.
    if not assets_dir.exists():
        print(f"ERROR: assets directory not found: {assets_dir}")
        return []

    units: list[tuple[str, dict[str, Path]]] = []
    subfolders = sorted(
        (p for p in assets_dir.iterdir() if p.is_dir() and p.name not in exclude),
        key=lambda p: _sort_key(p.name),
    )

    for folder in subfolders:
        recognized = {kind: find_asset(folder, kind) for kind in ASSET_KINDS}
        recognized = {kind: path for kind, path in recognized.items() if path is not None}

        if recognized:
            units.append((folder.name, recognized))
            continue

        for base, question_path, solution_path in discover_quiz_pairs(folder):
            files: dict[str, Path] = {}
            if question_path:
                files["quiz"] = question_path
            if solution_path:
                files["solution"] = solution_path
            if files:
                units.append((f"{folder.name}-{_slug(base)}", files))

    if only:
        units = [unit for unit in units if unit[0] == only]
    return units


def submit_unit(api_url: str, course_id: str, unit_id: str, files: dict[str, Path]) -> Optional[str]:
    # POSTs one unit's assets to /api/ingest and returns the job_id, or None on failure.
    opened = {}
    try:
        for kind, path in files.items():
            field = FORM_FIELD_BY_KIND[kind]
            opened[field] = (kind + path.suffix, open(path, "rb"))

        response = httpx.post(
            f"{api_url}/api/ingest",
            data={"lecture_id": unit_id, "course_id": course_id},
            files=opened,
            timeout=60,
        )
    finally:
        for _, handle in opened.values():
            handle.close()

    if response.status_code != 200:
        print(f"  ERROR: submit failed ({response.status_code}): {response.text[:300]}")
        return None
    return response.json()["job_id"]


def poll_job(api_url: str, job_id: str, poll_interval: float) -> dict:
    # Polls one job's status until it reaches a terminal state, printing progress along the way.
    last_stage = None
    while True:
        response = httpx.get(f"{api_url}/api/ingest/{job_id}", timeout=30)
        response.raise_for_status()
        job = response.json()

        if job["stage"] != last_stage:
            pct = round((job.get("progress") or 0) * 100)
            print(f"  [{pct:3d}%] {job['stage']:16} {job.get('message', '')}")
            last_stage = job["stage"]

        if job["status"] in ("completed", "failed"):
            return job
        time.sleep(poll_interval)


def main() -> int:
    # Discovers ingestable units, validates each, and submits + polls them one at a time.
    parser = argparse.ArgumentParser(description="Batch-ingest course material via POST /api/ingest.")
    parser.add_argument("--course-id", required=True, help="course id, e.g. bio-101")
    parser.add_argument(
        "--assets-dir",
        type=Path,
        default=None,
        help="folder of course subfolders (default: backend/database/courses/<course-id>)",
    )
    parser.add_argument("--api-url", default="http://localhost:8000", help="backend base URL")
    parser.add_argument("--lecture", default=None, help="only ingest this one unit id")
    parser.add_argument(
        "--exclude",
        default="",
        help="comma-separated unit ids to skip, e.g. lec34,lec35 (hold back for online testing)",
    )
    parser.add_argument("--poll-interval", type=float, default=2.0, help="seconds between status polls")
    parser.add_argument("--dry-run", action="store_true", help="validate and list units, submit nothing")
    args = parser.parse_args()

    exclude = {name.strip() for name in args.exclude.split(",") if name.strip()}
    assets_dir = args.assets_dir or (BACKEND_ROOT / "database" / "courses" / args.course_id)
    units = discover_units(assets_dir, args.lecture, exclude)
    if not units:
        print(f"No ingestable units found in {assets_dir}")
        return 2

    print(f"Found {len(units)} unit(s) in {assets_dir}")
    if exclude:
        print(f"Excluding: {', '.join(sorted(exclude))}")
    print()

    for unit_id, files in units:
        extras = ", ".join(f"{kind}={path.name}" for kind, path in files.items())
        print(f"OK    {unit_id}: {extras}")

    if args.dry_run:
        print(f"\nDry run: {len(units)} unit(s) would be submitted. Re-run without --dry-run to ingest.")
        return 0

    print(f"\nSubmitting {len(units)} unit(s) to {args.api_url} ...\n")
    results: list[tuple[str, str]] = []
    for unit_id, files in units:
        print(f"--- {unit_id} ---")
        job_id = submit_unit(args.api_url, args.course_id, unit_id, files)
        if job_id is None:
            results.append((unit_id, "submit_failed"))
            continue
        job = poll_job(args.api_url, job_id, args.poll_interval)
        if job["status"] == "completed":
            r = job.get("result", {})
            counts = ", ".join(
                f"{key}={r[key]}"
                for key in (
                    "caption_records",
                    "slide_records",
                    "transcript_records",
                    "discussion_records",
                    "quiz_records",
                    "quiz_solution_records",
                )
                if r.get(key)
            )
            print(f"  DONE  points_upserted={r.get('points_upserted')}" + (f" ({counts})" if counts else ""))
        else:
            print(f"  FAILED: {job.get('error')}")
        results.append((unit_id, job["status"]))
        print()

    print("=== Summary ===")
    for unit_id, status in results:
        print(f"  {unit_id}: {status}")
    failures = [r for r in results if r[1] != "completed"]
    return 1 if failures else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except httpx.ConnectError:
        print("\nERROR: could not reach the backend. Is it running? (uvicorn app.main:app)")
        sys.exit(2)
