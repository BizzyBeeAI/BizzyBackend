from __future__ import annotations

import math
from typing import Any

from backend.models.agent import AgentResponse, AgentStatus, Evidence, RecommendedAction, RiskLevel


def _evidence_map(result: AgentResponse) -> dict[str, object]:
    return {item.metric: item.value for item in result.evidence}


def _sales_inventory_link(
    sales: AgentResponse,
    inventory: AgentResponse,
) -> tuple[str, list[Evidence], float] | None:
    sales_evidence = _evidence_map(sales)
    inventory_evidence = _evidence_map(inventory)
    sales_product = sales_evidence.get("focus_product_id")
    inventory_product = inventory_evidence.get("product_id")
    if not sales_product or sales_product != inventory_product:
        return None

    decline = sales_evidence.get("focus_product_revenue_change_sgd")
    lost_revenue = inventory_evidence.get("recent_lost_revenue_sgd")
    if not isinstance(decline, (int, float)) or not isinstance(lost_revenue, (int, float)):
        return None

    decline_amount = abs(float(decline))
    explained_pct = 0.0 if not decline_amount else round(float(lost_revenue) / decline_amount * 100, 2)
    same_period = sales_evidence.get("recent_period") == inventory_evidence.get("recent_period")
    last_sale = sales_evidence.get("focus_product_last_sale_date")
    first_unfulfilled = inventory_evidence.get("first_recent_unfulfilled_date")
    timeline_aligned = bool(last_sale and first_unfulfilled and str(first_unfulfilled) > str(last_sale))
    amount_aligned = abs(float(lost_revenue) - decline_amount) <= 0.01

    relationship = "strongly_supported" if same_period and timeline_aligned and amount_aligned else "supported"
    wording = "strongly supports" if relationship == "strongly_supported" else "supports"
    summary = (
        f"The combined evidence {wording} a stockout-related explanation for the sales decline. "
        f"{sales_product} contributed SGD {decline_amount:,.2f} of lost revenue while inventory records show "
        f"SGD {float(lost_revenue):,.2f} of unfulfilled demand in the same analysis"
        f"{' period' if same_period else ''} ({explained_pct:.1f}% of the product revenue gap). "
        "This is evidence-based correlation, not proof of causation."
    )
    evidence = [
        Evidence(metric="linked_product_id", value=sales_product),
        Evidence(metric="sales_decline_sgd", value=decline_amount, unit="SGD"),
        Evidence(metric="stockout_lost_revenue_sgd", value=float(lost_revenue), unit="SGD"),
        Evidence(metric="stockout_explained_decline_pct", value=explained_pct, unit="percent"),
        Evidence(metric="relationship_assessment", value=relationship),
        Evidence(metric="period_aligned", value=same_period),
        Evidence(metric="timeline_aligned", value=timeline_aligned),
        Evidence(metric="amount_aligned", value=amount_aligned),
    ]
    confidence = round(min(sales.confidence, inventory.confidence), 2)
    return summary, evidence, confidence


def _detail_rows(evidence: dict[str, object], metric: str) -> list[dict[str, Any]]:
    value = evidence.get(metric)
    if not isinstance(value, list):
        return []
    return [row for row in value if isinstance(row, dict)]


