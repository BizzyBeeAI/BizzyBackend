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
    assert body["guard_decision"].startswith("approval_required:")
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


def test_customer_complaints_query_works_with_bundled_demo_data_and_no_api_key(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("BIZZYBEE_AUDIT_DB", str(tmp_path / "customer-query-audit.sqlite3"))

    response = client.post(
        "/api/v1/query",
        json={"question": "Why did customer complaints increase?"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["invoked_agents"] == ["customer"]
    assert body["specialist_results"][0]["agent"] == "customer"
    assert body["specialist_results"][0]["status"] == "success"
    assert body["advisor_result"]["agent"] == "advisor"
    specialist = body["specialist_results"][0]
    assert "complaints for 'Product A' changed from 2 to 6 (200.0% change)" in specialist["summary"]
    assert "packaging_damage" in specialist["summary"]
    evidence = {item["metric"]: item["value"] for item in specialist["evidence"]}
    assert evidence["previous_period_complaints"] == 2
    assert evidence["current_period_complaints"] == 6
    assert evidence["complaint_count_change_pct"] == 200.0
    assert evidence["previous_period_complaint_rate_pct"] == 2.8571
    assert evidence["current_period_complaint_rate_pct"] == 10.0
    assert evidence["top_complaint_reason"] == "packaging_damage"
    assert evidence["previous_period_start"] == "2026-06-01"
    assert evidence["previous_period_end"] == "2026-06-07"
    assert evidence["current_period_start"] == "2026-06-08"
    assert evidence["current_period_end"] == "2026-06-14"
