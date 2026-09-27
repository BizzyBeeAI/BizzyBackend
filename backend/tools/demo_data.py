from __future__ import annotations

import csv
import duckdb
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# Look for full dataset in workspace parent folders or fallback to local backend data
DATA_DIR = ROOT.parents[1] / "BizzyData.worktrees" / "explanation-request-clarification" / "data" / "demo"
if not DATA_DIR.exists():
    DATA_DIR = ROOT.parents[1] / "BizzyData" / "data" / "demo"
if not DATA_DIR.exists():
    DATA_DIR = ROOT / "data" / "demo"

def _read_csv(name: str) -> list[dict[str, str]]:
    file_path = DATA_DIR / name
    if not file_path.exists():
        return []

    with file_path.open("r", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load_sales() -> list[dict[str, str]]:
    return _read_csv("sales.csv")


def load_inventory() -> list[dict[str, str]]:
    return _read_csv("inventory.csv")


def load_invoices() -> list[dict[str, str]]:
    return _read_csv("invoices.csv")


def load_customer_enquiries() -> list[dict[str, str]]:
    return _read_csv("customer_enquiries.csv")

# Add this at the bottom of backend/tools/demo_data.py

def get_db() -> duckdb.DuckDBPyConnection:
    """Creates an in-memory DuckDB connection pointing directly to CSV datasets."""
    con = duckdb.connect()
    datasets = {
        "feedback": "customer_feedback.csv",
        "enquiries": "customer_enquiries.csv",
        "returns": "returns.csv",
        "refunds": "refunds.csv",
        "sales": "customer_sales.csv" if (DATA_DIR / "customer_sales.csv").exists() else "sales.csv",
        "products": "products.csv",
    }
    for view, filename in datasets.items():
        file_path = DATA_DIR / filename
        if file_path.exists():
            con.execute(f"CREATE VIEW {view} AS SELECT * FROM '{file_path}';")
    return con


def analyze_customer_complaints() -> list[dict]:
    """Calculates defect complaint rates and total refund financial impact per product."""
    required_files = (
        "customer_feedback.csv",
        "returns.csv",
        "refunds.csv",
        "customer_sales.csv",
        "products.csv",
    )
    if any(not (DATA_DIR / filename).exists() for filename in required_files):
        return []

    con = get_db()
    query = """
    WITH calendar AS (
        SELECT MAX(CAST(feedback_date AS DATE)) AS latest_date
        FROM feedback
        WHERE feedback_type = 'complaint'
    ),
    periods AS (
        SELECT
            latest_date - INTERVAL 13 DAY AS previous_start,
            latest_date - INTERVAL 7 DAY AS previous_end,
            latest_date - INTERVAL 6 DAY AS current_start,
            latest_date AS current_end
        FROM calendar
    ),
    product_sales AS (
        SELECT
            s.product_id,
            SUM(s.quantity) AS total_units_sold,
            SUM(CASE WHEN CAST(s.sale_date AS DATE) BETWEEN p.previous_start AND p.previous_end THEN s.quantity ELSE 0 END) AS previous_period_units_sold,
            SUM(CASE WHEN CAST(s.sale_date AS DATE) BETWEEN p.current_start AND p.current_end THEN s.quantity ELSE 0 END) AS current_period_units_sold
        FROM sales s
        CROSS JOIN periods p
        GROUP BY s.product_id
    ),
    complaint_stats AS (
        SELECT 
            f.product_id,
            COUNT(*) AS total_complaints,
            SUM(f.affected_quantity) AS defective_units,
            COUNT(DISTINCT f.return_id) AS total_returns
            ,SUM(CASE WHEN CAST(f.feedback_date AS DATE) BETWEEN p.previous_start AND p.previous_end THEN 1 ELSE 0 END) AS previous_period_complaints
            ,SUM(CASE WHEN CAST(f.feedback_date AS DATE) BETWEEN p.current_start AND p.current_end THEN 1 ELSE 0 END) AS current_period_complaints
            ,SUM(CASE WHEN CAST(f.feedback_date AS DATE) BETWEEN p.previous_start AND p.previous_end THEN f.affected_quantity ELSE 0 END) AS previous_period_defective_units
            ,SUM(CASE WHEN CAST(f.feedback_date AS DATE) BETWEEN p.current_start AND p.current_end THEN f.affected_quantity ELSE 0 END) AS current_period_defective_units
        FROM feedback f
        CROSS JOIN periods p
        WHERE f.feedback_type = 'complaint'
        GROUP BY f.product_id
    ),
    reason_stats AS (
        SELECT
            f.product_id,
            f.reason,
            SUM(CASE WHEN CAST(f.feedback_date AS DATE) BETWEEN p.previous_start AND p.previous_end THEN 1 ELSE 0 END) AS previous_period_reason_complaints,
            SUM(CASE WHEN CAST(f.feedback_date AS DATE) BETWEEN p.current_start AND p.current_end THEN 1 ELSE 0 END) AS current_period_reason_complaints
        FROM feedback f
        CROSS JOIN periods p
        WHERE f.feedback_type = 'complaint'
        GROUP BY f.product_id, f.reason
    ),
    refund_stats AS (
        SELECT 
            r.product_id,
            SUM(ref.amount) AS total_refund_amount_sgd
        FROM returns r
        JOIN refunds ref ON r.return_id = ref.return_id
        GROUP BY r.product_id
    )
    SELECT 
        p.product_id,
        p.product AS product_name,
        ps.total_units_sold,
        COALESCE(cs.total_complaints, 0) AS complaint_count,
        COALESCE(cs.defective_units, 0) AS defective_units,
        COALESCE(cs.total_returns, 0) AS return_count,
        ROUND((COALESCE(cs.defective_units, 0) * 100.0 / NULLIF(ps.total_units_sold, 0)), 4) AS complaint_rate_pct,
        COALESCE(rs.total_refund_amount_sgd, 0.0) AS total_refund_sgd,
        COALESCE(cs.previous_period_complaints, 0) AS previous_period_complaints,
        COALESCE(cs.current_period_complaints, 0) AS current_period_complaints,
        CASE WHEN COALESCE(cs.previous_period_complaints, 0) = 0 THEN NULL
             ELSE ROUND((cs.current_period_complaints - cs.previous_period_complaints) * 100.0 / cs.previous_period_complaints, 2)
        END AS complaint_change_pct,
        CAST(periods.previous_start AS DATE) AS previous_period_start,
        CAST(periods.previous_end AS DATE) AS previous_period_end,
        CAST(periods.current_start AS DATE) AS current_period_start,
        CAST(periods.current_end AS DATE) AS current_period_end,
        ROUND((COALESCE(cs.previous_period_defective_units, 0) * 100.0 / NULLIF(ps.previous_period_units_sold, 0)), 4) AS previous_period_complaint_rate_pct,
        ROUND((COALESCE(cs.current_period_defective_units, 0) * 100.0 / NULLIF(ps.current_period_units_sold, 0)), 4) AS current_period_complaint_rate_pct,
        (SELECT reason FROM reason_stats rstats WHERE rstats.product_id = p.product_id
         ORDER BY rstats.current_period_reason_complaints DESC, rstats.previous_period_reason_complaints DESC, rstats.reason
         LIMIT 1) AS top_complaint_reason,
        (SELECT previous_period_reason_complaints FROM reason_stats rstats WHERE rstats.product_id = p.product_id
         ORDER BY rstats.current_period_reason_complaints DESC, rstats.previous_period_reason_complaints DESC, rstats.reason
         LIMIT 1) AS previous_period_reason_complaints,
        (SELECT current_period_reason_complaints FROM reason_stats rstats WHERE rstats.product_id = p.product_id
         ORDER BY rstats.current_period_reason_complaints DESC, rstats.previous_period_reason_complaints DESC, rstats.reason
         LIMIT 1) AS current_period_reason_complaints
    FROM products p
    JOIN product_sales ps ON p.product_id = ps.product_id
    LEFT JOIN complaint_stats cs ON p.product_id = cs.product_id
    LEFT JOIN refund_stats rs ON p.product_id = rs.product_id
    CROSS JOIN periods
    ORDER BY current_period_complaints DESC, complaint_rate_pct DESC
    LIMIT 5;
    """
    rows = con.execute(query).fetchall()
    cols = [desc[0] for desc in con.description]
    results = [dict(zip(cols, row)) for row in rows]
    con.close()
    return results


def analyze_customer_enquiries_sla() -> list[dict]:
    """Analyzes customer support SLA and identifies unanswered high-intent leads."""
    results_by_status: dict[str, dict[str, object]] = {}
    for enquiry in load_customer_enquiries():
        status = enquiry.get("status", "")
        result = results_by_status.setdefault(
            status,
            {
                "status": status,
                "total_count": 0,
                "unanswered_leads": 0,
                "high_intent_missed": 0,
            },
        )
        result["total_count"] = int(result["total_count"]) + 1
        if status.lower() == "unanswered":
            if enquiry.get("intent", "").lower() == "lead":
                result["unanswered_leads"] = int(result["unanswered_leads"]) + 1
            if enquiry.get("intent_strength", "").lower() == "high":
                result["high_intent_missed"] = int(result["high_intent_missed"]) + 1
    return list(results_by_status.values())