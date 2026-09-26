# Finance Bee — scoped implementation

Branch `feat/finance-bee-analysis`. No other Bee implementation, routing, Guard rules, shared response schema, frontend, dataset source or AWS resource was modified. The only shared-file edit is inside localization's Finance-only branch: non-receivables reports and failures retain their truthful English summary rather than being replaced with a misleading zero-overdue Chinese summary.

## Capabilities

- Existing finance summary contract remains overdue invoice count/outstanding amount, fixed default cutoff 2026-09-23.
- With payments.csv present, reconstruct invoice balances from issue/payment dates, ignoring future payments. Return not-due, 1–30, 31–60, 61–90 and over-90-day buckets plus outstanding exposure by customer ID. Due today is not overdue. Without dated payments, the existing cutoff snapshot still works, but historical dates fail explicitly.
- Profitability: ledger net revenue after returns, COGS, gross profit, operating expenses, profit before tax and margins. Zero/non-positive revenue produces undefined margins, not division by zero or an invented percentage.
- Operating expenses: account-code breakdown from ledger postings. Depreciation is an expense, not a cash payment.
- Cash: opening balance plus dated receipts minus dated payments equals closing cash. Opening-balance journals are excluded from period cash flow; movements are grouped by source. Never sum supporting CSV totals on top of ledger balances.
- Month-to-date default, last calendar month and year-to-date phrases; explicit period_start/as_of supported by the Python Finance function. Comparison is the preceding equal-length interval, labelled with dates, not a falsely labelled calendar month. Comparisons outside data coverage are omitted. Selected unsupported date phrases return clarification instead of silently using this month; this is not a general natural-language date parser.
- SGD only; Decimal calculations. Duplicate records, unknown accounts, non-finite/negative monetary fields, invalid dates, mixed currencies, unbalanced journals and missing files fail closed. Connections/files are closed. Numeric evidence remains compatible with the existing response schema.
- Receivable reminder proposals retain the existing AMBER action; no reminder is proposed with zero overdue invoices. New ledger analyses are read-only and introduce no new Guard action names or executor.

## Verified dataset baseline

Full-history interval 2023-01-01 through 2026-09-23, SGD:

| Metric | Value |
| --- | ---: |
| Net revenue | 10,087,199.00 |
| Gross profit | 3,902,708.30 |
| Operating expenses | 1,140,703.36 |
| Profit before tax | 2,762,004.94 |
| Opening cash | 500,000.00 |
| Net cash flow | 2,799,719.68 |
| Closing cash | 3,299,719.68 |
| Overdue invoices | 528 |
| Overdue outstanding | 209,354.00 |

These were recomputed locally and compared to scenario_expectations.csv; they are not current real-world business figures. The ledger contains 273,036 lines. Existing source CSVs were not regenerated.

## Tests

`PYTHONPATH=. BIZZY_FINANCE_DATA_DIR=../BizzyData/data/demo python -m pytest -q tests/test_finance_bee.py tests/test_finance_analysis.py`

Includes balanced-ledger reconciliation, opening entries, refund impact, prior periods, future postings/payments, partial payments, ageing boundaries, invalid records, missing files, margins and Finance-only localization. Full-dataset scenario test is opt-in because the current container omits required finance files. No inference or cloud calls are needed.

## Explicit integration boundaries

1. Current backend archive contains neither accounts.csv/accounting_ledger.csv nor payments.csv. **Do not deploy this as complete Finance support yet.** A separately approved packaging-only change must add those pinned files and refresh archive checksums. No change to dataset contents is needed. Supplier/expense/opening CSVs already reconcile through ledger postings; their totals must not be added again.
2. Queen routing was not changed: terms such as profit may be sent to Sales or need Bedrock routing; the direct Finance function supports the new intents. API `/finance/summary` still defaults to overdue receivables because its signature was not changed. Exposing structured dates or improving cross-Bee routing requires separate authorization.
3. Advisor and Guard were not changed. Advanced Finance evidence is available as structured data; no promise that other Bees interpret every new metric. Full new-language summaries are not implemented; the Finance-only localization guard preserves amounts and intent through English fallback.
4. Monthly expense recognition follows actual posting dates. A month-to-date report can omit expenses recognized at month end; it is not a forecast or accrual estimate beyond the ledger.
5. Historical recorded supplier payments/refunds are evidence only, never authorization to make payments. No autonomous financial action exists.

Packaging, shared routing/API work and deployment remain separate decisions; this Finance-only change does not authorize them.
