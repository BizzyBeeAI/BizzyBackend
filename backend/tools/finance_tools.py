from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

import duckdb

from backend.tools.sales_tools import sql_path

INVOICE_COLUMN_TYPES = (
    "{'invoice_id': 'VARCHAR', 'due_date': 'DATE', 'amount': 'DECIMAL(14,2)', "
    "'paid_amount': 'DECIMAL(14,2)', 'outstanding_amount': 'DECIMAL(14,2)', "
    "'currency': 'VARCHAR', 'status': 'VARCHAR'}"
)


@dataclass(frozen=True)
class ReceivablesSummary:
    as_of: date
    overdue_invoice_count: int
    overdue_outstanding: Decimal


def assess_receivables(data_dir: Path, as_of: date) -> ReceivablesSummary:
    invoices_path = data_dir / "invoices.csv"
    if not invoices_path.exists():
        raise FileNotFoundError(f"invoices.csv not found in {data_dir}")

    con = duckdb.connect()
    try:
        count, outstanding = con.execute(
            f"""
            SELECT
                COUNT(*) FILTER (
                    WHERE outstanding_amount > 0
                      AND due_date < $as_of
                ),
                COALESCE(
                    SUM(outstanding_amount) FILTER (
                        WHERE outstanding_amount > 0
                          AND due_date < $as_of
                    ),
                    0
                )
            FROM read_csv(
                {sql_path(invoices_path)},
                header = true,
                types = {INVOICE_COLUMN_TYPES}
            )
            """,
            {"as_of": as_of},
        ).fetchone()
    finally:
        con.close()

    return ReceivablesSummary(
        as_of=as_of,
        overdue_invoice_count=int(count),
        overdue_outstanding=Decimal(outstanding),
    )

