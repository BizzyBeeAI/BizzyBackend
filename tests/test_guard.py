from backend.models.agent import AgentResponse, AgentStatus, RecommendedAction, RiskLevel
from backend.security.guard import evaluate


def response(*actions: tuple[str, RiskLevel]) -> AgentResponse:
    return AgentResponse(
        agent="test",
        status=AgentStatus.SUCCESS,
        summary="Test actions",
        confidence=1.0,
        recommended_actions=[
            RecommendedAction(type=action_type, risk_level=risk)
            for action_type, risk in actions
        ],
    )


def test_authorised_read_only_action_is_allowed() -> None:
    decision, approval_required = evaluate(
        [response(("review_sales_decline", RiskLevel.GREEN))]
    )

    assert decision.startswith("allowed:")
    assert "read-only business analytics" in decision
    assert approval_required is False


def test_customer_message_requires_explicit_approval() -> None:
    decision, approval_required = evaluate(
        [response(("send_customer_message", RiskLevel.GREEN))]
    )

    assert decision.startswith("approval_required:")
    assert "explicit human approval" in decision
    assert approval_required is True


def test_purchase_order_requires_explicit_approval() -> None:
    decision, approval_required = evaluate(
        [response(("submit_purchase_order", RiskLevel.GREEN))]
    )

    assert decision.startswith("approval_required:")
    assert "external communication or commitment" in decision
    assert approval_required is True


def test_external_commitment_requires_explicit_approval() -> None:
    decision, approval_required = evaluate(
        [response(("commit_to_supplier", RiskLevel.GREEN))]
    )

    assert decision.startswith("approval_required:")
    assert "explicit human approval" in decision
    assert approval_required is True


def test_autonomous_payment_is_blocked_even_when_marked_green() -> None:
    decision, approval_required = evaluate(
        [response(("process_payment", RiskLevel.GREEN))]
    )

    assert decision.startswith("blocked:")
    assert "prohibited" in decision
    assert approval_required is False


def test_bank_transfer_and_financial_record_deletion_are_blocked() -> None:
    decision, approval_required = evaluate(
        [
            response(
                ("bank_transfer", RiskLevel.GREEN),
                ("delete_financial_records", RiskLevel.GREEN),
            )
        ]
    )

    assert decision.startswith("blocked:")
    assert "bank_transfer: RED" in decision
    assert "delete_financial_records: RED" in decision
    assert approval_required is False


def test_unknown_action_is_denied_by_default() -> None:
    decision, approval_required = evaluate(
        [response(("launch_unknown_operation", RiskLevel.GREEN))]
    )

    assert decision.startswith("blocked:")
    assert "unknown action is denied by default" in decision
    assert approval_required is False


def test_ambiguous_external_message_is_denied_by_default() -> None:
    decision, approval_required = evaluate([response(("send", RiskLevel.AMBER))])

    assert decision.startswith("blocked:")
    assert "unknown action is denied by default" in decision
    assert approval_required is False


def test_low_risk_label_cannot_override_bank_details_policy() -> None:
    decision, approval_required = evaluate(
        [response(("change_bank_details", RiskLevel.GREEN))]
    )

    assert decision.startswith("blocked:")
    assert "prohibited" in decision
    assert approval_required is False


def test_mixed_read_only_and_amber_actions_require_approval() -> None:
    decision, approval_required = evaluate(
        [
            response(
                ("review_inventory_shortage", RiskLevel.RED),
                ("prepare_purchase_order", RiskLevel.GREEN),
            )
        ]
    )

    assert decision.startswith("approval_required:")
    assert "review_inventory_shortage: GREEN" in decision
    assert "prepare_purchase_order: AMBER" in decision
    assert approval_required is True


def test_red_decision_takes_precedence_over_amber_action() -> None:
    decision, approval_required = evaluate(
        [
            response(
                ("send_customer_message", RiskLevel.GREEN),
                ("autonomous_payment", RiskLevel.GREEN),
            )
        ]
    )

    assert decision.startswith("blocked:")
    assert "send_customer_message: AMBER" in decision
    assert "autonomous_payment: RED" in decision
    assert approval_required is False


def test_no_proposed_actions_are_allowed() -> None:
    decision, approval_required = evaluate([response()])

    assert decision == "allowed: no actions were proposed."
    assert approval_required is False