def _top_seller_stock_risk(
    sales: AgentResponse,
    inventory: AgentResponse,
) -> tuple[str, list[Evidence], RecommendedAction] | None:
    sales_evidence = _evidence_map(sales)
    current_rows = _detail_rows(sales_evidence, "top_product_details")
    baseline_rows = _detail_rows(sales_evidence, "baseline_top_product_details")
    candidates: dict[object, dict[str, Any]] = {}
    for row in current_rows:
        candidates[row.get("product_id")] = {**row, "current_top_seller": True}
    for row in baseline_rows:
        product_id = row.get("product_id")
        candidates[product_id] = {
            **candidates.get(product_id, {}),
            **row,
            "baseline_top_seller": True,
        }
    sales_rows = list(candidates.values())
    stock_rows = _detail_rows(_evidence_map(inventory), "top_seller_stock_details")
    if not stock_rows:
        stock_rows = _detail_rows(_evidence_map(inventory), "stock_risk_details")
    stock_by_product = {row.get("product_id"): row for row in stock_rows}
    linked = []
    for sale in sales_rows:
        stock = stock_by_product.get(sale.get("product_id"))
        if stock and stock.get("risk") != "ok":
            linked.append({**sale, **stock})
    if not linked:
        return None

    product_ids = [str(row["product_id"]) for row in linked]
    summary = (
        f"{len(linked)} of the {len(sales_rows)} current or baseline top revenue products are at stock risk: "
        f"{', '.join(product_ids)}. These products should be prioritised because shortages may interrupt "
        "revenue from current best sellers."
    )
    evidence = [Evidence(metric="top_sellers_at_stock_risk", value=linked)]
    action = RecommendedAction(
        type="prioritise_top_seller_replenishment",
        risk_level=RiskLevel.GREEN,
        reason="The products are both top revenue generators and unable to cover supplier lead time.",
        parameters={"product_ids": product_ids},
    )
    return summary, evidence, action


def _high_value_low_velocity(
    sales: AgentResponse,
    inventory: AgentResponse,
) -> tuple[str, list[Evidence], RecommendedAction] | None:
    velocity_rows = _detail_rows(_evidence_map(sales), "product_velocity_details")
    value_rows = _detail_rows(_evidence_map(inventory), "inventory_value_details")
    if not velocity_rows or not value_rows:
        return None

    sample_size = min(len(velocity_rows), len(value_rows))
    cutoff = max(1, math.ceil(sample_size / 2))
    low_velocity_ids = {
        row.get("product_id")
        for row in sorted(velocity_rows, key=lambda row: (float(row.get("avg_daily_units", 0)), row.get("product_id")))[
            :cutoff
        ]
    }
    high_value_rows = sorted(
        value_rows,
        key=lambda row: (-float(row.get("stock_value_sgd", 0)), row.get("product_id")),
    )[:cutoff]
    velocity_by_product = {row.get("product_id"): row for row in velocity_rows}
    linked = [
        {**row, **velocity_by_product[row.get("product_id")]}
        for row in high_value_rows
        if row.get("product_id") in low_velocity_ids
    ][:5]
    if not linked:
        return None

    product_ids = [str(row["product_id"]) for row in linked]
    summary = (
        f"{', '.join(product_ids)} {'has' if len(product_ids) == 1 else 'have'} both relatively high inventory "
        "value and low recent sales velocity, indicating working-capital or slow-moving-stock risk."
    )
    evidence = [
        Evidence(
            metric="high_value_low_velocity_products",
            value=linked,
            source="sales.csv + inventory.csv + inventory_history.csv",
        )
    ]
    action = RecommendedAction(
        type="review_slow_moving_inventory",
        risk_level=RiskLevel.GREEN,
        reason="High-value inventory is moving slowly relative to the rest of the catalogue.",
        parameters={"product_ids": product_ids},
    )
    return summary, evidence, action


def _replenishment_support(
    sales: AgentResponse,
    inventory: AgentResponse,
) -> tuple[str, list[Evidence], RecommendedAction] | None:
    sales_rows = _detail_rows(_evidence_map(sales), "product_performance_details")
    reorder_rows = _detail_rows(_evidence_map(inventory), "reorder_recommendation_details")
    if not reorder_rows:
        return None

    sales_by_product = {row.get("product_id"): row for row in sales_rows}
    linked = [{**sales_by_product.get(row.get("product_id"), {}), **row} for row in reorder_rows]
    linked.sort(
        key=lambda row: (
            row.get("risk") != "out_of_stock",
            -float(row.get("recent_lost_revenue_sgd") or 0),
            -float(row.get("recent_revenue_sgd") or 0),
            row.get("product_id"),
        )
    )
    product_ids = [str(row["product_id"]) for row in linked]
    total_units = sum(int(row.get("suggested_order_qty") or 0) for row in linked)
    provisional_count = sum(bool(row.get("suggested_order_qty_is_provisional")) for row in linked)
    summary = (
        f"Yes. {len(linked)} products need replenishment to protect current sales activity, with "
        f"{total_units} suggested units in total. {product_ids[0]} is the first priority based on stock risk "
        f"and revenue impact. {provisional_count} recommendation(s) require inbound-quantity verification. "
        "Purchase orders must remain drafts until approved."
    )
    evidence = [
        Evidence(metric="replenishment_priorities", value=linked),
        Evidence(metric="replenishment_total_suggested_units", value=total_units, unit="units"),
        Evidence(metric="provisional_replenishment_count", value=provisional_count, unit="products"),
    ]
    action = RecommendedAction(
        type="review_purchase_order_bundle",
        risk_level=RiskLevel.AMBER,
        reason="The proposed quantities affect supplier commitments and require human approval.",
        parameters={
            "product_ids": product_ids,
            "total_suggested_units": total_units,
            "provisional_product_ids": [
                row["product_id"] for row in linked if row.get("suggested_order_qty_is_provisional")
            ],
        },
    )
    return summary, evidence, action


