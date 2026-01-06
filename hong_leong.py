import re
from datetime import datetime


def parse_hong_leong(pdf, filename):
    """
    Hong Leong Islamic Bank – CURRENT ACCOUNT-i (NEW FORMAT)
    Compatible with app.py
    """
    transactions = []

    for page_num, page in enumerate(pdf.pages, start=1):
        text = page.extract_text()
        if not text:
            continue

        transactions.extend(
            extract_transactions_from_page(text, page_num, filename)
        )

    return transactions


def extract_transactions_from_page(text, page_num, filename):
    lines = text.split("\n")
    i = 0
    transactions = []

    while i < len(lines):
        line = lines[i].strip()

        # Transaction always starts with DD-MM-YYYY
        match = re.match(r"^(\d{2}-\d{2}-\d{4})\s+(.+)$", line)
        if not match:
            i += 1
            continue

        date_str, first_desc = match.groups()
        desc_lines = [first_desc]
        i += 1

        # Collect multiline description
        while i < len(lines):
            current = lines[i].strip()

            # Stop when amount line detected
            if re.search(r"[\d,]+\.\d{2}", current):
                break

            if not should_skip_line(current):
                desc_lines.append(current)

            i += 1

        if i >= len(lines):
            break

        amount_line = lines[i]
        numbers = re.findall(r"[\d,]+\.\d{2}", amount_line)

        deposit = withdrawal = balance = 0.0

        if len(numbers) == 3:
            deposit, withdrawal, balance = numbers
        elif len(numbers) == 2:
            withdrawal, balance = numbers
        elif len(numbers) == 1:
            balance = numbers[0]

        transactions.append({
            "date": datetime.strptime(date_str, "%d-%m-%Y").strftime("%Y-%m-%d"),
            "description": clean_description(desc_lines),
            "debit": float(withdrawal.replace(",", "")) if withdrawal else 0.0,
            "credit": float(deposit.replace(",", "")) if deposit else 0.0,
            "balance": float(balance.replace(",", "")),
            "page": page_num,
            "bank": "Hong Leong Islamic Bank",
            "source_file": filename
        })

        i += 1

    return transactions


def clean_description(lines):
    return re.sub(r"\s+", " ", " ".join(lines)).strip()


def should_skip_line(line):
    skip_patterns = [
        r"^CURRENT ACCOUNT",
        r"^Protected by PIDM",
        r"^Dilindungi oleh PIDM",
        r"^Page No",
        r"^Date / Tarikh",
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
        r"^\s*$"
    ]

    return any(re.search(p, line, re.IGNORECASE) for p in skip_patterns)
