from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_health_endpoint() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_inventory_only_query_routes_to_inventory_bee() -> None:
    payload = {"question": "How many Product A units are left?", "language": "en", "user": "owner"}
    response = client.post("/api/v1/query", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["invoked_agents"] == ["inventory"]
    assert body["guard_decision"] == "approval_required"
    assert body["approval_required"] is True


def test_cross_functional_query_returns_specialist_contract() -> None:
    payload = {"question": "Why did sales fall this week?", "language": "en", "user": "owner"}
    response = client.post("/api/v1/query", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert "sales" in body["invoked_agents"]
    assert "advisor_result" in body
    assert body["advisor_result"]["agent"] == "advisor"

    specialist = body["specialist_results"][0]
    assert set(specialist).issuperset(
        {"agent", "status", "summary", "evidence", "confidence", "recommended_actions"}
    )
