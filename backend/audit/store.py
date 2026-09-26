from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

from backend.models.agent import AgentResponse

_EVENTS: dict[str, dict[str, object]] = {}
_LOCK = Lock()


def _log_path() -> Path | None:
    configured = os.getenv("BIZZY_AUDIT_LOG")
    return None if not configured else Path(configured).expanduser()


def build_audit_event(
    workflow_id: str,
    user: str,
    results: list[AgentResponse],
    decision: str,
    question: str | None = None,
) -> dict[str, object]:
    return {
        "workflow_id": workflow_id,
        "user": user,
        "question": question,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "agents": [result.agent for result in results],
        "statuses": {result.agent: result.status.value for result in results},
        "decision": decision,
        "evidence_count": sum(len(result.evidence) for result in results),
        "actions": [
            {
                "agent": result.agent,
                "type": action.type,
                "risk_level": action.risk_level.value,
                "parameters": action.parameters,
            }
            for result in results
            for action in result.recommended_actions
        ],
    }


def save_audit_event(event: dict[str, object]) -> None:
    workflow_id = str(event["workflow_id"])
    with _LOCK:
        _EVENTS[workflow_id] = event
        path = _log_path()
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event, ensure_ascii=False) + "\n")


def get_audit_event(workflow_id: str) -> dict[str, object] | None:
    with _LOCK:
        event = _EVENTS.get(workflow_id)
        if event is not None:
            return dict(event)
        path = _log_path()
        if path is None or not path.exists():
            return None
        matched = None
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                candidate = json.loads(line)
                if str(candidate.get("workflow_id")) == workflow_id:
                    matched = candidate
        if matched is not None:
            _EVENTS[workflow_id] = matched
            return dict(matched)
        return None


def clear_audit_events() -> None:
    with _LOCK:
        _EVENTS.clear()