def advisor_bee(question: str, specialist_results: list[AgentResponse]) -> AgentResponse:
    """Synthesizes outputs from all executed specialists into prioritized guidance."""
    results_by_agent = {result.agent: result for result in specialist_results}
    sales = results_by_agent.get("sales")
    inventory = results_by_agent.get("inventory")
    if sales is not None and inventory is not None:
        text = question.lower()
        insight = None
        if any(
            term in text
            for term in ("best-selling", "best selling", "top-selling", "top selling", "畅销")
        ):
            insight = _top_seller_stock_risk(sales, inventory)
        elif ("inventory" in text or "库存" in text) and any(
            term in text for term in ("low sales", "sales velocity", "slow-moving", "销售速度", "滞销")
        ):
            insight = _high_value_low_velocity(sales, inventory)
        elif any(
            term in text
            for term in ("purchase order", "purchase orders", "reorder", "replenish", "采购", "补货", "下单")
        ):
            insight = _replenishment_support(sales, inventory)

        confidence = round(min(sales.confidence, inventory.confidence), 2)
        if insight is None and any(
            term in text
            for term in ("decline", "drop", "fell", "fall", "lost", "linked", "下降", "下跌", "损失", "关联")
        ):
            linked = _sales_inventory_link(sales, inventory)
            if linked is not None:
                summary, evidence, confidence = linked
                insight = (
                    summary,
                    evidence,
                    RecommendedAction(
                        type="prioritise_revenue_recovery",
                        risk_level=RiskLevel.GREEN,
                        reason="Sales and inventory evidence identify the same product and matching revenue gap.",
                        parameters={"product_id": _evidence_map(sales).get("focus_product_id")},
                    ),
                )

        if insight is not None:
            summary, evidence, action = insight
            additional_results = [
                result for result in specialist_results if result.agent not in {"sales", "inventory"}
            ]
            if additional_results:
                summary += " Additional specialist findings: " + " | ".join(
                    f"[{result.agent.upper()}]: {result.summary}" for result in additional_results
                )
                for result in additional_results:
                    evidence.extend(result.evidence)
            return AgentResponse(
                agent="advisor",
                status=AgentStatus.SUCCESS,
                summary=summary,
                evidence=evidence,
                confidence=round(
                    min([confidence, *(result.confidence for result in additional_results)]),
                    2,
                ),
                recommended_actions=[action],
            )

    evidence = []
    agent_summaries = []
    for result in specialist_results:
        agent_summaries.append(f"[{result.agent.upper()}]: {result.summary}")
        evidence.extend(result.evidence)

    summary_text = (
        f"Advisor analysis for '{question}': " + " | ".join(agent_summaries)
    )

    return AgentResponse(
        agent="advisor",
        status=AgentStatus.SUCCESS,
        summary=summary_text,
        evidence=evidence,
        confidence=min((result.confidence for result in specialist_results), default=0.0),
        recommended_actions=[
            RecommendedAction(
                type="review_advisor_summary",
                risk_level=RiskLevel.GREEN,
                reason="No additional cross-specialist action was inferred beyond the specialist recommendations.",
            )
        ],
    )
