from __future__ import annotations

from backend.models.agent import AgentResponse


def evaluate(actions_from_agents: list[AgentResponse]) -> tuple[str, bool]:
    all_actions = [action for response in actions_from_agents for action in response.recommended_actions]

    if any(action.risk_level.value == "RED" for action in all_actions):
        return "blocked", True
    if any(action.risk_level.value == "AMBER" for action in all_actions):
        return "approval_required", True
    return "allowed", False
