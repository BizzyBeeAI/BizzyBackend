from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

import duckdb

from backend.models.agent import AgentResponse, AgentStatus, Evidence, RecommendedAction, RiskLevel
from backend.tools import demo_data
from backend.tools.finance_tools import assess_receivables

logger = logging.getLogger(__name__)


def finance_bee(
    question: str | None = None,
    as_of: date | None = None,
    data_dir: Path | None = None,
) -> AgentResponse:
    reporting_date = as_of or demo_data.as_of_date()
    source_dir = data_dir or demo_data.DATA_DIR
    try:
        summary = assess_receivables(source_dir, reporting_date)
    except (FileNotFoundError, duckdb.Error):
        logger.warning("Finance Bee could not read invoice data from %s", source_dir, exc_info=True)
        return AgentResponse(
            agent="finance",
            status=AgentStatus.FAILED,
            summary="Invoice data is unavailable, so overdue receivables could not be calculated.",
            confidence=0.0,
        )

    outstanding = float(round(summary.overdue_outstanding, 2))
    return AgentResponse(
        agent="finance",
        status=AgentStatus.SUCCESS,
        summary=(
            f"{summary.overdue_invoice_count} invoices are overdue with "
            f"SGD {summary.overdue_outstanding:,.2f} still outstanding as of {summary.as_of.isoformat()}."
        ),
        evidence=[
            Evidence(metric="analysis_intent", value="overdue_receivables"),
            Evidence(metric="as_of_date", value=summary.as_of.isoformat(), source="invoices.csv"),
            Evidence(
                metric="overdue_invoice_count",
                value=summary.overdue_invoice_count,
                unit="invoices",
                source="invoices.csv",
            ),
            Evidence(
                metric="overdue_outstanding_sgd",
                value=outstanding,
                unit="SGD",
                source="invoices.csv",
            ),
        ],
        confidence=0.95,
        recommended_actions=[
            RecommendedAction(
                type="prepare_invoice_reminders",
                risk_level=RiskLevel.AMBER,
                reason="Overdue balances require customer follow-up but messages should be approved first.",
                parameters={"overdue_invoice_count": summary.overdue_invoice_count},
                expected_impact={"outstanding_receivables_sgd": outstanding},
            )
        ],
    )

