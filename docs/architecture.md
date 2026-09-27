# Architecture Diagrams

Mermaid diagrams for the four core pipelines in this repo. Rendered automatically on GitHub/GitLab, or in any Mermaid-compatible viewer.

## 1. Ingestion Pipeline

There is one wired, end-to-end pipeline: the **online per-lecture path**, driven by the UI and running fully inside a single ingestion job. The **offline batch path** (`database/src/pipeline.py`) is a separate, narrower tool — it only discovers and extracts whole-course material to CSVs; it does not itself run visual analysis, embedding, or Qdrant upsert.

```mermaid
flowchart TB
    subgraph Frontend
        A[register/page.tsx<br/>educator uploads assets] --> B[use-create-ingestion.ts<br/>POST /api/ingest multipart]
    end

    subgraph API["Backend API (app/)"]
        C[routes/ingest.py<br/>create_ingestion]
        D[IngestionJobManager<br/>ThreadPoolExecutor max_workers=1<br/>job.json state, resumable on restart]
        C --> D
    end

    subgraph Pipeline["database/src/ingest_service.py: ingest_lecture() (lazy import)"]
        E["extract 0.05-0.5<br/>captions (vtt/srt), transcript,<br/>discussion, quiz + solutions,<br/>slides via PyMuPDF"]
        F["visual_analysis ~0.55-0.8<br/>_build_slide_records<br/>analyse_image per slide"]
        G["embedding 0.8<br/>embed_texts on _embedding_text<br/>builds Qdrant PointStruct"]
        H["upsert 0.9-1.0<br/>create_point_id uuid5 record_id<br/>upload_points"]
        E --> F --> G --> H
    end

    subgraph External["External Services"]
        GEM["Google Gemini<br/>gemini-3.5-flash-lite<br/>-> gemini-3.1-flash-lite<br/>-> gemma-4-26b-a4b-it (fallback chain)"]
        HF[HF Inference API<br/>BAAI/bge-base-en-v1.5]
        QD[(Qdrant<br/>COURSEERA_ALMAX_MULTIMODAL)]
    end

    B --> C
    D -. lazy import .-> E
    F --> GEM
    G --> HF
    H --> QD

    I[use-ingestion-job.ts<br/>GET /api/ingest/id<br/>polls every 1.5s] -. status .-> D
    LOCAL[(local disk<br/>slide images)]
    F -.-> LOCAL

    style QD fill:#c3fae8,stroke:#06b6d4
    style GEM fill:#ffd8a8,stroke:#f59e0b
    style HF fill:#ffd8a8,stroke:#f59e0b
```

**Notes**
- Point IDs are deterministic (`uuid5` of `record_id`) so re-ingestion is idempotent.
- The same HF embedding model (`BAAI/bge-base-en-v1.5`) is used again at query time in the RAG pipeline, keeping the vector space consistent.
- The online path keeps slide images on **local disk only** — it never uploads to the HF private visual dataset (that only happens in the offline path, see below).
- Video/frame ingestion is explicitly out of scope for the online path; it stays in the offline discovery/extraction tooling.

### Offline batch tooling (whole-course processing)

This is **not** a single orchestrated pipeline — `pipeline.py` only covers discovery + extraction. Visual analysis, embedding, and Qdrant/HF upload for whole-course material are separate modules run independently; there is currently no script that chains all of them together end-to-end.

