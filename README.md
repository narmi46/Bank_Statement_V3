# Bank_Statement_V3

Streamlit tools for parsing Malaysian bank statements and running fraud-focused analysis.

## Apps
- `app.py`: multi-bank PDF statement parser with exports (JSON/XLSX).
- `fraud_app.py`: fraud analyzer for `transactions.json` or `full_report.json`.

## Key Fraud Features
- Top credit/debit counterparties.
- Configurable high-value credit detection (Top-N, threshold value, threshold mode).
- Inter-transaction company trace with relevance-based matching.
