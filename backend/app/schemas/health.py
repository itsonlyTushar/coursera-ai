from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    qdrant_url_configured: bool
    qdrant_collection: str
    embedding_model: str
    supabase_configured: bool = False
