# Coursera MIP Frontend

Next.js (App Router) frontend for the Coursera Multimodal Intelligence Platform — an
internal tool for educators/course staff to ingest course material, ask grounded questions
about it (RAG), and review AI-curated recommendations in a human-in-the-loop workflow.

Talks to the [backend](../backend/README.md) exclusively over its REST API — no direct
Qdrant/Supabase/LLM access from the browser.

## Stack

- **Core**: Next.js 16 (App Router), React 19, TypeScript
- **Styling & UI**: Tailwind CSS v4, shadcn-style components on Base UI, Lucide icons
- **Data fetching**: TanStack React Query v5 + Axios (one shared instance, `src/api/axios.ts`)
- **Forms**: React Hook Form
- **Charts**: Recharts
- **Feedback**: React Hot Toast

## Routes

| Route | Purpose |
| --- | --- |
| `/` | Login (landing page) |
| `/dashboard` | Qdrant/Supabase metrics + live ingestion processing monitor |
| `/chat` | Ask — grounded Q&A over the ingested course corpus |
| `/recommendations` | Curated recommendations: review, accept/reject, notes |
| `/register` | Ingest course material (captions, slides, transcript, discussion, quiz+solutions) |
| `/profile` | Educator profile |

## Setup

```bash
cd frontend
npm install
cp .env.example .env.local
```

Set `NEXT_PUBLIC_API_URL` in `.env.local` to your running backend (e.g.
`http://localhost:8000` locally, or the deployed backend URL). This is inlined at build/dev
time — restart `next dev` after changing it. `NEXT_PUBLIC_API_TIMEOUT` (ms) defaults to
300000 (5 min), sized for long-running LLM/ingestion requests.

The backend must be running (see [`../backend/README.md`](../backend/README.md)) — this app
has no functionality of its own without it.

## Run

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Build

```bash
npm run build
npm start
```

## API consumption pattern

Every backend call goes through the shared Axios instance (`src/api/axios.ts`), wrapped in a
TanStack Query hook — one file per endpoint, under `src/hooks/query/` (reads) or
`src/hooks/mutations/` (writes). Components never call `fetch`/`axios` directly. Request/response
logging is built into the Axios instance's interceptors (visible in the browser console).

Example: `src/hooks/query/use-recommendations.ts` → `GET /api/recommendations`,
`src/hooks/mutations/use-create-ingestion.ts` → `POST /api/ingest` (multipart).

## Design system

Component primitives live in `src/components/ui/` (Button, Card, Select, Table, Progress,
Badge, …) — shadcn-style, built on Base UI, themed via CSS variables in `globals.css` for
light/dark mode. Feature components compose these; new UI should reuse existing primitives
rather than introducing new styling patterns.

## Notes

- CORS: the backend's `FRONTEND_ORIGINS` env var must include whatever origin this app runs
  on (`http://localhost:3000`, `:3001` if that port gets used instead, your deployed URL, …).
- No auth is currently enforced by the backend — see the backend README.
