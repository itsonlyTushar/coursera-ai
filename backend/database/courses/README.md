# Staged course material for online ingestion

Drop downloaded course material here, then run `backend/scripts/batch_ingest.py`
against your **locally running backend** (`uvicorn app.main:app`). The script
POSTs each unit to the real `POST /api/ingest` endpoint — the same code path
the `/register` page uses — so what lands in Qdrant is identical either way.

The project's purpose is finding where students struggle, so ingest the whole
course surface, not just lecture content: syllabus, exams + solutions,
assignments + solutions, discussion threads, and transcripts all count.

This folder (everything below it) is git-ignored — only this README is
tracked. Raw course PDFs/captions/notes never get committed.

## Two folder shapes are supported

### 1. Per-unit folders — one folder per lecture (or lecture-like unit)

```
backend/database/courses/<course_id>/<lecture_id>/
    slides.pdf          # slide deck / lecture notes PDF
    captions.vtt          # .vtt or .srt
    transcript.pdf         # .pdf or .md/.txt
    discussion.md           # .md or .txt — learner discussion notes
    quiz.pdf                 # .pdf or .md/.txt — a quiz/exam question set
    solution.pdf               # .pdf or .md/.txt — its official solutions
```

**All six are optional — a folder just needs at least one of them.** File
names must start with `slides`, `captions`, `transcript`, `discussion`,
`quiz`, or `solution` (any extension, case-insensitive).

- `<course_id>` — one folder per course, e.g. `bio-101`.
- `<lecture_id>` — one folder per lecture *or named unit*, e.g. `lec01`, or
  a non-numbered unit like `readings`/`syllabus`. Folder name is used
  verbatim as the `lecture_id`.
- Course-wide material that isn't tied to one lecture (readings, syllabus) —
  give it its own folder (e.g. `syllabus/`) containing a `transcript.md`
  file; it's ingested exactly like any other unit, just without a number.

### 2. Flat quiz/exam containers — a folder of paired question + solution files

Many courses ship exams and assignments as a **flat pile of PDFs**, not one
folder per item — e.g. an `assignments/` or `exams/` folder straight from a
course download:

```
backend/database/courses/<course_id>/assignments/
    Assignment1.pdf
    Assignment1_SOLUTION.pdf
    Assignment2.pdf
    Assignment2_SOLUTION.pdf
```

No renaming needed. The batch script automatically pairs each question file
with its solution by stripping a trailing "solution" suffix from the
filename (`_SOLUTION`, `-Solution`, ` solution`, any case) — each pair becomes
its own unit (`assignments-assignment1`, `assignments-assignment2`, ...),
ingested as quiz content. A solution with no matching question (or vice
versa) is still ingested on its own.

A subfolder with **none** of the recognized files and **no** pairable
documents (e.g. random unrelated material) is automatically skipped — safe
to keep alongside real course folders.

## Example

```
backend/database/courses/bio-101/
├── assignments/             # flat container — auto-paired into 6 quiz units
│   ├── Assignment1.pdf
│   ├── Assignment1_SOLUTION.pdf
│   └── ...
├── exams/                   # flat container — auto-paired into 3 quiz units
│   ├── Exam_1.pdf
│   ├── Exam_1_SOLUTION.pdf
│   └── ...
├── lec01/
│   ├── Transcript.pdf
│   └── discussion.md
├── lec02/
│   └── Transcript.pdf
├── readings/
│   └── transcript.md        # renamed from readings.md
└── syllabus/
    └── transcript.md        # renamed from syllabus.md
```

## Running the batch

```bash
cd backend
pip install -r requirements.txt           # once, before first run
uvicorn app.main:app --port 8000          # in one terminal — must be running

python scripts/batch_ingest.py --course-id bio-101 --dry-run   # check first
python scripts/batch_ingest.py --course-id bio-101              # then ingest
```

To hold specific units back (e.g. to test the deployed `/register` page
later instead of ingesting them locally):

```bash
python scripts/batch_ingest.py --course-id bio-101 --exclude lec34,lec35
```

See `python scripts/batch_ingest.py --help` for all options (dry run,
single-unit filter, exclude list, custom API URL, poll interval).
