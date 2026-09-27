from __future__ import annotations

from fastapi.testclient import TestClient

from backend.api import routes
from backend.audit.store import (
    build_audit_event,
    get_audit_event,
    list_audit_events,
    persist_audit_event,
)
from backend.main import app
from backend.models.agent import AgentResponse, AgentStatus, Evidence, RecommendedAction, RiskLevel


client = TestClient(app)


def agent_result(
    agent: str,
    status: AgentStatus = AgentStatus.SUCCESS,
    actions: list[RecommendedAction] | None = None,
) -> AgentResponse:
    return AgentResponse(
        agent=agent,
        status=status,
        summary=f"{agent} result",
        evidence=[Evidence(metric="overdue_invoice_count", value=2)],
        confidence=0.9,
        recommended_actions=actions or [],
    )


def test_persists_and_retrieves_query_with_unique_trace_ids(tmp_path) -> None:
    database = tmp_path / "audit.sqlite3"
    specialist = agent_result("finance")
    advisor = agent_result(
        "advisor",
        actions=[
            RecommendedAction(
                type="review_financial_exposure [evidence: finance.overdue_invoice_count]",
                risk_level=RiskLevel.GREEN,
            )
        ],
    )

    first = build_audit_event(
        "trace-1",
        "owner@example.com",
        [specialist],
        "approval_required: prepare_invoice_reminders: AMBER - approval required",
        invoked_agents=["finance"],
        advisor_result=advisor,
        approval_required=True,
        query="Review invoice for owner@example.com",
    )
    second = build_audit_event(
        "trace-2",
        "owner@example.com",
        [specialist],
        "allowed: no actions were proposed.",
        invoked_agents=["finance"],
        query="Summarize overdue invoices",
    )
    persist_audit_event(first, database)
    persist_audit_event(second, database)

    stored = get_audit_event("trace-1", database)
    recent = list_audit_events(db_path=database)

    assert stored is not None
    assert stored["trace_id"] == "trace-1"
    assert stored["workflow_id"] == "trace-1"
    assert stored["timestamp"]
    assert "user" not in stored
    assert "[REDACTED_EMAIL]" in stored["query"]
    assert stored["advisor_result"]["recommended_actions"][0]["evidence_references"] == [
        "finance.overdue_invoice_count"
    ]
    assert {record["trace_id"] for record in recent} == {"trace-1", "trace-2"}


def test_records_failed_agents_guard_explanations_and_proposed_actions(tmp_path) -> None:
    failed_specialist = agent_result("customer", status=AgentStatus.FAILED)
    advisor = agent_result(
        "advisor",
        actions=[
            RecommendedAction(
                type="send_customer_message [evidence: customer.unanswered_leads]",
                risk_level=RiskLevel.GREEN,
            )
        ],
    )
    decision = (
        "approval_required: send_customer_message: AMBER - human approval is required"
    )
    event = build_audit_event(
        "trace-failed-agent",
        "unused-owner-id",
        [failed_specialist],
        decision,
        invoked_agents=["customer"],
        advisor_result=advisor,
        approval_required=True,
        query="Follow up with customers",
    )
    persist_audit_event(event, tmp_path / "audit.sqlite3")

    stored = get_audit_event("trace-failed-agent", tmp_path / "audit.sqlite3")

    assert stored is not None
    assert stored["specialist_results"][0]["status"] == "failed"
    assert stored["guard"]["decision"] == decision
    assert stored["guard"]["approval_required"] is True
    assert stored["guard"]["action_explanations"] == [
        {
            "action": "send_customer_message",
            "classification": "AMBER",
            "reason": "human approval is required",
        }
    ]
    assert stored["proposed_actions"][0]["status"] == "proposed"
    assert stored["proposed_actions"][0]["executed"] is False
    assert stored["executed_actions"] == []


def test_redacts_credentials_in_structured_evidence(tmp_path) -> None:
    result = agent_result("finance")
    result.evidence.append(
        Evidence(
            metric="configuration",
            value={"api_key": "hidden-key", "status": "available"},
        )
    )
    event = build_audit_event("trace-redaction", "unused", [result], "allowed")

    assert event["specialist_results"][0]["evidence"][1]["value"] == {
        "api_key": "[REDACTED_CREDENTIAL]",
        "status": "available",
    }
    persist_audit_event(event, tmp_path / "audit.sqlite3")
    stored = get_audit_event("trace-redaction", tmp_path / "audit.sqlite3")
    assert stored is not None
    assert "hidden-key" not in str(stored)


def test_audit_endpoints_return_trace_and_recent_history(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("BIZZYBEE_AUDIT_DB", str(tmp_path / "route-audit.sqlite3"))
    monkeypatch.setattr(
        routes,
        "run_specialists",
        lambda question: (["sales"], [agent_result("sales")]),
    )
    monkeypatch.setattr(routes, "advisor_bee", lambda question, results: agent_result("advisor"))
    monkeypatch.setattr(routes, "evaluate", lambda results: ("allowed: read-only", False))

    first_response = client.post("/api/v1/query", json={"question": "Sales summary"})
    second_response = client.post("/api/v1/query", json={"question": "Another sales summary"})

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    first_trace = first_response.json()["workflow_id"]
    second_trace = second_response.json()["workflow_id"]
    assert first_trace != second_trace

    trace_response = client.get(f"/api/v1/audit/{first_trace}")
    recent_response = client.get("/api/v1/audit?limit=2")

    assert trace_response.status_code == 200
    assert trace_response.json()["trace_id"] == first_trace
    assert recent_response.status_code == 200
    assert recent_response.json()["count"] == 2
    assert {item["trace_id"] for item in recent_response.json()["items"]} == {
        first_trace,
        second_trace,
    }


def test_failed_query_pipeline_still_writes_audit_record(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("BIZZYBEE_AUDIT_DB", str(tmp_path / "failed-query.sqlite3"))
    monkeypatch.setattr(
        routes,
        "run_specialists",
        lambda question: (_ for _ in ()).throw(RuntimeError("internal detail")),
    )
    failing_client = TestClient(app, raise_server_exceptions=False)

    response = failing_client.post(
        "/api/v1/query",
        json={"question": "Check business health", "user": "owner@example.com"},
    )

    assert response.status_code == 500
    records = list_audit_events(db_path=tmp_path / "failed-query.sqlite3")
    assert len(records) == 1
    assert records[0]["status"] == "failed"
    assert records[0]["failure_type"] == "RuntimeError"
    assert "internal detail" not in str(records[0])
    assert "user" not in records[0]