```mermaid
flowchart LR
    P["database/src/pipeline.py<br/>run_extraction_pipeline()<br/>python -m src.pipeline"]
    DISC[discovery.py<br/>discover_lecture_assets]
    EXTR[extraction.py<br/>extract_lecture_content<br/>incl. OpenCV video/frame extraction]
    CSV[("processed/master/*.csv<br/>video_metadata, caption_chunks,<br/>transcripts, slide_manifest")]

    P --> DISC --> EXTR --> CSV

    subgraph Manual["Run separately, not chained by pipeline.py"]
        VIS[visual_analysis.py /<br/>visual_database.py]
        EMB[embedding_client.py /<br/>quiz_discussion_embedding.py]
        QDB[qdrant_db.py /<br/>quiz_discussion_qdrant.py]
        VAQ["visual_asset_qdrant.py<br/>uploads slide/frame images"]
        CDB[caption_databases.py]
    end

    HFDS[(HF private dataset<br/>COURSEERA_ALMAX_VISUALS)]
    QD2[(Qdrant<br/>COURSEERA_ALMAX_MULTIMODAL)]

    CSV -.manual input.-> VIS
    CSV -.manual input.-> EMB
    CSV -.manual input.-> CDB
    VAQ --> HFDS
    QDB --> QD2
    EMB --> QDB
    CDB --> QDB

    style CSV fill:#c3fae8,stroke:#06b6d4
    style HFDS fill:#ffd8a8,stroke:#f59e0b
    style QD2 fill:#c3fae8,stroke:#06b6d4
```

**Notes**
- Run via `python -m src.pipeline` from `backend/database/` (has a `if __name__ == "__main__":` entrypoint) — there is no wrapper CLI script anymore.
- `backend/database/README.md` currently describes `pipeline.py` as coordinating all pipeline stages; that's stale versus the code and shouldn't be trusted as-is.
- The HF private visual dataset (`COURSEERA_ALMAX_VISUALS`) is only ever written to from `visual_asset_qdrant.py`, i.e. only from this offline/batch side, never from the online per-lecture path.

---

## 2. RAG Pipeline

Standalone package at `backend/rag/`, importable by the FastAPI app and runnable independently as a FastMCP server.

```mermaid
flowchart TB
    subgraph Retrieval["Retrieval (retrieval.py)"]
        Q1[query string<br/>from RagService] --> Q2[HuggingFaceEndpointEmbeddings<br/>embed query bge-base-en-v1.5]
        Q2 --> Q3[QdrantVectorStore<br/>similarity_search k=15]
        Q3 --> Q4[_hydrate_payloads<br/>client.retrieve by ids<br/>full payload merge]
        Q4 --> Q5{COHERE_API_KEY set?}
        Q5 -->|yes| Q6[CohereRerank rerank-v3.5<br/>cross-encoder to top_k]
        Q5 -->|no / fails| Q7[Fallback: first top_k<br/>vector-search hits]
        Q6 --> Q8[Standardize + dedupe<br/>segment_id, source_id, modality,<br/>timestamp, excerpt, score]
        Q7 --> Q8
    end

    subgraph Synthesis["Synthesis (synthesis.py)"]
        S1{chunks empty?}
        S2[Zero-confidence<br/>'no evidence' recommendation<br/>no LLM call]
        S3[_format_evidence_block<br/>Segment ID / Source / Excerpt]
        S4[instructor.from_groq<br/>Groq LLM gpt-oss-120b<br/>structured InsightSynthesis]
        S5[Filter hallucinated<br/>cited_segment_ids against chunk_map]
        S6[Build EvidenceSegment list<br/>deterministically from real chunks]
        S7[InsightRecommendation<br/>summary, friction_explanation,<br/>recommended_action, confidence,<br/>requires_human_review=True]

        S1 -->|yes| S2
        S1 -->|no| S3 --> S4 --> S5 --> S6 --> S7
    end

    subgraph External["External / Data"]
        QD[(Qdrant<br/>COURSEERA_ALMAX_MULTIMODAL)]
        COH[Cohere Rerank API]
        GROQ[Groq API]
    end

    subgraph MCP["MCP exposure"]
        M1[setup_server.py<br/>FastMCP tool: generate_insight<br/>standalone entrypoint]
    end

    Q8 --> S1
    Q3 --> QD
    Q6 --> COH
    S4 --> GROQ
    Q8 -.-> M1
    S7 -.-> M1

    style QD fill:#c3fae8,stroke:#06b6d4
    style COH fill:#ffd8a8,stroke:#f59e0b
    style GROQ fill:#ffd8a8,stroke:#f59e0b
    style M1 fill:#eebefa,stroke:#ec4899
```

