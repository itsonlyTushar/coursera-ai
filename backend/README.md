# Coursera MIP Backend

FastAPI backend that orchestrates the `rag` retrieval/synthesis pipeline (Qdrant dense
search, then Cohere rerank, then Groq/Instructor synthesis) and persists the
human-in-the-loop workflow to Supabase (PostgREST).

The HTTP surface is intentionally minimal: it exposes only the endpoints the frontend
consumes, plus `/health`. The multimodal ingestion pipeline is bundled at `backend/database/`;
the backend drives it online via `POST /api/ingest`, while the full offline batch pipeline in
that package is run manually by the database team.

## Project structure

```text
backend/
├── app/
│   ├── main.py              # FastAPI app: logging, CORS, router mount
│   ├── core/                # Cross-cutting concerns
│   │   ├── config.py        # Settings (pydantic-settings) + get_settings()
│   │   └── logging.py       # setup_logging() / get_logger()
│   ├── schemas/             # Pydantic request/response models, grouped by domain
│   │   ├── health.py  dashboard.py  conversation.py  rag.py
│   ├── services/            # Business logic / integrations
│   │   ├── qdrant_service.py     # metrics (cached collection scan)
│   │   ├── supabase_service.py   # persistence via a pooled httpx client
│   │   └── rag_service.py        # bridges the rag pipeline; synthesize_and_record()
│   │                              # orchestrates run + persist so routes stay thin
│   ├── api/
│   │   ├── router.py        # aggregates all route modules
│   │   └── routes/          # one module per domain
│   │       ├── health.py  metrics.py  dashboard.py  conversations.py  rag.py
│   └── tests/               # pytest suite (runs without external services)
├── rag/                     # Standalone RAG pipeline + FastMCP server
│   ├── retrieval.py  synthesis.py  schema.py  setup_server.py
├── database/                # Bundled ingestion pipeline (src/, sql/) + offline batch tools
│   ├── src/                 # extraction, embedding_client, ingest_service, qdrant_db, ...
│   └── sql/                 # Supabase schema, views, RLS
├── requirements.txt         # runtime deps (API + ingestion pipeline)
├── requirements-dev.txt     # runtime + test deps
└── pytest.ini
```

## Setup

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Fill `.env` with the Qdrant URL/collection/key, Supabase URL + secret key, Groq key, and
HuggingFace/Cohere keys. Keep real secrets out of git.

### Supabase schema (one-time per project)

A fresh Supabase project doesn't have any of the app's tables yet, so `/api/synthesize` and
friends will fail with `Could not find the table 'public.conversations'` until the schema is
applied. Apply `database/sql/supabase_schema.sql` then `supabase_dashboard_views.sql` then
`supabase_rls.sql`, in that order since the views and policies depend on the tables existing
first. Two ways to do it:

- **Supabase SQL Editor**: paste and run each file, in order.
- **[`scripts/apply_supabase_sql.py`](scripts/apply_supabase_sql.py)**: runs all three
  locally via a direct Postgres connection. Needs `SUPABASE_DB_URL` in `.env`, which is the
  **Session Pooler** connection string from Supabase's Database settings (not
  `SUPABASE_URL`/`SUPABASE_SECRET_KEY`, those are REST-API-only and can't run DDL), plus
  `pip install -r requirements-dev.txt`. Pass `--dry-run` to just test the connection.

## Run

