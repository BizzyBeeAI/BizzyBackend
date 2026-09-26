from __future__ import annotations

from backend.models.agent import AgentResponse, AgentStatus, Evidence, RecommendedAction, RiskLevel


def advisor_bee(question: str, specialist_results: list[AgentResponse]) -> AgentResponse:
    """Synthesizes outputs from all executed specialists into prioritized guidance."""
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
        confidence=0.90,
        recommended_actions=[
            RecommendedAction(type="prioritise_revenue_recovery", risk_level=RiskLevel.GREEN),
            RecommendedAction(type="bundle_amber_actions_for_approval", risk_level=RiskLevel.AMBER),
        ],
    )