import re
import fitz
from datetime import datetime
from collections import defaultdict


# =========================================================
# SHARED: multiline description extractor (test.py style)
# - Groups by Y
# - Detects a new txn when date appears in date column (X range)
# - Appends continuation lines from description column (X range)
# - Stops at footer keywords
# Returns: dict { y_bucket_start : "full description..." }
# =========================================================
def _extract_multiline_desc_by_y(words, date_x_range, desc_x_range, date_regex, footer_keywords):
    lines = defaultdict(list)
    for x0, y0, x1, y1, text, *_ in words:
        t = str(text).strip()
        if not t:
            continue
        lines[round(y0, 1)].append((x0, t))

    sorted_lines = sorted(lines.items(), key=lambda x: x[0])

    desc_by_y = {}
    current_y = None
    current_desc = []

    for y, items in sorted_lines:
        items.sort(key=lambda x: x[0])

        date_text = " ".join(
            t for x, t in items if date_x_range[0] <= x <= date_x_range[1]
        ).strip()
        desc_text = " ".join(
            t for x, t in items if desc_x_range[0] <= x <= desc_x_range[1]
        ).strip()

        date_text = re.sub(r"\s+", " ", date_text)
        desc_text = re.sub(r"\s+", " ", desc_text)

        # stop at footer
        if any(k in desc_text.upper() for k in footer_keywords):
            break

        # new transaction row
        if date_regex.fullmatch(date_text):
            if current_y is not None:
                desc_by_y[current_y] = " ".join(current_desc).strip()

            current_y = y
            current_desc = []
            if desc_text:
                current_desc.append(desc_text)

        # continuation lines
        elif current_y is not None and desc_text:
            current_desc.append(desc_text)

    # last txn
    if current_y is not None:
        desc_by_y[current_y] = " ".join(current_desc).strip()

    return desc_by_y