**Notes**
- Citations are never LLM-generated prose UUIDs — `EvidenceSegment`s are built directly from real retrieval chunks, so cited evidence always points to actual data.
- `setup_server.py` wires `retrieve_and_rerank` → `synthesize_insight` into a single MCP tool (`generate_insight`), runnable standalone via `python rag/setup_server.py`, independent of the FastAPI app.

---

## 3. Backend Orchestration

FastAPI app at `backend/app/`, split into three independently-importable packages: `app/` (API layer), `rag/` (retrieval + synthesis), `database/` (ingestion pipeline + SQL). The API lazily imports the other two.

```mermaid
flowchart LR
    subgraph API["API Layer"]
        MAIN[main.py<br/>FastAPI app, CORS, api_router]
        ROUTES["api/routes/*.py<br/>health, metrics, dashboard,<br/>conversations, rag, ingest<br/>(thin, Depends into services)"]
        CONFIG[core/config.py<br/>Settings pydantic-settings<br/>bridges env vars to rag/database]
        MAIN --> ROUTES
    end

    subgraph Services["Services (business logic)"]
        RAGSVC[RagService<br/>synthesize<br/>synthesize_and_record]
        QDSVC[QdrantService<br/>30s cache, scroll aggregates]
        SUPASVC[SupabaseService<br/>pooled httpx.Client<br/>PostgREST _request]
        INGESTSVC[IngestionJobManager<br/>thread-pool, job.json state]
    end

    subgraph Lazy["Lazy-imported packages"]
        RAGPKG[rag/ package<br/>retrieval.py + synthesis.py]
        DBPKG[database/src package<br/>ingest_service.py]
    end

    subgraph Data["Data Stores"]
        QD[(Qdrant Cloud<br/>COURSEERA_ALMAX_MULTIMODAL)]
        SUPA[(Supabase Postgres<br/>conversations to user_queries to<br/>generated_responses to evidence/<br/>recommendations/feedback)]
        EXT[Groq + Cohere + HF API]
        HFDS[HF private dataset<br/>COURSEERA_ALMAX_VISUALS<br/>slide/frame images]
    end

    ROUTES -->|POST /api/synthesize| RAGSVC
    ROUTES -->|GET /api/metrics| QDSVC
    ROUTES -->|dashboard/conversations| SUPASVC
    ROUTES -->|POST /api/ingest| INGESTSVC
    RAGSVC -.->|save_interaction| SUPASVC

    RAGSVC -. lazy import .-> RAGPKG
    INGESTSVC -. lazy import .-> DBPKG

    QDSVC --> QD
    RAGPKG --> QD
    RAGPKG --> EXT
    SUPASVC --> SUPA
    DBPKG --> QD
    DBPKG -.-> HFDS

    style QD fill:#c3fae8,stroke:#06b6d4
    style SUPA fill:#c3fae8,stroke:#06b6d4
    style EXT fill:#ffd8a8,stroke:#f59e0b
    style HFDS fill:#ffd8a8,stroke:#f59e0b
```

### `POST /api/synthesize` flow

