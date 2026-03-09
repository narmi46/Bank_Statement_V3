# fraud_parser.py
import re
from collections import defaultdict
from typing import Any, Dict, List


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
        desc = re.sub(p, "", desc, flags=re.IGNORECASE)

    # Remove long numeric tails (references)
    desc = re.sub(r"\d{6,}", "", desc).strip()

    # Numeric-only references → bank clearing bucket
    if re.fullmatch(r"[0-9 ]+", desc):
        return f"BANK_CLEARING_{desc}"

    return desc[:80] if desc else "UNKNOWN"


def safe_float(value: Any) -> float:
    """Convert numeric strings to float safely.
    Handles None, empty strings, commas, and (1,234.56) parentheses negatives.
    """
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)

    s = str(value).strip()
    if not s:
        return 0.0

    # Common banking prefixes
    s = re.sub(r"^(RM|MYR)\s*", "", s, flags=re.IGNORECASE)

    neg = False
    if s.startswith("(") and s.endswith(")"):
        neg = True
        s = s[1:-1].strip()

    if s.endswith("-"):
        neg = True
        s = s[:-1].strip()

    # remove commas and non-numeric symbols (keeps minus and dot)
    s = s.replace(",", "")
    s = re.sub(r"[^0-9.\-]", "", s)

    if s in {"", "-", "."}:
        return 0.0

    try:
        f = float(s)
        return -f if neg else f
    except Exception:
        return 0.0


# ==================================================
# PARSER 1: TOP PARTIES + HIGH-VALUE CREDITS
# ==================================================
def parse_top_parties_and_high_value(
    transactions: List[Dict],
    top_n: int = TOP_N,
    threshold: float = HIGH_VALUE_THRESHOLD,
    threshold_mode: str = THRESHOLD_MODE,
) -> Dict:
    credit_by_party = defaultdict(float)
    debit_by_party = defaultdict(float)
    credit_tx_count = defaultdict(int)
    debit_tx_count = defaultdict(int)
    high_value_credits = []

    for tx in transactions:
        party = normalize_party(tx.get("description", ""))

        credit = safe_float(tx.get("credit", 0))
        debit = safe_float(tx.get("debit", 0))

        if credit > 0:
            credit_by_party[party] += credit
            credit_tx_count[party] += 1

            if (
                (threshold_mode == "gte" and credit >= threshold)
                or (threshold_mode == "lte" and credit <= threshold)
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
    )[:top_n]

    top_debit = sorted(
        debit_by_party.items(),
        key=lambda x: x[1],
        reverse=True
    )[:top_n]

    return {
        "config": {
            "top_n": top_n,
            "high_value_threshold": threshold,
            "threshold_mode": threshold_mode,
        },
        "totals": {
            "transactions": len(transactions),
            "credit_parties": len(credit_by_party),
            "debit_parties": len(debit_by_party),
        },
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
    STOPWORDS = {
        "SDN", "BHD", "BERHAD", "ENTERPRISE", "ENT",
        "TRADING", "TRADERS", "RESOURCES",
        "COMPANY", "CO", "LTD", "LIMITED",
        "PERNIAGAAN"
    }

    tokens = [
        t for t in normalize_text(company_name).split()
        if len(t) >= 3 and t not in STOPWORDS
    ]

    matched = []
    min_matches = 1 if len(tokens) <= 2 else 2

    for tx in transactions:
        desc_norm = normalize_text(tx.get("description", ""))
        party_norm = normalize_party(tx.get("description", ""))
        haystack = f"{desc_norm} {party_norm}"

        matched_tokens = [t for t in tokens if t in haystack]

        # match if ANY strong token exists
        if len(matched_tokens) >= min_matches:
            tx_copy = dict(tx)
            tx_copy["_matched_tokens"] = matched_tokens
            tx_copy["_match_score"] = len(matched_tokens)
            matched.append(tx_copy)

    matched.sort(
        key=lambda tx: (
            tx.get("_match_score", 0),
            safe_float(tx.get("credit", 0)) + safe_float(tx.get("debit", 0)),
        ),
        reverse=True,
    )

    total_credit = sum(safe_float(tx.get("credit", 0)) for tx in matched)
    total_debit  = sum(safe_float(tx.get("debit", 0)) for tx in matched)

    return {
        "company_name": company_name,
        "company_tokens": tokens,
        "min_token_matches": min_matches,
        "transaction_count": len(matched),
        "total_credit": round(total_credit, 2),
        "total_debit": round(total_debit, 2),
        "net_flow": round(total_credit - total_debit, 2),
        "transactions": matched
    }
