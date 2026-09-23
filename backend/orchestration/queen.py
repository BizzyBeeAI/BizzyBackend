from __future__ import annotations

from backend.agents.specialists import customer_bee, finance_bee, inventory_bee, sales_bee
from backend.models.agent import AgentResponse, AgentStatus, Evidence, RecommendedAction, RiskLevel


AGENT_REGISTRY = {
    "sales": sales_bee,
    "customer": customer_bee,
    "finance": finance_bee,
    "inventory": inventory_bee,
}


def select_agents(question: str) -> list[str]:
    text = question.lower()

    if any(keyword in text for keyword in ("stock", "inventory", "units left")):
        return ["inventory"]

    selected = []
    if any(keyword in text for keyword in ("sales", "revenue", "decline", "fell")):
        selected.append("sales")
    if any(keyword in text for keyword in ("customer", "lead", "enquiry", "convert")):
        selected.append("customer")
    if any(keyword in text for keyword in ("invoice", "cash", "finance", "overdue")):
        selected.append("finance")
    if any(keyword in text for keyword in ("stock", "inventory", "product")):
        selected.append("inventory")

    return selected or ["sales"]


def run_specialists(question: str) -> tuple[list[str], list[AgentResponse]]:
    selected = select_agents(question)
    results = [AGENT_REGISTRY[name]() for name in selected]
    return selected, results


def advisor_bee(question: str, specialist_results: list[AgentResponse]) -> AgentResponse:
    evidence = [
        Evidence(metric=f"{result.agent}_summary", value=result.summary)
        for result in specialist_results
    ]

    return AgentResponse(
        agent="advisor",
        status=AgentStatus.SUCCESS,
        summary=f"Based on {len(specialist_results)} specialist analyses, prioritise high-impact follow-up actions.",
        evidence=evidence,
        confidence=0.84,
        recommended_actions=[
            RecommendedAction(type="prioritise_revenue_recovery", risk_level=RiskLevel.GREEN),
            RecommendedAction(type="bundle_amber_actions_for_approval", risk_level=RiskLevel.AMBER),
        ],
    )
