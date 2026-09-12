# Coursera Multimodal Intelligence Platform (MIP)

Coursera-MIP is an AI-powered curriculum analytics and multimodal diagnostic engine. It indexes lecture videos, transcripts, and slides into a unified vector space, synthesizes pedagogical friction diagnostics via LLM reasoning, and delivers a human-in-the-loop recommendation escalation pipeline.

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
- **Auth**: Supabase JWT / JWKS verification (implemented in `app/core/security.py`)

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