```bash
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Or specify the venv binary directly: `.venv\Scripts\python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`

Interactive API docs (Swagger UI, ReDoc, and the `/openapi.json` schema route) are
disabled in [`app/main.py`](app/main.py). Re-enable them by removing the
`docs_url=None, redoc_url=None, openapi_url=None` arguments from the `FastAPI(...)` call.

## Test

```bash
pip install -r requirements-dev.txt
python -m pytest
```

The suite uses FastAPI dependency overrides and stubbed services, so it needs no Qdrant,
Supabase, or LLM credentials.

## API reference

All application routes are prefixed with `/api`. These are exactly the endpoints the
frontend uses.

| Method & path                                       | Purpose                                                                                                                                  |
| --------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| `GET /health`                                       | Liveness + which integrations are configured.                                                                                            |
| `GET /api/metrics`                                  | Live Qdrant collection health and content-type/course/model breakdowns (30s cached).                                                     |
| `GET /api/dashboard/summary`                        | Aggregated Supabase dashboard views (activity, topics, evidence, lectures, feedback).                                                    |
| `GET /api/conversations`                            | Recent conversations, newest first.                                                                                                      |
| `GET /api/conversations/{conversation_id}/messages` | Full transcript for one conversation (queries + nested responses/evidence/recommendations).                                              |
| `POST /api/synthesize`                              | Runs the RAG pipeline, then persists the query/answer/evidence (creating a conversation if none is supplied). Returns the cited insight. |
| `POST /api/recommendations`                         | Saves a human-curated recommendation and marks its response `pending` for review.                                                        |
| `GET /api/recommendations`                          | Paginated curated recommendations with their source context.                                                                             |
| `POST /api/review-feedback`                         | Records a reviewer's approve/reject decision against a response.                                                                         |
| `POST /api/ingest`                                  | Multipart upload of a lecture's assets; stages them and starts a background ingestion job. Returns the job to poll.                      |
| `GET /api/ingest`                                   | Lists recent ingestion jobs.                                                                                                             |
| `GET /api/ingest/{job_id}`                          | Live status/progress of one ingestion job.                                                                                               |

## Online ingestion (`/api/ingest`)

An educator uploads course material to `POST /api/ingest`: captions (`.vtt`/`.srt`), slides
(`.pdf`), transcript (`.pdf`/`.md`), discussion notes (`.md`), and/or a quiz/exam question set
with its solutions (`.pdf`/`.md` each). All six are optional, but at least one is required.
Since the project's purpose is finding where students struggle, the full course surface
matters: many courses lack slide decks or synced captions, and exam/assignment questions
plus their official solutions are the kind of evidence (expected answer vs. discussion
confusion) the RAG layer needs. The backend stages the files to a per-job working directory and
runs the pipeline as a background job: extract, then Gemini visual analysis (slides only),
then API embeddings, then Qdrant upsert, while the request returns immediately with a `job_id`
to poll via `GET /api/ingest/{job_id}`.

- **Orchestration** lives in [`app/services/ingestion_service.py`](app/services/ingestion_service.py),
  a thread-pool job manager with an injectable runner, so it is unit-tested without ML deps.
- **The pipeline** lives in the bundled database package
  ([`database/src/ingest_service.py`](database/src/ingest_service.py)), a per-lecture runner
  that reuses the batch pipeline's building blocks (extraction, `analyse_image`, API embeddings,
  Qdrant helpers) and produces identical point ids/payloads. Transcript, discussion, and quiz
  text are all chunked and embedded rather than just extracted and discarded. Quiz questions and
  solutions share `content_type="quiz"`, distinguished by a `role` payload field, since the
  DB only allows a fixed set of content types. Transcript, discussion, and quiz are already
  valid end to end: Qdrant payload, the RAG service's normalizer, and the Supabase DB constraint.
  Frames are out of scope for v1 (disabled by default in the batch pipeline too), and slide
  images stay on local disk; uploading them to the private HF visual dataset is a separate step.
- **The pipeline is real and live-ready**, with no mocks or offline-only models. Embeddings run
  through the Hugging Face Inference API (same model the RAG side uses), visual analysis through
  the Gemini API, and points are upserted straight into the live Qdrant collection. The pipeline
  deps ship in `requirements.txt`, so a standard install runs ingestion:
  ```bash
  pip install -r requirements.txt
  ```
  A live run also needs the bundled `database/` package (now inside `backend/`) and the ingestion
  credentials (`GEMINI_API_KEY`, `QDRANT_URL`/`QDRANT_API_KEY`, `HF_TOKEN`) set as environment
  variables, or in `backend/database/.env` locally. Missing creds surface as a failed job with a
  clear error, visible in the processing monitor, instead of a silent stub.
- v1 keeps job state in memory and runs one job at a time (serial worker). A durable queue or
  external worker is the scaling path.

## Notes

- The `rag/` package is standalone (it can also run as a FastMCP server via
  `rag/setup_server.py`). `app/services/rag_service.py` imports it lazily so startup stays
  fast and missing credentials fail with a clear 503.
- `retrieval_evidence.content_type` has a DB `CHECK` constraint; `rag_service._content_type`
  normalizes any modality to the allowed set before persistence.
- Media parsing, embedding generation, and Qdrant upserts live in the bundled `database/`
  pipeline; the backend imports and drives it for online ingestion (`/api/ingest`).
