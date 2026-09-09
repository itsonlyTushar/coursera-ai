# Coursera MIP Backend

FastAPI backend that orchestrates the `rag` retrieval/synthesis pipeline (Qdrant dense
search → Cohere rerank → Groq/Instructor synthesis) and persists the human-in-the-loop
workflow to Supabase (PostgREST).

The HTTP surface is intentionally minimal: it exposes only the endpoints the frontend
consumes, plus `/health`. Vector ingestion and multimodal extraction live in the separate
`database/` project, not here.

## Project structure

```text
backend/
├── app/
│   ├── main.py              # FastAPI app: logging, CORS, router mount
│   ├── core/                # Cross-cutting concerns
│   │   ├── config.py        # Settings (pydantic-settings) + get_settings()
│   │   ├── logging.py       # setup_logging() / get_logger()
│   │   └── security.py      # JWT/JWKS auth dependency (implemented, NOT wired)
│   ├── schemas/             # Pydantic request/response models, grouped by domain
│   │   ├── health.py  dashboard.py  conversation.py  rag.py
│   ├── services/            # Business logic / integrations
│   │   ├── qdrant_service.py     # metrics (cached collection scan)
│   │   ├── supabase_service.py   # persistence via a pooled httpx client
│   │   └── rag_service.py        # bridge to the rag pipeline
│   ├── api/
│   │   ├── router.py        # aggregates all route modules
│   │   └── routes/          # one module per domain
│   │       ├── health.py  metrics.py  dashboard.py  conversations.py  rag.py
│   └── tests/               # pytest suite (runs without external services)
├── rag/                     # Standalone RAG pipeline + FastMCP server
│   ├── retreival.py  synthesis.py  schema.py  setup_server.py
├── requirements.txt         # runtime deps
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

## Run

```bash
.venv\Scripts\python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

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

| Method & path | Purpose |
| --- | --- |
| `GET /health` | Liveness + which integrations are configured. |
| `GET /api/metrics` | Live Qdrant collection health and content-type/course/model breakdowns (30s cached). |
| `GET /api/dashboard/summary` | Aggregated Supabase dashboard views (activity, topics, evidence, lectures, feedback). |
| `GET /api/conversations` | Recent conversations, newest first. |
| `GET /api/conversations/{conversation_id}/messages` | Full transcript for one conversation (queries + nested responses/evidence/recommendations). |
| `POST /api/synthesize` | Runs the RAG pipeline, then persists the query/answer/evidence (creating a conversation if none is supplied). Returns the cited insight. |
| `POST /api/recommendations` | Saves a human-curated recommendation and marks its response `pending` for review. |
| `GET /api/recommendations` | Paginated curated recommendations with their source context. |
| `POST /api/review-feedback` | Records a reviewer's approve/reject decision against a response. |
| `POST /api/ingest` | Multipart upload of a lecture's assets; stages them and starts a background ingestion job. Returns the job to poll. |
| `GET /api/ingest` | Lists recent ingestion jobs. |
| `GET /api/ingest/{job_id}` | Live status/progress of one ingestion job. |

## Authentication

Supabase JWT verification is implemented in [`app/core/security.py`](app/core/security.py)
but **not yet wired** — every endpoint is currently public. Tokens are verified against the
JWKS at `SUPABASE_JWKS_URL` (RS256/ES256) with the `authenticated` audience.

To protect an endpoint, add the dependency:

```python
from fastapi import Depends
from app.core.security import CurrentUser, get_current_user

@router.get("/api/example")
def example(user: CurrentUser = Depends(get_current_user)):
    return {"user_id": user.id}
```

`get_optional_user` is also available for endpoints that personalize but don't require login.

## Online ingestion (`/api/ingest`)

An educator uploads a lecture's assets (captions `.vtt` + slides `.pdf` required; transcript
`.pdf` and video optional) to `POST /api/ingest`. The backend stages the files to a per-job
working directory and runs the pipeline **as a background job** — extract → Gemini visual
analysis → API embeddings → Qdrant upsert — while the request returns immediately with a
`job_id` to poll via `GET /api/ingest/{job_id}`.

- **Orchestration** lives in [`app/services/ingestion_service.py`](app/services/ingestion_service.py)
  (a thread-pool job manager with an injectable runner, so it is unit-tested without ML deps).
- **The pipeline** lives in the database package
  ([`database/src/ingest_service.py`](../database/src/ingest_service.py)) — a per-lecture runner
  that reuses the batch pipeline's building blocks (extraction, `analyse_image`, API embeddings,
  Qdrant helpers) and produces identical point ids/payloads. Scope: captions + slides. Frames
  are out of scope for v1 (disabled by default in the batch pipeline too), and slide images stay
  on local disk (uploading them to the private HF visual dataset is a separate step).
- **To run ingestion**, the backend host needs the pipeline deps and the database credentials:
  ```bash
  pip install -r requirements-ingest.txt      # google-genai, opencv, PyMuPDF, webvtt, ...
  ```
  plus a populated `database/.env` (`GEMINI_API_KEY`, `QDRANT_URL`/`QDRANT_API_KEY`, `HF_TOKEN`).
  The orchestration/API layer and its tests run without these; only executing a real job needs them.
- v1 keeps job state in memory and runs one job at a time (serial worker). A durable queue /
  external worker is the scaling path.

## Notes

- The `rag/` package is standalone (it can also run as a FastMCP server via
  `rag/setup_server.py`). `app/services/rag_service.py` imports it lazily so startup stays
  fast and missing credentials fail with a clear 503.
- `retrieval_evidence.content_type` has a DB `CHECK` constraint; `rag_service._content_type`
  normalizes any modality to the allowed set before persistence.
- Media ingestion, embedding generation, and Qdrant upserts are owned by the `database/`
  pipeline, not this service.
