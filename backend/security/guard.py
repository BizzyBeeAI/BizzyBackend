from __future__ import annotations

from backend.models.agent import AgentResponse


def _positive_integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _invalid_controlled_action(action_type: str, parameters: dict[str, object]) -> bool:
    if action_type == "prepare_purchase_order":
        return not (
            parameters.get("product_id")
            and parameters.get("supplier_id")
            and _positive_integer(parameters.get("quantity"))
        )
    if action_type == "verify_inbound_quantity":
        return not (
            parameters.get("product_id")
            and parameters.get("supplier_id")
            and parameters.get("existing_receipt_date")
            and _positive_integer(parameters.get("provisional_additional_order_qty"))
        )
    if action_type == "review_purchase_order_bundle":
        product_ids = parameters.get("product_ids")
        return not (
            isinstance(product_ids, list)
            and product_ids
            and all(isinstance(product_id, str) and product_id for product_id in product_ids)
            and _positive_integer(parameters.get("total_suggested_units"))
        )
    return False


def evaluate(actions_from_agents: list[AgentResponse]) -> tuple[str, bool]:
    all_actions = [action for response in actions_from_agents for action in response.recommended_actions]
    controlled_types = {
        "prepare_purchase_order",
        "verify_inbound_quantity",
        "review_purchase_order_bundle",
    }

    if any(action.risk_level.value == "RED" for action in all_actions):
        return "blocked", True
    if any(
        action.type in controlled_types and _invalid_controlled_action(action.type, action.parameters)
        for action in all_actions
    ):
        return "blocked", True
    if any(action.type in controlled_types for action in all_actions):
        return "approval_required", True
    if any(action.risk_level.value == "AMBER" for action in all_actions):
        return "approval_required", True
    return "allowed", False
