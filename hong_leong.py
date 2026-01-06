    import re
    from datetime import datetime
    
    def parse_hong_leong(pdf, filename):
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
        txs = []
    
        while i < len(lines):
            line = lines[i].strip()
    
            date_match = re.match(r"^(\d{2}-\d{2}-\d{4})\s+(.*)$", line)
            if not date_match:
                i += 1
                continue
    
            date_str, first_desc = date_match.groups()
            desc_lines = [first_desc]
            amounts = []
            balance = None
    
            i += 1
    
            # Collect until next DATE or footer
            while i < len(lines):
                l = lines[i].strip()
    
                if re.match(r"^\d{2}-\d{2}-\d{4}\s+", l):
                    break
    
                if not should_skip_line(l):
                    desc_lines.append(l)
    
                    nums = re.findall(r"[\d,]+\.\d{2}", l)
                    amounts.extend(nums)
    
                i += 1
    
            deposit = withdrawal = 0.0
    
            # Heuristic:
            if len(amounts) >= 2:
                withdrawal = float(amounts[-2].replace(",", ""))
                balance = float(amounts[-1].replace(",", ""))
            elif len(amounts) == 1:
                withdrawal = float(amounts[0].replace(",", ""))
    
            txs.append({
                "date": datetime.strptime(date_str, "%d-%m-%Y").strftime("%Y-%m-%d"),
                "description": clean_description(desc_lines),
                "debit": withdrawal,
                "credit": deposit,
                "balance": balance,
                "page": page_num,
                "bank": "Hong Leong Islamic Bank",
                "source_file": filename
            })
    
        return txs
    
    def clean_description(lines):
        return re.sub(r"\s+", " ", " ".join(lines)).strip()
    
    def should_skip_line(line):
        skip = [
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
        return any(re.search(p, line, re.IGNORECASE) for p in skip)
    
