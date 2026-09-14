# Coursera Multimodal Intelligence Platform (MIP)

Coursera-MIP is an AI-powered curriculum analytics and multimodal diagnostic engine. It
indexes a course's full surface — lecture transcripts, slides, discussion threads, and
quiz/exam questions with their official solutions — into a unified vector space, synthesizes
pedagogical friction diagnostics via LLM reasoning (grounded, cited retrieval), and delivers
a human-in-the-loop recommendation escalation pipeline for course staff to review, accept, or
reject.

See [`docs/architecture.md`](docs/architecture.md) for a system diagram (source: `docs/architecture.excalidraw`).

---

## Tech Stack by Module

### Frontend (`frontend/`)

- **Core**: Next.js 16 (App Router), React 19, TypeScript
- **Styling & UI**: Tailwind CSS v4, Shadcn UI, Radix / Base UI, Lucide Icons
- **State & Data Fetching**: TanStack React Query v5, Axios
- **Visualization**: Recharts
- **Forms & Feedback**: React Hook Form, React Hot Toast

### Backend (`backend/`)

- **API & Runtime**: FastAPI, Uvicorn, Python 3.10+
- **RAG & Orchestration**: LangChain, FastMCP (Model Context Protocol)
- **Vector Search & Reranking**: Qdrant (dense vector search), Cohere Rerank
- **LLM Reasoning & Output**: Groq, Instructor, Pydantic v2
- **Embeddings**: BGE via Hugging Face Inference Endpoints (serverless)
- **Persistence**: Supabase (PostgreSQL)

### Database & Pipeline (`backend/database/`)

- **Media Ingestion & Parsing**: PyMuPDF (slides & transcripts), WebVTT (captions); OpenCV (video frames, offline batch pipeline only)
- **Multimodal AI**: Google Gemini API (`google-genai`) for visual slide & frame analysis
- **Vector Ingestion**: Qdrant Client, BGE embeddings via the Hugging Face Inference API (768-dim)
- **Relational Storage & Views**: Supabase (PostgreSQL schemas, views, and RLS policies)
- **Data Processing**: Pandas, NumPy, Pydantic

---

## Repository Structure

```text
coursera-mip/
├── backend/        # FastAPI server, RAG pipeline, MCP server, + the ingestion pipeline
│   └── database/   # Multimodal extraction, ingestion pipeline, and Supabase SQL
└── frontend/       # Next.js web application, diagnostic dashboard, and chat interface
```

---

## Quick Start

### 1. Run Backend (FastAPI)

```bash
cd backend
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 2. Run Frontend (Next.js)

```bash
cd frontend
npm run dev
```
