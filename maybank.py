import re
import fitz
from datetime import datetime
from collections import defaultdict


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

    # ---------------- BANK NAME + STATEMENT YEAR ----------------
    bank_name = "Maybank"
    statement_year = None

    STATEMENT_DATE_RE = re.compile(
        r"STATEMENT\s+DATE\s*:?\s*(\d{2})/(\d{2})/(\d{2})"
    )

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

    # =========================================================
    # PARSER A — CLASSIC MAYBANK (UNCHANGED)
    # =========================================================
    DATE_RE_A = re.compile(
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
        sign = "+" if t.endswith("+") else "-" if t.endswith("-") else None
        v = float(t.replace(",", "").rstrip("+-"))
        return v, sign

    def parse_classic():
        transactions = []
        previous_balance = None

        for page_index, page in enumerate(doc):
            words = page.get_text("words")
            rows = [{
                "x": w[0],
                "y": round(w[1], 1),
                "text": str(w[4]).strip()
            } for w in words if str(w[4]).strip()]

            rows.sort(key=lambda r: (r["y"], r["x"]))
            used_y = set()

            for r in rows:
                if not DATE_RE_A.match(r["text"]):
                    continue

                y = r["y"]
                if y in used_y:
                    continue

                line = [w for w in rows if abs(w["y"] - y) <= 1.8]
                line.sort(key=lambda w: w["x"])

                date_iso = norm_date_a(r["text"], statement_year)
                if not date_iso:
                    continue

                desc, amounts = [], []
                for w in line:
                    if AMOUNT_RE_A.match(w["text"]):
                        amounts.append(w["text"])
                    else:
                        desc.append(w["text"])

                if not amounts:
                    continue

                balance, _ = parse_amt_a(amounts[-1])
                debit = credit = 0.0

                if previous_balance is not None:
                    delta = round(balance - previous_balance, 2)
                    if delta < 0:
                        debit = abs(delta)
                    elif delta > 0:
                        credit = delta
                else:
                    if len(amounts) >= 2:
                        txn, sign = parse_amt_a(amounts[-2])
                        if sign == "+":
                            credit = txn
                        elif sign == "-":
                            debit = txn

                transactions.append({
                    "date": date_iso,
                    "description": " ".join(desc),
                    "debit": round(debit, 2),
                    "credit": round(credit, 2),
                    "balance": round(balance, 2),
                    "page": page_index + 1,
                    "bank": bank_name,
                    "source_file": source_filename
                })

                previous_balance = balance
                used_y.add(y)

        return transactions

    # =========================================================
    # PARSER B — MAYBANK ISLAMIC (FIXED WITH test.py LOGIC)
    # =========================================================
    def parse_split_date_islamic():

        DATE_X0, DATE_X1 = 55, 160
        DESC_X0, DESC_X1 = 200, 460

        FOOTER_KEYWORDS = [
            "ENDING BALANCE",
            "LEDGER BALANCE",
            "TOTAL DEBITS",
            "TOTAL CREDITS",
            "END OF STATEMENT",
            "CHEQUES",
            "OVERDRAWN",
        ]

        MONTHS = {"JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"}

        def is_day(t): return t.isdigit() and 1 <= int(t) <= 31
        def is_month(t): return t.upper()[:3] in MONTHS
        def is_year(t): return t.isdigit() and t.startswith("20")

        def looks_like_money(t):
            try:
                float(t.replace(",", ""))
                return "." in t
            except:
                return False

        def extract_descriptions(words):
            date_regex = re.compile(r"\d{2}\s+[A-Za-z]{3}\s+\d{4}")
            lines = defaultdict(list)

            for x0, y0, x1, y1, text, *_ in words:
                lines[round(y0, 1)].append((x0, text))

            result = {}
            current_date = None
            current_desc = []

            for _, items in sorted(lines.items()):
                items.sort(key=lambda x: x[0])

                date_text = " ".join(t for x, t in items if DATE_X0 <= x <= DATE_X1)
                desc_text = " ".join(t for x, t in items if DESC_X0 <= x <= DESC_X1)

                if any(k in desc_text.upper() for k in FOOTER_KEYWORDS):
                    break

                if date_regex.fullmatch(date_text.strip()):
                    if current_date and current_desc:
                        result[current_date] = " ".join(current_desc)
                    current_date = date_text.strip()
                    current_desc = []
                    if desc_text.strip():
                        current_desc.append(desc_text.strip())
                elif current_date and desc_text.strip():
                    current_desc.append(desc_text.strip())

            if current_date and current_desc:
                result[current_date] = " ".join(current_desc)

            return result

        transactions = []
        previous_balance = None

        for page_index, page in enumerate(doc):
            words = page.get_text("words")
            desc_map = extract_descriptions(words)

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

                y = w1["y"]
                if y in used_y:
                    continue

                try:
                    date_iso = datetime.strptime(
                        f"{w1['text']} {w2['text']} {w3['text']}",
                        "%d %b %Y"
                    ).strftime("%Y-%m-%d")
                except:
                    continue

                raw_date = f"{w1['text']} {w2['text']} {w3['text']}"
                description = desc_map.get(raw_date, "")

                line = [w for w in rows if abs(w["y"] - y) <= 1.5]
                amounts = [w["text"] for w in line if looks_like_money(w["text"])]

                if not amounts:
                    continue

                balance = float(amounts[-1].replace(",", ""))
                debit = credit = 0.0

                if previous_balance is not None:
                    delta = round(balance - previous_balance, 2)
                    if delta < 0:
                        debit = abs(delta)
                    elif delta > 0:
                        credit = delta
                else:
                    if len(amounts) >= 2:
                        txn = float(amounts[-2].replace(",", ""))
                        if "CR" in description.upper():
                            credit = txn
                        else:
                            debit = txn

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
                used_y.add(y)

        return transactions

    # ---------------- RUN BOTH & MERGE ----------------
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
