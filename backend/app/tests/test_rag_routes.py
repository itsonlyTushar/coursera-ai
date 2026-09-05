from app.main import app
from app.schemas import (
    ConversationResponse,
    InteractionSaveResponse,
    SynthesizeResponse,
)
from app.services.rag_service import get_rag_service
from app.services.supabase_service import get_supabase_service


class FakeRagService:
    # Stands in for the real RAG service so route tests don't call Qdrant/Groq.
    def synthesize(self, request):
        # Returns a fixed synthesis result so the route's persistence/wiring can be asserted deterministically.
        response = SynthesizeResponse(
            insight_id="",
            conversation_id="",
            query_id="",
            answer_text="Summary: ok",
            recommended_action="Add a worked example.",
            citations=[],
            confidence=0.9,
            status="completed",
        )
        return response, [], response.answer_text


class FakeSupabaseService:
    # Stands in for persistence so route tests run without a live Supabase.
    def __init__(self):
        # Tracks how many conversations were created so tests can assert create-vs-reuse behavior.
        self.created = 0

    def create_conversation(self, request):
        # Records and returns a fixed conversation so the route's "create when missing" path is observable.
        self.created += 1
        return ConversationResponse(conversation_id="conv-1", session_id=request.session_id)

    def save_interaction(self, request):
        # Returns fixed ids so the test can assert the route copies them onto the response.
        return InteractionSaveResponse(
            conversation_id=request.conversation_id,
            query_id="query-1",
            response_id="resp-1",
            evidence_count=len(request.evidence),
        )

    def list_curated_recommendations(self, limit, offset):
        # Returns one canned recommendation so the list route can be asserted without a database.
        return [{"recommendation_id": "rec-1", "recommendation_text": "x"}]


# Asserts synthesize creates a conversation when none is given and wires the saved ids onto the response.
def test_synthesize_wires_ids_and_creates_conversation(client):
    fake_supabase = FakeSupabaseService()
    app.dependency_overrides[get_rag_service] = lambda: FakeRagService()
    app.dependency_overrides[get_supabase_service] = lambda: fake_supabase

    resp = client.post("/api/synthesize", json={"query": "why is quiz 3 hard?"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["insight_id"] == "resp-1"
    assert body["conversation_id"] == "conv-1"
    assert body["query_id"] == "query-1"
    assert body["recommended_action"] == "Add a worked example."
    assert fake_supabase.created == 1


# Asserts synthesize reuses a supplied conversation_id instead of creating a new conversation.
def test_synthesize_reuses_existing_conversation(client):
    fake_supabase = FakeSupabaseService()
    app.dependency_overrides[get_rag_service] = lambda: FakeRagService()
    app.dependency_overrides[get_supabase_service] = lambda: fake_supabase

    resp = client.post(
        "/api/synthesize",
        json={"query": "q", "conversation_id": "existing"},
    )

    assert resp.status_code == 200
    assert resp.json()["conversation_id"] == "existing"
    assert fake_supabase.created == 0


# Asserts the recommendations list route returns the service's rows so the page has data to render.
def test_list_recommendations(client):
    app.dependency_overrides[get_supabase_service] = lambda: FakeSupabaseService()

    resp = client.get("/api/recommendations", params={"limit": 5})

    assert resp.status_code == 200
    assert resp.json()[0]["recommendation_id"] == "rec-1"
