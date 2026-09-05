from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import get_settings
from app.core.logging import setup_logging


settings = get_settings()
setup_logging(settings.log_level)

app = FastAPI(
    title="Coursera Multimodal Intelligence Backend",
    description="Backend API for RAG retrieval/synthesis orchestration and persistence.",
    version="0.3.0",
    # Interactive API docs are disabled (no Swagger UI, ReDoc, or OpenAPI schema route).
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
