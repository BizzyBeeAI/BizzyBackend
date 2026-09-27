from __future__ import annotations

import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.models.agent import AgentResponse


DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "audit.sqlite3"

_EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_BEARER_PATTERN = re.compile(r"\bBearer\s+\S+", re.IGNORECASE)
_SECRET_PATTERN = re.compile(
    r"\b(api[_ -]?key|access[_ -]?token|password|secret)\s*[:=]\s*\S+",
    re.IGNORECASE,
)
_SENSITIVE_KEY_PATTERN = re.compile(
    r"(api[_-]?key|access[_-]?token|password|secret|credential|authorization)",
    re.IGNORECASE,
)
_KEY_PATTERN = re.compile(r"\b(?:sk-[A-Za-z0-9_-]{16,}|AKIA[A-Z0-9]{16})\b")
_PHONE_PATTERN = re.compile(r"(?<!\w)\+?\d[\d ().-]{7,}\d(?!\w)")
_ACTION_EVIDENCE_PATTERN = re.compile(r"\[evidence:\s*(.*?)\]\s*$", re.IGNORECASE)
_GUARD_DETAIL_PATTERN = re.compile(r"^(.*?): (GREEN|AMBER|RED|DENY) - (.+)$")


def _redact_text(value: str) -> str:
    value = _BEARER_PATTERN.sub("[REDACTED_CREDENTIAL]", value)
    value = _SECRET_PATTERN.sub(r"\1=[REDACTED_CREDENTIAL]", value)
    value = _KEY_PATTERN.sub("[REDACTED_CREDENTIAL]", value)
    value = _EMAIL_PATTERN.sub("[REDACTED_EMAIL]", value)
    return _PHONE_PATTERN.sub("[REDACTED_PHONE]", value)


def _safe_value(value: Any) -> Any:
    if isinstance(value, str):
        return _redact_text(value)
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED_CREDENTIAL]"
            if _SENSITIVE_KEY_PATTERN.search(str(key))
            else _safe_value(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_safe_value(item) for item in value]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return _redact_text(str(value))


def _evidence_data(result: AgentResponse) -> list[dict[str, Any]]:
    return [
        {"metric": _redact_text(item.metric), "value": _safe_value(item.value)}
        for item in result.evidence
    ]


def _action_data(result: AgentResponse) -> list[dict[str, Any]]:
    actions = []
    for action in result.recommended_actions:
        match = _ACTION_EVIDENCE_PATTERN.search(action.type)
        action_name = action.type[: match.start()].strip() if match else action.type
        evidence_references = (
            [reference.strip() for reference in match.group(1).split(",") if reference.strip()]
            if match
            else []
        )
        actions.append(
            {
                "type": _redact_text(action_name),
                "risk_level": action.risk_level.value,
                "evidence_references": [_redact_text(reference) for reference in evidence_references],
                "status": "proposed",
                "executed": False,
            }
        )
    return actions


def _agent_data(result: AgentResponse) -> dict[str, Any]:
    return {
        "agent": _redact_text(result.agent),
        "status": result.status.value,
        "summary": _redact_text(result.summary),
        "evidence": _evidence_data(result),
        "confidence": result.confidence,
        "recommended_actions": _action_data(result),
    }


def _guard_explanations(decision: str) -> list[dict[str, str]]:
    _, separator, details = decision.partition(": ")
    if not separator:
        return []

    explanations = []
    for entry in details.split("; "):
        match = _GUARD_DETAIL_PATTERN.match(entry)
        if match:
            explanations.append(
                {
                    "action": _redact_text(match.group(1)),
                    "classification": match.group(2),
                    "reason": _redact_text(match.group(3)),
                }
            )
    return explanations


def build_audit_event(
    workflow_id: str,
    user: str,
    results: list[AgentResponse],
    decision: str,
    *,
    invoked_agents: list[str] | None = None,
    advisor_result: AgentResponse | None = None,
    approval_required: bool = False,
    query: str = "",
    status: str = "completed",
    failure_type: str | None = None,
) -> dict[str, Any]:
    """Build a privacy-filtered audit event; the legacy user argument is not stored."""
    del user
    specialists = [result for result in results if result.agent.lower() != "advisor"]
    if advisor_result is None:
        advisor_result = next(
            (result for result in results if result.agent.lower() == "advisor"),
            None,
        )
    all_results = [*specialists, *([advisor_result] if advisor_result else [])]
    proposed_actions = [action for result in all_results for action in _action_data(result)]

    return {
        "trace_id": workflow_id,
        "workflow_id": workflow_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "query": _redact_text(query),
        "invoked_agents": [_redact_text(agent) for agent in (invoked_agents or [])],
        "agents": [_redact_text(result.agent) for result in all_results],
        "specialist_results": [_agent_data(result) for result in specialists],
        "advisor_result": _agent_data(advisor_result) if advisor_result else None,
        "decision": decision,
        "guard": {
            "decision": _redact_text(decision),
            "approval_required": approval_required,
            "action_explanations": _guard_explanations(decision),
        },
        "approval_required": approval_required,
        "proposed_actions": proposed_actions,
        "executed_actions": [],
        "evidence_count": sum(len(result.evidence) for result in all_results),
        "failure_type": failure_type,
    }


def _database_path(db_path: str | Path | None = None) -> Path:
    configured_path = db_path or os.getenv("BIZZYBEE_AUDIT_DB")
    return Path(configured_path) if configured_path else DEFAULT_DB_PATH


def _connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    path = _database_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_events (
            trace_id TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL,
            payload TEXT NOT NULL
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_audit_events_timestamp ON audit_events(timestamp DESC)"
    )
    return connection


def persist_audit_event(
    event: dict[str, Any],
    db_path: str | Path | None = None,
) -> None:
    with _connect(db_path) as connection:
        connection.execute(
            "INSERT INTO audit_events (trace_id, timestamp, payload) VALUES (?, ?, ?)",
            (
                event["trace_id"],
                event["timestamp"],
                json.dumps(event, ensure_ascii=False, separators=(",", ":")),
            ),
        )


def get_audit_event(
    trace_id: str,
    db_path: str | Path | None = None,
) -> dict[str, Any] | None:
    with _connect(db_path) as connection:
        row = connection.execute(
            "SELECT payload FROM audit_events WHERE trace_id = ?",
            (trace_id,),
        ).fetchone()
    return json.loads(row["payload"]) if row else None


def list_audit_events(
    limit: int = 20,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    with _connect(db_path) as connection:
        rows = connection.execute(
            "SELECT payload FROM audit_events ORDER BY timestamp DESC, rowid DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [json.loads(row["payload"]) for row in rows]
