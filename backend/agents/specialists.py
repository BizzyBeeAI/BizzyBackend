from __future__ import annotations

from backend.agents.inventory import inventory_bee
from backend.agents.sales import sales_bee
from backend.models.agent import AgentResponse, AgentStatus, Evidence, RecommendedAction, RiskLevel
from backend.tools import demo_data

__all__ = ["customer_bee", "finance_bee", "inventory_bee", "sales_bee"]


def customer_bee(question: str | None = None) -> AgentResponse:
    # 1. Execute SQL analytics on CSVs via DuckDB
    complaint_records = demo_data.analyze_customer_complaints()
    enquiry_records = demo_data.analyze_customer_enquiries_sla()

    # 2. Extract top product defect insights
    top_defect = complaint_records[0] if complaint_records else {}
    top_product = top_defect.get("product_name", "N/A")
    top_rate = top_defect.get("complaint_rate_pct", 0.0)
    top_refunds = top_defect.get("total_refund_sgd", 0.0)

    # 3. Extract customer enquiry SLA metrics
    unanswered_leads = sum(r.get("unanswered_leads", 0) for r in enquiry_records)
    high_intent_missed = sum(r.get("high_intent_missed", 0) for r in enquiry_records)

    # 4. Build structured evidence list
    evidence = [
        Evidence(metric="highest_defect_product", value=top_product),
        Evidence(metric="highest_complaint_rate_pct", value=top_rate),
        Evidence(metric="total_refund_financial_impact_sgd", value=top_refunds),
        Evidence(metric="unanswered_customer_leads", value=unanswered_leads),
        Evidence(metric="high_intent_missed_opportunities", value=high_intent_missed),
    ]

    # 5. Formulate human-readable summary
    summary = (
        f"Customer analysis reveals highest defect complaint rate in '{top_product}' "
        f"({top_rate}% of units sold affected, totaling SGD {top_refunds:.2f} refunded). "
        f"Additionally, {high_intent_missed} high-intent customer enquiries remain unanswered."
    )

    return AgentResponse(
        agent="customer",
        status=AgentStatus.SUCCESS,
        summary=summary,
        evidence=evidence,
        confidence=0.92,
        recommended_actions=[
            RecommendedAction(type="prepare_customer_follow_up", risk_level=RiskLevel.AMBER),
            RecommendedAction(type="review_supplier_quality_defect", risk_level=RiskLevel.AMBER),
        ],
    )


def finance_bee(question: str | None = None) -> AgentResponse:
    invoices = demo_data.load_invoices()
    overdue = [item for item in invoices if item.get("status", "").lower() == "overdue"]
    overdue_amount = sum(float(item["amount"]) for item in overdue) if overdue else 0.0
    return AgentResponse(
        agent="finance",
        status=AgentStatus.SUCCESS,
        summary="Overdue invoices are affecting cash flow.",
        evidence=[
            Evidence(metric="overdue_invoice_count", value=len(overdue)),
            Evidence(metric="overdue_amount_sgd", value=overdue_amount),
        ],
        confidence=0.89,
        recommended_actions=[RecommendedAction(type="prepare_invoice_reminders", risk_level=RiskLevel.AMBER)],
    )
