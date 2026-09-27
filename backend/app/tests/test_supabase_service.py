import json

from fastapi import HTTPException
import httpx
import pytest

from app.core.config import Settings
from app.schemas import EvidenceSaveItem, InteractionSaveRequest
from app.integrations.supabase.postgrest_client import PostgrestClient
from app.services.supabase_service import SupabaseService


def _service_with_transport(handler) -> SupabaseService:
    supabase_url = "https://example.supabase.co"
    secret_key = "test-key"
    settings = Settings(supabase_url=supabase_url, supabase_secret_key=secret_key)
    service = SupabaseService(settings)
    if service._postgrest._client is not None:
        service._postgrest._client.close()
    service._postgrest._client = httpx.Client(
        base_url=supabase_url,
        headers={
            "apikey": secret_key,
            "Authorization": f"Bearer {secret_key}",
            "Content-Type": "application/json",
        },
        transport=httpx.MockTransport(handler),
    )
    return service


def test_postgrest_client_rejects_unconfigured_requests():
    client = PostgrestClient(Settings(supabase_url=None, supabase_secret_key=None))

    with pytest.raises(HTTPException) as exc_info:
        client.request("GET", "/rest/v1/conversations")

    assert exc_info.value.status_code == 503


def test_save_interaction_persists_deduplicated_evidence():
    calls = []
    evidence_payload = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        if request.url.path.endswith("/user_queries"):
            return httpx.Response(201, json=[{"query_id": "query-1"}])
        if request.url.path.endswith("/generated_responses"):
            return httpx.Response(201, json=[{"response_id": "response-1"}])
        if request.url.path.endswith("/retrieval_evidence"):
            evidence_payload.extend(json.loads(request.content))
            return httpx.Response(201)
        return httpx.Response(204)

    service = _service_with_transport(handler)
    try:
        result = service.save_interaction(
            InteractionSaveRequest(
                conversation_id="conversation-1",
                query_text="Why is this difficult?",
                generated_answer="Try this example.",
                evidence=[
                    EvidenceSaveItem(point_id="point-1", content_type="caption", text="first"),
                    EvidenceSaveItem(point_id="point-1", content_type="caption", text="duplicate"),
                    EvidenceSaveItem(point_id="point-2", content_type="slide", text="second"),
                ],
            )
        )
    finally:
        service._postgrest._client.close()

    assert result.query_id == "query-1"
    assert result.response_id == "response-1"
    assert result.evidence_count == 2
    assert [record["qdrant_record_id"] for record in evidence_payload] == ["point-1", "point-2"]
    assert [record["retrieval_rank"] for record in evidence_payload] == [1, 3]
    assert calls == [
        ("POST", "/rest/v1/user_queries"),
        ("POST", "/rest/v1/generated_responses"),
        ("POST", "/rest/v1/retrieval_evidence"),
        ("PATCH", "/rest/v1/conversations"),
    ]


def test_save_interaction_rolls_back_query_when_response_insert_fails():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        if request.method == "POST" and request.url.path.endswith("/user_queries"):
            return httpx.Response(201, json=[{"query_id": "query-1"}])
        if request.method == "POST" and request.url.path.endswith("/generated_responses"):
            return httpx.Response(500, text="database error")
        return httpx.Response(204)

    service = _service_with_transport(handler)
    try:
        with pytest.raises(HTTPException) as exc_info:
            service.save_interaction(
                InteractionSaveRequest(
                    conversation_id="conversation-1",
                    query_text="Question",
                    generated_answer="Answer",
                )
            )
    finally:
        service._postgrest._client.close()

    assert exc_info.value.status_code == 500
    assert calls == [
        ("POST", "/rest/v1/user_queries"),
        ("POST", "/rest/v1/generated_responses"),
        ("DELETE", "/rest/v1/user_queries"),
    ]