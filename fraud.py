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
# NORMALIZATION UTILITIES
# ==================================================
def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().upper()


def normalize_party(description: str) -> str:
    desc = normalize_text(description)

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

    # Remove long numeric tails (references)
    desc = re.sub(r"\d{6,}", "", desc).strip()

    # Numeric-only references → bank clearing bucket
    if re.fullmatch(r"[0-9 ]+", desc):
        return f"BANK_CLEARING_{desc}"

    return desc[:80] if desc else "UNKNOWN"


# ==================================================
# PARSER 1: TOP PARTIES + HIGH-VALUE CREDITS
# ==================================================
def parse_top_parties_and_high_value(transactions: List[Dict]) -> Dict:
    credit_by_party = defaultdict(float)
    debit_by_party = defaultdict(float)
    credit_tx_count = defaultdict(int)
    debit_tx_count = defaultdict(int)
    high_value_credits = []

    for tx in transactions:
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

    top_credit = sorted(
        credit_by_party.items(),
        key=lambda x: x[1],
        reverse=True
    )[:TOP_N]

    top_debit = sorted(
        debit_by_party.items(),
        key=lambda x: x[1],
        reverse=True
    )[:TOP_N]

    return {
        "top_credit_parties": [
            {
                "party": p,
                "total_credit": round(v, 2),
                "credit_tx_count": credit_tx_count[p]
            } for p, v in top_credit
        ],
        "top_debit_parties": [
            {
                "party": p,
                "total_debit": round(v, 2),
                "debit_tx_count": debit_tx_count[p]
            } for p, v in top_debit
        ],
        "high_value_credits": high_value_credits
    }


# ==================================================
# PARSER 2: INTER-TRANSACTION TRACE (BY COMPANY NAME)
# ==================================================
def parse_inter_transactions(transactions: List[Dict], company_name: str) -> Dict:
    tokens = [
        t for t in normalize_text(company_name).split()
        if len(t) >= 3 and t not in {"SDN", "BHD", "BERHAD", "ENTERPRISE", "TRADING"}
    ]

    matched = []

    for tx in transactions:
        desc_norm = normalize_text(tx.get("description", ""))
        party_norm = normalize_party(tx.get("description", ""))

        haystack = f"{desc_norm} {party_norm}"

        # ✅ require ALL words to exist (SEP + ABADI)
        if tokens and all(t in haystack for t in tokens):
            matched.append(tx)

    total_credit = sum(float(tx.get("credit", 0) or 0) for tx in matched)
    total_debit  = sum(float(tx.get("debit", 0) or 0) for tx in matched)

    return {
        "company_name": company_name,
        "company_tokens": tokens,
        "transaction_count": len(matched),
        "total_credit": round(total_credit, 2),
        "total_debit": round(total_debit, 2),
        "net_flow": round(total_credit - total_debit, 2),
        "transactions": matched
    }
