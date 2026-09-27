from __future__ import annotations

import re

from backend.models.agent import AgentResponse


_READ_ONLY_ACTIONS = {
    "analyze_customer",
    "analyze_finance",
    "analyze_inventory",
    "analyze_sales",
    "get_business_health",
    "read_business_analytics",
    "review_customer_complaints",
    "review_financial_exposure",
    "review_inventory_shortage",
    "review_payment_history",
    "review_pending_enquiries",
    "review_pricing",
    "review_sales_decline",
    "review_supplier_quality_defect",
}

_AMBER_ACTIONS = {
    "prepare_customer_follow_up",
    "prepare_invoice_reminders",
    "prepare_purchase_order",
    "send_customer_follow_up",
    "send_customer_message",
    "send_invoice_reminder",
    "send_message_to_customer",
    "submit_purchase_order",
}

_RED_VERBS = {"delete", "erase", "remove"}
_FINANCIAL_RECORDS = {
    "bank",
    "finance",
    "financial",
    "invoice",
    "payment",
    "record",
    "records",
    "transaction",
}
_BANK_DETAIL_MUTATIONS = {"alter", "change", "edit", "modify", "replace", "set", "update"}
_EXTERNAL_PARTIES = {"client", "customer", "external", "supplier", "vendor"}
_COMMUNICATION_VERBS = {
    "communicate",
    "contact",
    "email",
    "message",
    "notify",
    "reply",
    "respond",
    "send",
}
_COMMUNICATION_NOUNS = {"communication", "email", "message", "notification", "response"}


def _action_key(action_type: str) -> str:
    action_name = action_type.split("[evidence:", maxsplit=1)[0].strip().lower()
    return re.sub(r"[^a-z0-9]+", "_", action_name).strip("_")


def _classify(action_type: str) -> tuple[str, str]:
    action = _action_key(action_type)
    if action in _READ_ONLY_ACTIONS:
        return "GREEN", "allowlisted read-only business analytics."

    tokens = set(action.split("_"))
    is_bank_detail_change = "bank" in tokens and bool(
        tokens.intersection({"account", "detail", "details"})
        and tokens.intersection(_BANK_DETAIL_MUTATIONS)
    )
    is_financial_deletion = bool(tokens.intersection(_RED_VERBS)) and bool(
        tokens.intersection(_FINANCIAL_RECORDS)
    )
    if (
        tokens.intersection({"pay", "payment", "payments"})
        or "transfer" in tokens
        or is_bank_detail_change
        or is_financial_deletion
    ):
        return "RED", "autonomous financial or bank-data action is prohibited."

    is_external_communication = bool(tokens.intersection(_COMMUNICATION_VERBS)) and bool(
        tokens.intersection(_EXTERNAL_PARTIES)
        or tokens.intersection(_COMMUNICATION_NOUNS)
    )
    if (
        action in _AMBER_ACTIONS
        or "purchase_order" in action
        or is_external_communication
        or "external_commitment" in action
        or "commit_to_supplier" in action
        or ("commitment" in tokens and bool(tokens.intersection(_EXTERNAL_PARTIES)))
    ):
        return "AMBER", "explicit human approval is required before external communication or commitment."

    return "DENY", "unknown action is denied by default."


def evaluate(actions_from_agents: list[AgentResponse]) -> tuple[str, bool]:
    """Classify proposed actions without executing them or trusting agent risk labels."""
    classified = [
        (_action_key(action.type), *_classify(action.type))
        for response in actions_from_agents
        for action in response.recommended_actions
    ]

    if not classified:
        return "allowed: no actions were proposed.", False

    details = [f"{action}: {risk} - {reason}" for action, risk, reason in classified]
    if any(risk in {"RED", "DENY"} for _, risk, _ in classified):
        return f"blocked: {'; '.join(details)}", False
    if any(risk == "AMBER" for _, risk, _ in classified):
        return f"approval_required: {'; '.join(details)}", True
    return f"allowed: {'; '.join(details)}", False