from __future__ import annotations

from backend.models.agent import AgentResponse, AgentStatus, Evidence, RecommendedAction, RiskLevel
from backend.tools import demo_data


def sales_bee() -> AgentResponse:
    sales = demo_data.load_sales()
    latest = sales[-1] if sales else {"revenue": "0", "quantity": "0", "product": "n/a"}
    return AgentResponse(
        agent="sales",
        status=AgentStatus.SUCCESS,
        summary="Sales trend indicates a week-on-week decline.",
        evidence=[
            Evidence(metric="latest_revenue", value=float(latest["revenue"])),
            Evidence(metric="latest_quantity", value=int(latest["quantity"])),
            Evidence(metric="focus_product", value=latest["product"]),
        ],
        confidence=0.86,
        recommended_actions=[RecommendedAction(type="review_pricing", risk_level=RiskLevel.GREEN)],
    )


def customer_bee() -> AgentResponse:
    # 1. Execute SQL analytics on CSVs via DuckDB
    complaint_records = demo_data.analyze_customer_complaints()
    enquiry_records = demo_data.analyze_customer_enquiries_sla()

    # 2. Extract top product defect insights
    top_defect = complaint_records[0] if complaint_records else {}
    top_product = top_defect.get("product_name", "N/A")
    top_rate = top_defect.get("complaint_rate_pct", 0.0)
    top_refunds = top_defect.get("total_refund_sgd", 0.0)
    previous_period_complaints = top_defect.get("previous_period_complaints")
    current_period_complaints = top_defect.get("current_period_complaints")
    complaint_change_pct = top_defect.get("complaint_change_pct")
    previous_period_rate = top_defect.get("previous_period_complaint_rate_pct")
    current_period_rate = top_defect.get("current_period_complaint_rate_pct")
    top_complaint_reason = top_defect.get("top_complaint_reason")

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
    if previous_period_complaints is not None and current_period_complaints is not None:
        evidence.extend(
            [
                Evidence(
                    metric="previous_period_complaints",
                    value=previous_period_complaints,
                ),
                Evidence(
                    metric="current_period_complaints",
                    value=current_period_complaints,
                ),
                Evidence(
                    metric="complaint_count_change_pct",
                    value=complaint_change_pct,
                ),
                Evidence(
                    metric="previous_period_complaint_rate_pct",
                    value=previous_period_rate,
                ),
                Evidence(
                    metric="current_period_complaint_rate_pct",
                    value=current_period_rate,
                ),
                Evidence(
                    metric="previous_period_start",
                    value=top_defect.get("previous_period_start"),
                ),
                Evidence(
                    metric="previous_period_end",
                    value=top_defect.get("previous_period_end"),
                ),
                Evidence(
                    metric="current_period_start",
                    value=top_defect.get("current_period_start"),
                ),
                Evidence(
                    metric="current_period_end",
                    value=top_defect.get("current_period_end"),
                ),
            ]
        )
        if top_complaint_reason:
            evidence.extend(
                [
                    Evidence(
                        metric="top_complaint_reason",
                        value=top_complaint_reason,
                    ),
                    Evidence(
                        metric="previous_period_top_reason_complaints",
                        value=top_defect.get("previous_period_reason_complaints", 0),
                    ),
                    Evidence(
                        metric="current_period_top_reason_complaints",
                        value=top_defect.get("current_period_reason_complaints", 0),
                    ),
                ]
            )

    # 5. Formulate human-readable summary
    summary = (
        f"Customer analysis reveals highest defect complaint rate in '{top_product}' "
        f"({top_rate}% of units sold affected, totaling SGD {top_refunds:.2f} refunded). "
        f"Additionally, {high_intent_missed} high-intent customer enquiries remain unanswered."
    )
    if previous_period_complaints is not None and current_period_complaints is not None:
        comparison = (
            f"Across {top_defect['previous_period_start']} to {top_defect['previous_period_end']} "
            f"versus {top_defect['current_period_start']} to {top_defect['current_period_end']}, "
            f"complaints for '{top_product}' changed from {previous_period_complaints} "
            f"to {current_period_complaints}"
        )
        if complaint_change_pct is None:
            comparison += "; a percentage change is unavailable because the previous period had no complaints."
        else:
            comparison += f" ({complaint_change_pct}% change)."
        if previous_period_rate is not None and current_period_rate is not None:
            comparison += (
                f" The affected-unit complaint rate changed from {previous_period_rate}% "
                f"to {current_period_rate}%."
            )
        if top_complaint_reason:
            comparison += (
                f" The leading current-period reason was '{top_complaint_reason}' "
                f"({top_defect.get('current_period_reason_complaints', 0)} reports)."
            )
        summary += " " + comparison

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


def finance_bee() -> AgentResponse:
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


def inventory_bee() -> AgentResponse:
    rows = demo_data.load_inventory()
    first = rows[0] if rows else {"current_stock": "0", "reorder_level": "0", "product": "n/a"}
    current_stock = int(first["current_stock"])
    reorder_level = int(first["reorder_level"])
    needs_reorder = current_stock <= reorder_level

    return AgentResponse(
        agent="inventory",
        status=AgentStatus.SUCCESS,
        summary="Inventory is below threshold." if needs_reorder else "Inventory level is healthy.",
        evidence=[
            Evidence(metric="product", value=first["product"]),
            Evidence(metric="current_stock", value=current_stock),
            Evidence(metric="reorder_level", value=reorder_level),
        ],
        confidence=0.91,
        recommended_actions=[
            RecommendedAction(
                type="prepare_purchase_order",
                risk_level=RiskLevel.AMBER if needs_reorder else RiskLevel.GREEN,
            )
        ],
    )
