# fraud.py
import re
from collections import defaultdict
from typing import List, Dict

# ==================================================
# CONFIGURATION
# ==================================================
TOP_N = 5
HIGH_VALUE_THRESHOLD = 100_000
THRESHOLD_MODE = "gte"   # "gte" (>=) or "lte" (<=)

# ==================================================
# PARTY NORMALIZATION
# ==================================================
def normalize_party(description: str) -> str:
    if not description:
        return "UNKNOWN"

    desc = str(description).upper()

    remove_patterns = [
        r"TRANSFER TO A/C",
        r"TRANSFER FR A/C",
        r"INTER-BANK PAYMENT INTO A/C",
        r"CMS - CR PYMT",
        r"DUITNOW QR-",
        r"\*",
        r"= BAKI LEGAR.*",
    ]
    for p in remove_patterns:
        desc = re.sub(p, "", desc)

    desc = re.sub(r"\s+", " ", desc).strip()

    # Numeric-only → bank clearing
    if re.fullmatch(r"[0-9 ]+", desc):
        return f"BANK_CLEARING_{desc}"

    # Trim long numeric tails (refs)
    desc = re.split(r"\d{6,}", desc)[0].strip()

    return desc[:80] if desc else "UNKNOWN"

# ==================================================
# FRAUD ENGINE (ONE PASS)
# ==================================================
def run_fraud_detection(transactions: List[Dict]) -> Dict:
    credit_by_party = defaultdict(float)
    debit_by_party = defaultdict(float)
    credit_tx_count = defaultdict(int)
    debit_tx_count = defaultdict(int)
    high_value_credits = []

    for tx in transactions or []:
        party = normalize_party(tx.get("description", ""))

        credit = float(tx.get("credit", 0) or 0)
        debit = float(tx.get("debit", 0) or 0)

        if credit > 0:
            credit_by_party[party] += credit
            credit_tx_count[party] += 1

            if (
                (THRESHOLD_MODE == "gte" and credit >= HIGH_VALUE_THRESHOLD)
                or (THRESHOLD_MODE == "lte" and credit <= HIGH_VALUE_THRESHOLD)
            ):
                high_value_credits.append({
                    "date": tx.get("date"),
                    "party": party,
                    "credit": round(credit, 2),
                    "description": tx.get("description")
                })

        if debit > 0:
            debit_by_party[party] += debit
            debit_tx_count[party] += 1

    top_credit = sorted(credit_by_party.items(), key=lambda x: x[1], reverse=True)[:TOP_N]
    top_debit = sorted(debit_by_party.items(), key=lambda x: x[1], reverse=True)[:TOP_N]

    return {
        "top_credit_parties": [
            {"party": p, "total_credit": round(v, 2), "credit_tx_count": credit_tx_count[p]}
            for p, v in top_credit
        ],
        "top_debit_parties": [
            {"party": p, "total_debit": round(v, 2), "debit_tx_count": debit_tx_count[p]}
            for p, v in top_debit
        ],
        "high_value_credits": high_value_credits,
        "config": {
            "top_n": TOP_N,
            "threshold": HIGH_VALUE_THRESHOLD,
            "threshold_mode": f"Credit {'≥' if THRESHOLD_MODE == 'gte' else '≤'} threshold"
        }
    }


# ==================================================
# INTER-TRANSACTION TRACE (BASIC)
# ==================================================
def trace_inter_transactions(transactions: List[Dict], company_name: str) -> Dict:
    """Trace transactions related to a given company name (simple substring match).

    Matching:
      - company name in normalized party, OR
      - company name in raw description (case-insensitive)

    Returns matched transactions + summary totals.
    """
    comp = (company_name or "").strip()
    if not comp:
        return {
            "company_name": company_name,
            "matched_transactions": [],
            "summary": {"count": 0, "total_credit": 0.0, "total_debit": 0.0, "net": 0.0},
        }

    comp_up = comp.upper()

    matched = []
    total_credit = 0.0
    total_debit = 0.0

    for tx in transactions:
        desc_raw = tx.get("description", "") or ""
        party = normalize_party(desc_raw)

        if comp_up in party or comp_up in desc_raw.upper():
            credit = float(tx.get("credit", 0) or 0)
            debit = float(tx.get("debit", 0) or 0)

            direction = "credit" if credit > 0 else "debit" if debit > 0 else "other"

            matched.append({
                "date": tx.get("date"),
                "party": party,
                "direction": direction,
                "credit": round(credit, 2),
                "debit": round(debit, 2),
                "description": tx.get("description"),
                "bank": tx.get("bank"),
                "source_file": tx.get("source_file"),
            })

            total_credit += credit
            total_debit += debit

    matched_sorted = sorted(matched, key=lambda x: (x.get("date") or ""))

    return {
        "company_name": company_name,
        "matched_transactions": matched_sorted,
        "summary": {
            "count": len(matched_sorted),
            "total_credit": round(total_credit, 2),
            "total_debit": round(total_debit, 2),
            "net": round(total_credit - total_debit, 2),
        },
    }