```mermaid
sequenceDiagram
    participant Route as routes/rag.py
    participant Rag as RagService
    participant RagPkg as rag/ package
    participant Supa as SupabaseService
    participant DB as Supabase Postgres

    Route->>Rag: synthesize_and_record(request)
    Rag->>RagPkg: retrieve_and_rerank(query, top_k)
    RagPkg-->>Rag: reranked chunks
    Rag->>RagPkg: synthesize_insight(query, chunks)
    RagPkg-->>Rag: InsightRecommendation
    Rag->>Rag: map to SynthesizeResponse (answer + citations)
    alt no conversation_id given
        Rag->>Supa: create_conversation()
        Supa->>DB: insert conversations row
    end
    Rag->>Supa: save_interaction()
    Supa->>DB: insert user_queries row
    Supa->>DB: insert generated_responses row
    Supa->>DB: bulk-insert retrieval_evidence rows
    Supa->>DB: patch conversations.last_activity_at
    alt downstream failure
        Supa->>DB: rollback query row
    end
    Rag-->>Route: SynthesizeResponse (insight_id, conversation_id, query_id)
```

---

## 4. Client Flow

Next.js 16 App Router app at `frontend/src/`, using TanStack React Query for server state and a shared Axios instance for HTTP.

```mermaid
flowchart TB
    subgraph Shell["App Shell"]
        LOGIN["page.tsx<br/>mock login / continue<br/>-> router.push /dashboard"]
        APPSHELL["(app)/layout.tsx<br/>AppSidebar + ThemeToggle<br/>nav: Dashboard/Ask/Recs/Ingest"]
        LOGIN --> APPSHELL
    end

    subgraph Chat["Chat / Ask (primary RAG client path)"]
        CHATPAGE[chat/page.tsx<br/>ChatProvider]
        CHATSESS["useChatSession<br/>reads id param, sessionStorage,<br/>useConversationMessages"]
        EMPTY[chat-empty-state.tsx<br/>3 hardcoded suggestion<br/>queries biology course]
        BOTTOMBAR[chat-bottombar.tsx<br/>user submits query<br/>optimistic append]
        SYNTH[use-synthesize.ts<br/>POST /api/synthesize]
        RENDER["chat-messages-view.tsx<br/>InsightMessageCard<br/>summary/friction/actions/<br/>citations + CurateButton"]
        CURATE[use-curate-recommendation.ts<br/>POST /api/recommendations]

        CHATPAGE --> CHATSESS --> EMPTY --> BOTTOMBAR --> SYNTH --> RENDER --> CURATE
    end

    subgraph Ingest["Ingest client flow"]
        REGPAGE["register/page.tsx<br/>react-hook-form + AssetUploadSection<br/>auto-guesses asset type"]
        CREATEING[use-create-ingestion.ts<br/>POST /api/ingest multipart]
        POLLING["use-ingestion-job.ts<br/>GET /api/ingest/id<br/>polls 1.5s until terminal"]
        PROGRESSUI["ingestion-progress.tsx<br/>renders stage / percent"]

        REGPAGE --> CREATEING --> POLLING --> PROGRESSUI
    end

    subgraph DashRec["Dashboard / Recommendations"]
        DASH["dashboard/page.tsx<br/>useMetrics + useDashboardSummary<br/>+ useIngestionJobs (parallel)"]
        REC["recommendations/page.tsx<br/>GET /api/recommendations<br/>review via /api/review-feedback"]
    end

    subgraph Backend["Backend API"]
        API["FastAPI backend /api/*<br/>see Backend Orchestration diagram"]
    end

    APPSHELL --> CHATPAGE
    APPSHELL --> REGPAGE
    APPSHELL --> DASH
    APPSHELL --> REC

    SYNTH --> API
    CREATEING --> API
    POLLING --> API
    DASH --> API
    REC --> API

    style API fill:#ffd8a8,stroke:#f59e0b
```

**Notes**
- `api/axios.ts`: shared instance, `baseURL` from `NEXT_PUBLIC_API_URL`, 5-minute timeout (for long LLM/ingestion calls), request/response logging interceptors.
- All server state is managed via TanStack React Query (cache invalidation on mutation, e.g. invalidating `["conversations"]` after a successful synthesize call).
- `use-ingestion-jobs.ts` (list hook, plural) is shared by both the register page's "Recent ingestions" panel and the dashboard's Processing Monitor.