# =========================================================
# MAIN ENTRY (USED BY app.py)
# =========================================================
def parse_transactions_maybank(pdf_input, source_filename):
    # ---------------- OPEN PDF (Streamlit-safe) ----------------
    def open_doc(inp):
        if hasattr(inp, "stream"):
            inp.stream.seek(0)
            data = inp.stream.read()
            return fitz.open(stream=data, filetype="pdf")
        return fitz.open(inp)

    doc = open_doc(pdf_input)

    # ---------------- BANK NAME / YEAR ----------------
    bank_name = "Maybank"
    statement_year = None

    STATEMENT_DATE_RE = re.compile(r"STATEMENT\s+DATE\s*:?\s*(\d{2})/(\d{2})/(\d{2})")

    for p in range(min(2, len(doc))):
        txt = doc[p].get_text("text").upper()

        if "MAYBANK ISLAMIC" in txt:
            bank_name = "Maybank Islamic"
        elif "MAYBANK" in txt:
            bank_name = "Maybank"

        m = STATEMENT_DATE_RE.search(txt)
        if m:
            statement_year = f"20{int(m.group(3)):02d}"
            break

    if not statement_year:
        statement_year = str(datetime.now().year)

    # ---------------- COMMON FOOTER KEYWORDS ----------------
    FOOTER_KEYWORDS = [
        "ENDING BALANCE",
        "LEDGER BALANCE",
        "TOTAL DEBITS",
        "TOTAL CREDITS",
        "END OF STATEMENT",
        "CHEQUES",
        "OVERDRAWN",
    ]

    # =========================================================
    # PARSER A — CLASSIC MAYBANK (NOW MULTILINE DESCRIPTION)
    # Example: Larney, Maza, MyTuto
    # =========================================================
    DATE_RE_A_TOKEN = re.compile(
        r"^("
        r"\d{2}/\d{2}/\d{4}|"
        r"\d{2}/\d{2}|"
        r"\d{2}-\d{2}|"
        r"\d{2}\s+[A-Z]{3}"
        r")$",
        re.IGNORECASE
    )
    AMOUNT_RE_A = re.compile(r"^(?:\d{1,3}(?:,\d{3})*|\d+)?\.\d{2}[+-]?$")

    def norm_date_a(token, year):
        token = token.strip().upper()
        for fmt in ("%d/%m/%Y", "%d/%m", "%d-%m", "%d %b"):
            try:
                if fmt == "%d/%m/%Y":
                    dt = datetime.strptime(token, fmt)
                else:
                    dt = datetime.strptime(f"{token}/{year}", fmt + "/%Y")
                return dt.strftime("%Y-%m-%d")
            except:
                pass
        return None

    def parse_amt_a(t):
        t = t.strip()
        sign = "+" if t.endswith("+") else "-" if t.endswith("-") else None
        v = float(t.replace(",", "").rstrip("+-"))
        return v, sign

    def parse_classic():
        transactions = []
        previous_balance = None

        # For classic statements (like your Jan 2025), the "date column" is short like 01/01
        # Use a relaxed date regex matching the date text extracted from the date column.
        date_regex_column = re.compile(
            r"^("
            r"\d{2}/\d{2}(?:/\d{4})?|"
            r"\d{2}-\d{2}|"
            r"\d{2}\s+[A-Za-z]{3}(?:\s+\d{4})?"
            r")$"
        )

        # X-ranges used to build multiline description blocks (same technique as test.py)
        DATE_X0, DATE_X1 = 55, 160
        DESC_X0, DESC_X1 = 200, 460

        for page_index, page in enumerate(doc):
            words = page.get_text("words")

            # 1) Build multiline descriptions keyed by txn start y
            desc_by_y = _extract_multiline_desc_by_y(
                words=words,
                date_x_range=(DATE_X0, DATE_X1),
                desc_x_range=(DESC_X0, DESC_X1),
                date_regex=date_regex_column,
                footer_keywords=FOOTER_KEYWORDS,
            )

            # 2) Continue with existing amount/balance parsing, but description comes from desc_by_y
            rows = [{
                "x0": w[0],
                "y0": round(w[1], 1),
                "text": str(w[4]).strip()
            } for w in words if str(w[4]).strip()]

            rows.sort(key=lambda r: (r["y0"], r["x0"]))
            used_y = set()

            for r in rows:
                token = r["text"]
                if not DATE_RE_A_TOKEN.match(token):
                    continue

                y = r["y0"]
                if y in used_y:
                    continue

                # gather same-line amounts (balance is normally last amount)
                line = [w for w in rows if abs(w["y0"] - y) <= 1.8]
                line.sort(key=lambda w: w["x0"])

                date_iso = norm_date_a(token, statement_year)
                if not date_iso:
                    continue

                amounts = []
                for w in line:
                    if AMOUNT_RE_A.match(w["text"]):
                        amounts.append((w["x0"], w["text"]))

                if not amounts:
                    continue

                amounts.sort(key=lambda a: a[0])
                balance_val, _ = parse_amt_a(amounts[-1][1])

                txn_val = txn_sign = None
                if len(amounts) > 1:
                    txn_val, txn_sign = parse_amt_a(amounts[-2][1])

                # ✅ NEW: multiline description (same idea as parser B)
                description = desc_by_y.get(y, "").strip()
                description = " ".join(description.split())  # normalize spaces

                debit = credit = 0.0
                if previous_balance is not None:
                    delta = round(balance_val - previous_balance, 2)
                    if delta > 0:
                        credit = abs(delta)
                    elif delta < 0:
                        debit = abs(delta)
                    else:
                        if txn_sign == "+" and txn_val is not None:
                            credit = txn_val
                        elif txn_sign == "-" and txn_val is not None:
                            debit = txn_val
                else:
                    if txn_sign == "+" and txn_val is not None:
                        credit = txn_val
                    elif txn_sign == "-" and txn_val is not None:
                        debit = txn_val

                used_y.add(y)
                transactions.append({
                    "date": date_iso,
                    "description": description,
                    "debit": round(debit, 2),
                    "credit": round(credit, 2),
                    "balance": round(balance_val, 2),
                    "page": page_index + 1,
                    "bank": bank_name,
                    "source_file": source_filename
                })

                previous_balance = balance_val

        return transactions

    # =========================================================
    # PARSER B — MAYBANK ISLAMIC (multiline description already)
    # Example: Clear Water Service
    # =========================================================
    MONTHS = {"Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"}

    def is_day(t): return t.isdigit() and 1 <= int(t) <= 31
    def is_month(t): return t.capitalize() in MONTHS
    def is_year(t): return t.isdigit() and t.startswith("20")

    def parse_amount(v):
        return float(v.replace(",", ""))

    def looks_like_money(t):
        tt = t.replace(",", "")
        if "." not in tt:
            return False
        try:
            float(tt)
            return True
        except:
            return False

    def parse_split_date_islamic():
        transactions = []
        previous_balance = None

        # X ranges used for multiline extraction (same technique as test.py)
        DATE_X0, DATE_X1 = 55, 160
        DESC_X0, DESC_X1 = 200, 460

        # Date column shows full like "01 Jan 2025" for Islamic-style extractor
        date_regex_column = re.compile(r"^\d{2}\s+[A-Za-z]{3}\s+\d{4}$")

        for page_index, page in enumerate(doc):
            words = page.get_text("words")

            # Multiline descriptions keyed by txn start y
            desc_by_y = _extract_multiline_desc_by_y(
                words=words,
                date_x_range=(DATE_X0, DATE_X1),
                desc_x_range=(DESC_X0, DESC_X1),
                date_regex=date_regex_column,
                footer_keywords=FOOTER_KEYWORDS,
            )

            rows = [{
                "x": w[0],
                "y": round(w[1], 1),
                "text": str(w[4]).strip()
            } for w in words if str(w[4]).strip()]

            rows.sort(key=lambda r: (r["y"], r["x"]))
            used_y = set()

            for i in range(len(rows) - 2):
                w1, w2, w3 = rows[i], rows[i+1], rows[i+2]
                if not (is_day(w1["text"]) and is_month(w2["text"]) and is_year(w3["text"])):
                    continue

                y_key = w1["y"]
                if y_key in used_y:
                    continue

                try:
                    date_iso = datetime.strptime(
                        f"{w1['text']} {w2['text']} {w3['text']}",
                        "%d %b %Y"
                    ).strftime("%Y-%m-%d")
                except:
                    continue

                # ✅ multiline description from extractor
                description = desc_by_y.get(y_key, "").strip()
                description = " ".join(description.split())

                line = [w for w in rows if abs(w["y"] - y_key) <= 1.5]
                line.sort(key=lambda w: w["x"])

                amounts = [w["text"] for w in line if looks_like_money(w["text"])]
                if not amounts:
                    continue

                balance = parse_amount(amounts[-1])
                debit = credit = 0.0

                if previous_balance is not None:
                    delta = round(balance - previous_balance, 2)
                    if delta < 0:
                        debit = abs(delta)
                    elif delta > 0:
                        credit = delta
                else:
                    if len(amounts) >= 2:
                        txn_amt = parse_amount(amounts[-2])
                        desc_up = description.upper()
                        if ("CR" in desc_up) or ("CREDIT" in desc_up):
                            credit = txn_amt
                        else:
                            debit = txn_amt

                transactions.append({
                    "date": date_iso,
                    "description": description,
                    "debit": round(debit, 2),
                    "credit": round(credit, 2),
                    "balance": round(balance, 2),
                    "page": page_index + 1,
                    "bank": bank_name,
                    "source_file": source_filename
                })

                previous_balance = balance
                used_y.add(y_key)

        return transactions

    # ---------------- RUN BOTH + MERGE ----------------
    tx_a = parse_classic()
    tx_b = parse_split_date_islamic()

    tx = tx_a if len(tx_a) >= len(tx_b) else tx_b

    if tx_a and tx_b:
        seen = set()
        merged = []
        for t in (tx_a + tx_b):
            key = (
                t["date"],
                t["description"],
                t["debit"],
                t["credit"],
                t["balance"],
                t["page"],
                t["source_file"],
            )
            if key not in seen:
                seen.add(key)
                merged.append(t)
        tx = merged

    doc.close()
    return tx
