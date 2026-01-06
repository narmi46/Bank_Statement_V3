import re
from datetime import datetime


# =========================================================
# MAIN ENTRY (USED BY app.py)
# =========================================================

def parse_hong_leong(pdf, filename):
    transactions = []

    opening_balance = extract_opening_balance(pdf)
    running_balance = opening_balance

    for page_num, page in enumerate(pdf.pages, start=1):
        words = page.extract_words(
            use_text_flow=True,
            keep_blank_chars=False
        )

        rows = group_words_by_row(words)

        for row in rows:
            date = extract_date(row)
            if not date:
                continue

            description = extract_description(row)
            credit, debit = extract_credit_debit(row)

            # Skip empty rows
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

    match = re.search(
        r"Balance from previous statement\s+([\d,]+\.\d{2})",
        text,
        re.IGNORECASE
    )

    if not match:
        raise ValueError("Opening balance not found")

    return float(match.group(1).replace(",", ""))


# =========================================================
# GROUP WORDS BY ROW (Y AXIS)
# =========================================================

def group_words_by_row(words, tolerance=3):
    rows = []

    for w in words:
        placed = False
        for row in rows:
            if abs(row[0]["top"] - w["top"]) <= tolerance:
                row.append(w)
                placed = True
                break

        if not placed:
            rows.append([w])

    # sort each row by X position
    for row in rows:
        row.sort(key=lambda x: x["x0"])

    return rows


# =========================================================
# DATE DETECTION (ANCHOR)
# =========================================================

def extract_date(row):
    for w in row:
        if re.fullmatch(r"\d{2}-\d{2}-\d{4}", w["text"]):
            return datetime.strptime(
                w["text"], "%d-%m-%Y"
            ).strftime("%Y-%m-%d")
    return None


# =========================================================
# DESCRIPTION (NON-NUMERIC, NON-DATE)
# =========================================================

def extract_description(row):
    parts = []

    for w in row:
        if re.fullmatch(r"\d{2}-\d{2}-\d{4}", w["text"]):
            continue
        if re.fullmatch(r"[\d,]+\.\d{2}", w["text"]):
            continue
        if should_skip_text(w["text"]):
            continue

        parts.append(w["text"])

    return " ".join(parts).strip()


# =========================================================
# CREDIT / DEBIT USING X POSITION
# =========================================================

def extract_credit_debit(row):
    credit = 0.0
    debit = 0.0

    for w in row:
        if re.fullmatch(r"[\d,]+\.\d{2}", w["text"]):
            amount = float(w["text"].replace(",", ""))

            # YOUR RULE:
            # Lower X  -> CREDIT
            # Higher X -> DEBIT
            if w["x0"] < 350:
                credit += amount
            else:
                debit += amount

    return round(credit, 2), round(debit, 2)


# =========================================================
# FILTER JUNK TEXT
# =========================================================

def should_skip_text(text):
    skip_patterns = [
        r"^CURRENT ACCOUNT",
        r"^Protected by PIDM",
        r"^Dilindungi oleh PIDM",
        r"^Page No",
        r"^Date / Tarikh",
        r"^A/C No",
        r"^Statement Period",
        r"^Branch / Cawangan",
        r"^Tel No",
        r"^Hong Leong Islamic Bank",
        r"^Menara Hong Leong",
        r"^hlisb\.com\.my",
        r"^Total Withdrawals",
        r"^Total Deposits",
        r"^Closing Balance",
        r"^Important Notices",
        r"^\d+_\d+\s+\d+$",
        r"^PTJ$"
    ]

    return any(re.search(p, text, re.IGNORECASE) for p in skip_patterns)
