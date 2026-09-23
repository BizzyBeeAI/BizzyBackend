from __future__ import annotations

from backend.models.agent import AgentResponse


def build_audit_event(workflow_id: str, user: str, results: list[AgentResponse], decision: str) -> dict[str, object]:
    return {
        "workflow_id": workflow_id,
        "user": user,
        "agents": [result.agent for result in results],
        "decision": decision,
        "evidence_count": sum(len(result.evidence) for result in results),
    }
