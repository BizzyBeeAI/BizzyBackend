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
    enquiries = demo_data.load_customer_enquiries()
    open_count = sum(1 for item in enquiries if item.get("status", "").lower() != "closed")
    return AgentResponse(
        agent="customer",
        status=AgentStatus.SUCCESS,
        summary="Open customer opportunities need follow-up.",
        evidence=[Evidence(metric="open_enquiries", value=open_count)],
        confidence=0.82,
        recommended_actions=[RecommendedAction(type="prepare_customer_follow_up", risk_level=RiskLevel.AMBER)],
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
