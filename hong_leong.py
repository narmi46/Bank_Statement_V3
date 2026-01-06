import re
from datetime import datetime


# =========================================================
# MAIN ENTRY
# =========================================================

def parse_hong_leong(pdf, filename):
    transactions = []

    opening_balance = extract_opening_balance(pdf)
    running_balance = opening_balance

    for page_num, page in enumerate(pdf.pages, start=1):
        words = page.extract_words(use_text_flow=True)
        rows = group_words_by_row(words)

        for row in rows:
            date = extract_date(row)
            if not date:
                continue

            if is_total_row(row):
                continue

            description = extract_description(row)
            credit, debit = extract_credit_debit(row)

            if credit == 0 and debit == 0:
                continue

            running_balance = round(
                running_balance + credit - debit, 2
            )

            transactions.append({
                "date": date,
                "description": description,
                "debit": debit,
                "credit": credit,
                "balance": running_balance,
                "page": page_num,
                "bank": "Hong Leong Islamic Bank",
                "source_file": filename
            })

    return transactions


# =========================================================
# OPENING BALANCE
# =========================================================

def extract_opening_balance(pdf):
    text = pdf.pages[0].extract_text()

    m = re.search(
        r"Balance from previous statement\s+([\d,]+\.\d{2})",
        text,
        re.IGNORECASE
    )

    if not m:
        raise ValueError("Opening balance not found")

    return float(m.group(1).replace(",", ""))


# =========================================================
# ROW GROUPING (Y AXIS)
# =========================================================

def group_words_by_row(words, tolerance=3):
    rows = []

    for w in words:
        for row in rows:
            if abs(row[0]["top"] - w["top"]) <= tolerance:
                row.append(w)
                break
        else:
            rows.append([w])

    for row in rows:
        row.sort(key=lambda x: x["x0"])

    return rows


# =========================================================
# DATE DETECTION
# =========================================================

def extract_date(row):
    for w in row:
        if re.fullmatch(r"\d{2}-\d{2}-\d{4}", w["text"]):
            return datetime.strptime(
                w["text"], "%d-%m-%Y"
            ).strftime("%Y-%m-%d")
    return None


# =========================================================
# DESCRIPTION
# =========================================================

def extract_description(row):
    parts = []

    for w in row:
        t = w["text"]

        if re.fullmatch(r"\d{2}-\d{2}-\d{4}", t):
            continue
        if re.fullmatch(r"[\d,]+\.\d{2}", t):
            continue
        if is_noise(t):
            continue

        parts.append(t)

    return " ".join(parts).strip()


# =========================================================
# CREDIT / DEBIT (RELATIVE X — CORRECT WAY)
# =========================================================

def extract_credit_debit(row):
    amounts = []

    for w in row:
        if re.fullmatch(r"[\d,]+\.\d{2}", w["text"]):
            amounts.append({
                "x": w["x0"],
                "value": float(w["text"].replace(",", ""))
            })

    if not amounts:
        return 0.0, 0.0

    # sort by X position (left → right)
    amounts.sort(key=lambda x: x["x"])

    # ignore balance column (rightmost)
    if len(amounts) >= 3:
        amounts = amounts[:2]

    if len(amounts) == 2:
        credit = amounts[0]["value"]
        debit = amounts[1]["value"]
    else:
        credit = 0.0
        debit = amounts[0]["value"]

    return round(credit, 2), round(debit, 2)


# =========================================================
# FILTER TOTAL ROWS
# =========================================================

def is_total_row(row):
    text = " ".join(w["text"] for w in row)
    return bool(re.search(
        r"Total Withdrawals|Total Deposits|Closing Balance",
        text,
        re.IGNORECASE
    ))


# =========================================================
# NOISE FILTER
# =========================================================

def is_noise(text):
    return bool(re.search(
        r"Protected by PIDM|Hong Leong Islamic Bank|hlisb\.com\.my",
        text,
        re.IGNORECASE
    ))
