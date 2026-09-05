# Verifies the health endpoint responds ok with config flags so monitoring has a reliable probe.
def test_health_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "qdrant_collection" in body
    assert "supabase_configured" in body
