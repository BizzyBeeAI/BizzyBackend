from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter

from backend.advisor.advisor import advisor_bee
from backend.audit.store import build_audit_event
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
    invoked_agents, specialist_results = run_specialists(payload.question)
    advisor_result = advisor_bee(payload.question, specialist_results)

    guard_decision, approval_required = evaluate([*specialist_results, advisor_result])
    _ = build_audit_event(workflow_id, payload.user, [*specialist_results, advisor_result], guard_decision)

    return QueryResponse(
        workflow_id=workflow_id,
        invoked_agents=invoked_agents,
        specialist_results=specialist_results,
        advisor_result=advisor_result,
        guard_decision=guard_decision,
        approval_required=approval_required,
    )
