import re
from datetime import datetime


# ============================================================
# MAIN ENTRY
# ============================================================

def parse_hong_leong(pdf, filename):
    """
    Parse Hong Leong Islamic Bank (HLIB) CURRENT ACCOUNT-i statement
    New format: DD-MM-YYYY + multi-line description + amounts may be partial
    Compatible with Streamlit app.py
    """

    transactions = []

    for page_num, page in enumerate(pdf.pages, start=1):
        text = page.extract_text()
        if not text:
            continue

        transactions.extend(
            extract_transactions_from_page_hlib(text, page_num, filename)
        )

    return transactions


# ============================================================
# PAGE PARSING
# ============================================================

def extract_transactions_from_page_hlib(text, page_num, filename):
    """
    Strategy:
    - Every transaction begins with a DATE line: DD-MM-YYYY ...
    - Description can span multiple lines
    - Amounts can appear:
        * on the first date line itself
        * inside description block
        * sometimes balance is missing (then set balance=None)
    - We read UNTIL we hit the next date line
    """
    lines = text.split("\n")
    i = 0
    txs = []

    while i < len(lines):
        line = lines[i].strip()

        # Detect transaction start
        date_match = re.match(r"^(\d{2}-\d{2}-\d{4})\s+(.*)$", line)
        if not date_match:
            i += 1
            continue

        date_str, first_desc = date_match.groups()

        # Start collecting this transaction block
        desc_lines = [first_desc] if first_desc else []
        all_amounts = []

        # also capture amounts that might appear on the same first line
        all_amounts.extend(re.findall(r"[\d,]+\.\d{2}", line))

        i += 1

        # Collect block lines until next transaction date starts
        while i < len(lines):
            l = lines[i].strip()

            # next transaction begins → stop current block
            if re.match(r"^\d{2}-\d{2}-\d{4}\s+", l):
                break

            # ignore headers/footers
            if not should_skip_line(l):
                desc_lines.append(l)

                # gather numeric amounts from lines in block
                nums = re.findall(r"[\d,]+\.\d{2}", l)
                if nums:
                    all_amounts.extend(nums)

            i += 1

        # ------------------------------------------------------------
        # Amount interpretation (HLIB)
        #
        # In your statement, the final numeric values usually mean:
        # - If 3 nums: deposit, withdrawal, balance
        # - If 2 nums: withdrawal, balance
        # - If 1 num : withdrawal OR fee-only (balance missing)
        #
        # We keep it robust:
        # - If balance found => last number used as balance
        # - Credit not always present in extracted text, so set to 0 unless detected
        #
        # NOTE: This prevents "missing transactions" by always outputting a row.
        # ------------------------------------------------------------
        deposit = 0.0
        withdrawal = 0.0
        balance = None

        if len(all_amounts) >= 3:
            # safest: take last 3 numbers as (deposit, withdrawal, balance)
            dep_str, wd_str, bal_str = all_amounts[-3], all_amounts[-2], all_amounts[-1]
            deposit = float(dep_str.replace(",", ""))
            withdrawal = float(wd_str.replace(",", ""))
            balance = float(bal_str.replace(",", ""))

        elif len(all_amounts) == 2:
            # safest: (withdrawal, balance)
            wd_str, bal_str = all_amounts[-2], all_amounts[-1]
            withdrawal = float(wd_str.replace(",", ""))
            balance = float(bal_str.replace(",", ""))

        elif len(all_amounts) == 1:
            # amount-only tx (fees etc) — keep balance None
            withdrawal = float(all_amounts[0].replace(",", ""))

        # Create transaction record
        txs.append({
            "date": datetime.strptime(date_str, "%d-%m-%Y").strftime("%Y-%m-%d"),
            "description": clean_description(desc_lines),
            "debit": round(withdrawal, 2),
            "credit": round(deposit, 2),
            "balance": round(balance, 2) if balance is not None else None,
            "page": page_num,
            "bank": "Hong Leong Islamic Bank",
            "source_file": filename
        })

    return txs


# ============================================================
# HELPERS
# ============================================================

def clean_description(lines):
    """
    Join multi-line description into one line
    """
    desc = " ".join([x.strip() for x in lines if x and x.strip()])
    desc = re.sub(r"\s+", " ", desc).strip()
    return desc


def should_skip_line(line):
    """
    Filter out statement headers/footers and junk lines.
    """
    if not line:
        return True

    skip_patterns = [
        r"^CURRENT ACCOUNT",
        r"^ACCOUNT\-i STATEMENT",
        r"^Protected by PIDM",
        r"^Dilindungi oleh PIDM",
        r"^Page No",
        r"^Date / Tarikh",
        r"^A/C No",
        r"^Statement Period",
        r"^Branch / Cawangan",
        r"^Tel No",
        r"^Date Transaction Description",
        r"^Tarikh Deskripsi",
        r"^Hong Leong Islamic Bank",
        r"^Menara Hong Leong",
        r"^hlisb\.com\.my",
        r"^Total Withdrawals",
        r"^Total Deposits",
        r"^Closing Balance",
        r"^Important Notices",
        r"^\d+_\d+\s+\d+$",     # e.g. 36301131050_5 3
        r"^PTJ$",
    ]

    return any(re.search(p, line, re.IGNORECASE) for p in skip_patterns)
