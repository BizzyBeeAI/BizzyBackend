from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query

from backend.advisor.advisor import advisor_bee
from backend.audit.store import (
    build_audit_event,
    get_audit_event,
    list_audit_events,
    persist_audit_event,
)
from backend.models.agent import QueryRequest, QueryResponse
from backend.orchestration.queen import run_specialists
from backend.security.guard import evaluate
from dotenv import load_dotenv

load_dotenv()  # Loads environment variables from .env file
router = APIRouter(prefix="/api/v1", tags=["bizzybee"])


@router.get("/business-health")
def business_health() -> dict[str, object]:
    return {
        "score": 78,
        "priority_issues": ["stock_risk", "overdue_invoices", "open_customer_opportunities"],
    }


@router.post("/query", response_model=QueryResponse)
def query(payload: QueryRequest) -> QueryResponse:
    workflow_id = str(uuid4())
    invoked_agents: list[str] = []
    specialist_results = []
    advisor_result = None
    guard_decision = "not_evaluated"
    approval_required = False

    try:
        invoked_agents, specialist_results = run_specialists(payload.question)
        advisor_result = advisor_bee(payload.question, specialist_results)
        guard_decision, approval_required = evaluate([*specialist_results, advisor_result])
    except Exception as error:
        event = build_audit_event(
            workflow_id,
            payload.user,
            specialist_results,
            guard_decision,
            invoked_agents=invoked_agents,
            advisor_result=advisor_result,
            approval_required=approval_required,
            query=payload.question,
            status="failed",
            failure_type=type(error).__name__,
        )
        persist_audit_event(event)
        raise

    event = build_audit_event(
        workflow_id,
        payload.user,
        specialist_results,
        guard_decision,
        invoked_agents=invoked_agents,
        advisor_result=advisor_result,
        approval_required=approval_required,
        query=payload.question,
        status="completed",
    )
    persist_audit_event(event)

    return QueryResponse(
        workflow_id=workflow_id,
        invoked_agents=invoked_agents,
        specialist_results=specialist_results,
        advisor_result=advisor_result,
        guard_decision=guard_decision,
        approval_required=approval_required,
    )


@router.get("/audit")
def recent_audit_history(
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, object]:
    records = list_audit_events(limit)
    return {"items": records, "count": len(records)}


@router.get("/audit/{trace_id}")
def audit_by_trace_id(trace_id: str) -> dict[str, object]:
    event = get_audit_event(trace_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Audit trace not found")
    return event
