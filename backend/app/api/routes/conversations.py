from typing import Any

from fastapi import APIRouter, Depends, Query

from app.schemas import ConversationResponse
from app.services.supabase_service import SupabaseService, get_supabase_service


router = APIRouter(prefix="/api", tags=["conversations"])


@router.get("/conversations", response_model=list[ConversationResponse])
def conversations(
    limit: int = Query(default=50, ge=1, le=500),
    service: SupabaseService = Depends(get_supabase_service),
) -> list[ConversationResponse]:
    # Lists recent conversations so the frontend can render the chat history sidebar.
    return service.list_conversations(limit=limit)


@router.get("/conversations/{conversation_id}/messages", response_model=list[dict])
def conversation_messages(
    conversation_id: str,
    service: SupabaseService = Depends(get_supabase_service),
) -> list[dict[str, Any]]:
    # Returns the full message transcript for one conversation so the frontend can replay the thread.
    return service.get_conversation_messages(conversation_id)
