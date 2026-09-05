"""Aggregates every route module into a single API router."""
from fastapi import APIRouter

from app.api.routes import conversations, dashboard, health, metrics, rag


api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(metrics.router)
api_router.include_router(dashboard.router)
api_router.include_router(conversations.router)
api_router.include_router(rag.router)
