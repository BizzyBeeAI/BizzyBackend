from __future__ import annotations

import re

from backend.models.agent import AgentResponse, AgentStatus, Evidence, RecommendedAction, RiskLevel


def _normalise(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def _number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(",", "").strip())
        except ValueError:
            return None
    return None


def _has_any(text: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase in text for phrase in phrases)


def _evidence_refs(
    result: AgentResponse,
    matches: tuple[str, ...],
) -> list[str]:
    return [
        f"{result.agent}.{item.metric}"
        for item in result.evidence
        if _has_any(_normalise(item.metric), matches)
    ]


def _has_metric_conflict(
    result: AgentResponse,
    matches: tuple[str, ...],
    conflicting_metrics: set[tuple[str, str]],
) -> bool:
    return any(
        agent == result.agent and _has_any(metric, matches)
        for agent, metric in conflicting_metrics
    )


def _action(action: str, references: list[str]) -> RecommendedAction:
    # RecommendedAction has no evidence field, so retain the shared schema and
    # expose the source references in its existing string identifier.
    cited_type = f"{action} [evidence: {', '.join(references)}]"
    return RecommendedAction(type=cited_type, risk_level=RiskLevel.GREEN)


def advisor_bee(question: str, specialist_results: list[AgentResponse]) -> AgentResponse:
    """Turn supported specialist findings into review-only recommendations."""
    usable_results = [
        result
        for result in specialist_results
        if result.status in (AgentStatus.SUCCESS, AgentStatus.PARTIAL)
    ]
    evidence = [item for result in usable_results for item in result.evidence]
    agent_summaries = [
        f"[{result.agent.upper()} / {result.status.value}]: {result.summary}"
        for result in specialist_results
    ]

    values_by_metric: dict[tuple[str, str], set[float]] = {}
    for result in usable_results:
        for item in result.evidence:
            number = _number(item.value)
            if number is not None:
                key = (result.agent, _normalise(item.metric))
                values_by_metric.setdefault(key, set()).add(number)
    conflicting_metrics = {
        key for key, values in values_by_metric.items() if len(values) > 1
    }

    recommendations: list[RecommendedAction] = []
    findings: list[str] = []
    conflicts: list[str] = []
    declined_sales: list[AgentResponse] = []
    low_inventory: list[AgentResponse] = []
    customer_issues: list[AgentResponse] = []

    for result in usable_results:
        summary = result.summary.lower()
        metrics = [(_normalise(item.metric), _number(item.value)) for item in result.evidence]

        if result.agent == "sales":
            directional_values = [
                number
                for metric, number in metrics
                if number is not None
                and _has_any(metric, ("change", "growth", "trend", "delta", "variance", "week_on_week", "week_over_week", "wow"))
            ]
            says_decline = _has_any(
                summary,
                ("declin", "fell", "decreas", "drop", "downward", "down week"),
            ) and not _has_any(
                summary,
                ("no decline", "not declining", "did not decline", "has not declined", "did not fall", "not fallen", "no decrease"),
            )
            says_growth = _has_any(
                summary,
                ("increas", "grew", "growth", "improv", "upward", "up week"),
            )
            has_negative = any(value < 0 for value in directional_values)
            has_positive = any(value > 0 for value in directional_values)
            is_conflicted = _has_metric_conflict(
                result,
                ("sales", "revenue", "change", "trend", "growth", "decline", "delta", "variance", "week_on_week", "week_over_week", "wow"),
                conflicting_metrics,
            ) or (says_decline and (says_growth or has_positive)) or (says_growth and has_negative)
            if is_conflicted:
                conflicts.append("Sales direction is conflicting; a sales recommendation was withheld.")
            elif says_decline or has_negative:
                refs = _evidence_refs(result, ("revenue", "sales", "quantity", "change", "trend"))
                if refs:
                    declined_sales.append(result)
                    findings.append("Sales decline is reported by the sales specialist.")
                    recommendations.append(_action("review_sales_decline", refs))

        elif result.agent == "inventory":
            stock = next((number for metric, number in metrics if metric == "current_stock"), None)
            threshold = next((number for metric, number in metrics if metric == "reorder_level"), None)
            says_low = _has_any(summary, ("below threshold", "low inventory", "stockout", "stock-out", "shortage", "out of stock")) and not _has_any(
                summary,
                ("not below threshold", "no stockout", "no stock-out", "no shortage", "not low", "above threshold"),
            )
            says_healthy = _has_any(summary, ("healthy", "above threshold", "sufficient stock"))
            numeric_low = stock is not None and threshold is not None and stock <= threshold
            numeric_healthy = stock is not None and threshold is not None and stock > threshold
            is_conflicted = _has_metric_conflict(
                result, ("current_stock", "reorder_level"), conflicting_metrics
            ) or (numeric_low and says_healthy) or (numeric_healthy and says_low)
            if is_conflicted:
                conflicts.append("Inventory status is conflicting; an inventory recommendation was withheld.")
            elif numeric_low or says_low:
                refs = _evidence_refs(result, ("stock", "reorder"))
                if refs:
                    low_inventory.append(result)
                    findings.append("Inventory is reported at or below its reorder threshold.")
                    recommendations.append(_action("review_inventory_shortage", refs))

        elif result.agent == "customer":
            complaint_metrics = ("complaint", "defect", "refund")
            pending_metrics = ("unanswered", "pending", "enquiry", "lead", "response")
            complaint_values = [
                number
                for metric, number in metrics
                if number is not None and _has_any(metric, complaint_metrics)
            ]
            pending_values = [
                number
                for metric, number in metrics
                if number is not None and _has_any(metric, pending_metrics)
            ]
            complaint_text_signal = _has_any(
                summary, ("complaints increased", "increasing complaints", "defect reports", "refund impact")
            )
            pending_text_signal = (
                _has_any(summary, ("unanswered", "pending enquiries", "missed opportunities"))
                and not _has_any(
                    summary,
                    ("no unanswered", "none unanswered", "no pending", "all enquiries answered", "no missed opportunities"),
                )
            )
            complaint_positive = any(value > 0 for value in complaint_values)
            pending_positive = any(value > 0 for value in pending_values)
            complaint_conflict = _has_metric_conflict(result, complaint_metrics, conflicting_metrics) or (
                complaint_text_signal and bool(complaint_values) and not complaint_positive
            )
            pending_conflict = _has_metric_conflict(result, pending_metrics, conflicting_metrics) or (
                pending_text_signal and bool(pending_values) and not pending_positive
            )
            complaint_signal = complaint_positive or (complaint_text_signal and not complaint_values)
            pending_signal = pending_positive or (pending_text_signal and not pending_values)
            if complaint_conflict:
                conflicts.append("Customer complaint evidence is conflicting; a complaint recommendation was withheld.")
            elif complaint_signal:
                refs = _evidence_refs(result, complaint_metrics)
                if refs:
                    customer_issues.append(result)
                    findings.append("Customer complaint or defect evidence is present.")
                    recommendations.append(_action("review_customer_complaints", refs))
            if pending_conflict:
                conflicts.append("Pending-enquiry evidence is conflicting; a follow-up recommendation was withheld.")
            elif pending_signal:
                refs = _evidence_refs(result, pending_metrics)
                if refs:
                    customer_issues.append(result)
                    findings.append("Unanswered or pending customer enquiries are reported.")
                    recommendations.append(_action("review_pending_enquiries", refs))

        elif result.agent == "finance":
            finance_metrics = ("overdue", "unpaid", "receivable", "outstanding", "cash", "past_due")
            finance_values = [
                number
                for metric, number in metrics
                if number is not None and _has_any(metric, finance_metrics)
            ]
            finance_text_signal = _has_any(
                summary, ("overdue", "unpaid", "cash flow", "receivable", "past due", "financial concern")
            ) and not _has_any(
                summary,
                ("no overdue", "no unpaid", "no outstanding", "no receivable", "no past due", "no financial concern", "cash flow is healthy"),
            )
            finance_negative_text = _has_any(
                summary,
                ("no overdue", "no unpaid", "no outstanding", "no receivable", "no past due", "no financial concern", "cash flow is healthy"),
            )
            numeric_financial_concern = any(value > 0 for value in finance_values)
            finance_signal = (
                numeric_financial_concern if finance_values else finance_text_signal
            )
            is_conflicted = _has_metric_conflict(result, finance_metrics, conflicting_metrics)
            is_conflicted = is_conflicted or (finance_negative_text and numeric_financial_concern)
            if is_conflicted:
                conflicts.append("Financial evidence is conflicting; a financial recommendation was withheld.")
            elif finance_signal:
                refs = _evidence_refs(result, finance_metrics)
                if refs:
                    findings.append("Financial exposure is reported by the finance specialist.")
                    recommendations.append(_action("review_financial_exposure", refs))

    relationships: list[str] = []
    if declined_sales and low_inventory:
        relationships.append(
            "Sales decline coincides with low inventory; this may be related, but the evidence does not establish causation."
        )
    if declined_sales and customer_issues:
        relationships.append(
            "Sales decline coincides with customer complaints or pending enquiries; this may be related, but the evidence does not establish causation."
        )

    if not usable_results:
        findings.append("No usable specialist results were available; no recommendations were made.")
    elif not recommendations and not conflicts:
        findings.append("No significant problems were reported by the available specialists.")

    summary_parts = [f"Advisor analysis for '{question}'."]
    if agent_summaries:
        summary_parts.append(" ".join(agent_summaries))
    summary_parts.extend(findings)
    summary_parts.extend(relationships)
    summary_parts.extend(conflicts)
    summary_text = " ".join(summary_parts)

    status = (
        AgentStatus.PARTIAL
        if not usable_results
        or conflicts
        or any(result.status != AgentStatus.SUCCESS for result in specialist_results)
        else AgentStatus.SUCCESS
    )
    if usable_results:
        confidence = sum(result.confidence for result in usable_results) / len(usable_results)
        if status == AgentStatus.PARTIAL:
            confidence *= 0.75
    else:
        confidence = 0.0

    return AgentResponse(
        agent="advisor",
        status=status,
        summary=summary_text,
        evidence=evidence,
        confidence=confidence,
        recommended_actions=recommendations,
    )