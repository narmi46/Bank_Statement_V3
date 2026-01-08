import streamlit as st
import pdfplumber
import json
import pandas as pd
from datetime import datetime
from io import BytesIO
import re

# ---------------------------------------------------
# Import standalone parsers (EXISTING)
# ---------------------------------------------------
from maybank import parse_transactions_maybank
from public_bank import parse_transactions_pbb
from rhb import parse_transactions_rhb
from cimb import parse_transactions_cimb
from bank_islam import parse_bank_islam
from bank_rakyat import parse_bank_rakyat
from hong_leong import parse_hong_leong


# ---------------------------------------------------
# NEW BANK PARSERS (ADDED ONLY)
# ---------------------------------------------------

from ambank import parse_ambank
from bank_muamalat import parse_transactions_bank_muamalat
from affin_bank import parse_affin_bank
from agro_bank import parse_agro_bank

# ---------------------------------------------------
# Streamlit Setup
# ---------------------------------------------------
st.set_page_config(page_title="Bank Statement Parser", layout="wide")
st.title("📄 Bank Statement Parser (Multi-File Support)")
st.write("Upload one or more bank statement PDFs to extract transactions.")


# ---------------------------------------------------
# Session State
# ---------------------------------------------------
if "status" not in st.session_state:
    st.session_state.status = "idle"    # idle, running, stopped

if "results" not in st.session_state:
    st.session_state.results = []


# ---------------------------------------------------
# Bank Selection
# ---------------------------------------------------
bank_choice = st.selectbox(
    "Select Bank Format",
    [
            "Affin Bank",
            "Agro Bank",
            "Ambank",
            "Bank Islam",
            "Bank Muamalat",
            "Bank Rakyat",
            "CIMB Bank",
            "Hong Leong",
            "Maybank",
            "Public Bank (PBB)",
            "RHB Bank"
    ]
)


# ---------------------------------------------------
# File Upload
# ---------------------------------------------------
uploaded_files = st.file_uploader(
    "Upload PDF files",
    type=["pdf"],
    accept_multiple_files=True
)

# Sort uploaded files by name
if uploaded_files:
    uploaded_files = sorted(uploaded_files, key=lambda x: x.name)


# ---------------------------------------------------
# Start / Stop / Reset Controls
# ---------------------------------------------------
col1, col2, col3 = st.columns(3)

with col1:
    if st.button("▶️ Start Processing"):
        st.session_state.status = "running"

with col2:
    if st.button("⏹️ Stop"):
        st.session_state.status = "stopped"

with col3:
    if st.button("🔄 Reset"):
        st.session_state.status = "idle"
        st.session_state.results = []
        st.rerun()

st.write(f"### ⚙️ Status: **{st.session_state.status.upper()}**")


# ---------------------------------------------------
# MAIN PROCESSING
# ---------------------------------------------------
all_tx = []

if uploaded_files and st.session_state.status == "running":

    bank_display_box = st.empty()
    progress_bar = st.progress(0)

    total_files = len(uploaded_files)

    for file_idx, uploaded_file in enumerate(uploaded_files):

        if st.session_state.status == "stopped":
            st.warning("⏹️ Processing stopped by user.")
            break

        st.write(f"### 🗂️ Processing File: **{uploaded_file.name}**")
        bank_display_box.info(f"📄 Processing {bank_choice}: {uploaded_file.name}...")

        try:
            with pdfplumber.open(uploaded_file) as pdf:

                tx = []

                if bank_choice == "Maybank":
                    tx = parse_transactions_maybank(pdf, uploaded_file.name)

                elif bank_choice == "Public Bank (PBB)":
                    tx = parse_transactions_pbb(pdf, uploaded_file.name)
                    
                elif bank_choice == "RHB Bank":
                    tx = parse_transactions_rhb(uploaded_file, uploaded_file.name)

                #elif bank_choice == "RHB Bank":
                #   tx = parse_transactions_rhb(pdf, uploaded_file.name)

                elif bank_choice == "CIMB Bank":
                    tx = parse_transactions_cimb(pdf, uploaded_file.name)
                                
                elif bank_choice == "Ambank":
                    tx = parse_ambank(pdf, uploaded_file.name)

                elif bank_choice == "Bank Islam":
                    tx = parse_bank_islam(pdf, uploaded_file.name)

                elif bank_choice == "Bank Rakyat":
                    tx = parse_bank_rakyat(pdf, uploaded_file.name)

                # ---------------------------------------------------
                # NEW BANKS (ADDED ONLY)
                # ---------------------------------------------------

                elif bank_choice == "Bank Muamalat":
                    tx = parse_transactions_bank_muamalat(pdf, uploaded_file.name)

                elif bank_choice == "Agro Bank":
                    tx = parse_agro_bank(pdf, uploaded_file.name)

                elif bank_choice == "Hong Leong":
                    tx = parse_hong_leong(pdf, uploaded_file.name)
                
                elif bank_choice == "Affin Bank":
                    tx = parse_affin_bank(pdf, uploaded_file.name)

                if tx:
                    st.success(f"✅ Extracted {len(tx)} transactions from {uploaded_file.name}")
                    all_tx.extend(tx)
                else:
                    st.warning(f"⚠️ No transactions found in {uploaded_file.name}")

        except Exception as e:
            st.error(f"❌ Error processing {uploaded_file.name}: {e}")

        progress = (file_idx + 1) / total_files
        progress_bar.progress(progress)

    bank_display_box.success(f"🏦 Completed processing: **{bank_choice}**")
    st.session_state.results = all_tx


# ---------------------------------------------------
# CALCULATE MONTHLY SUMMARY
# ---------------------------------------------------
def calculate_monthly_summary(transactions):
    if not transactions:
        return []

    df = pd.DataFrame(transactions)

    df['date_parsed'] = pd.to_datetime(df['date'], errors='coerce')
    df = df.dropna(subset=['date_parsed'])

    if df.empty:
        st.warning("⚠️ No valid transaction dates found.")
        return []

    df['month_period'] = df['date_parsed'].dt.strftime('%Y-%m')

    df['debit'] = pd.to_numeric(df['debit'], errors='coerce').fillna(0)
    df['credit'] = pd.to_numeric(df['credit'], errors='coerce').fillna(0)
    df['balance'] = pd.to_numeric(df['balance'], errors='coerce')

    monthly_summary = []

    for period, group in df.groupby('month_period', sort=True):

        ending_balance = None
        if not group['balance'].isna().all():
            group_sorted = group.sort_values('date_parsed')
            balances = group_sorted['balance'].dropna()
            if not balances.empty:
                ending_balance = round(balances.iloc[-1], 2)

        monthly_summary.append({
            'month': period,
            'transaction_count': len(group),
            'total_debit': round(group['debit'].sum(), 2),
            'total_credit': round(group['credit'].sum(), 2),
            'net_change': round(group['credit'].sum() - group['debit'].sum(), 2),
            'ending_balance': ending_balance,
            'lowest_balance': round(group['balance'].min(), 2) if not group['balance'].isna().all() else None,
            'highest_balance': round(group['balance'].max(), 2) if not group['balance'].isna().all() else None,
            'source_files': ', '.join(sorted(group['source_file'].unique())) if 'source_file' in group.columns else ''
        })

    return sorted(monthly_summary, key=lambda x: x['month'])



# ---------------------------------------------------
# SIMPLE FRAUD / COUNTERPARTY HEURISTICS (BETA)
# ---------------------------------------------------
def _normalize_text(s):
    try:
        return re.sub(r"\s+", " ", str(s or "")).strip().upper()
    except Exception:
        return ""

def parse_party_rules(rules_json_text):
    """
    Expected JSON shape (example):
    {
      "PARTY_A": ["KEYWORD1", "KEYWORD2"],
      "PARTY_B": ["ACME SDN BHD", "ACME"]
    }
    Returns dict[str, list[str]] with normalized patterns.
    """
    if not rules_json_text or not str(rules_json_text).strip():
        return {}

    try:
        data = json.loads(rules_json_text)
        if not isinstance(data, dict):
            return {}
        out = {}
        for party, patterns in data.items():
            if not party:
                continue
            if isinstance(patterns, str):
                patterns = [patterns]
            if not isinstance(patterns, list):
                continue
            norm_patterns = []
            for p in patterns:
                p2 = _normalize_text(p)
                if p2:
                    norm_patterns.append(p2)
            if norm_patterns:
                out[_normalize_text(party)] = norm_patterns
        return out
    except Exception:
        return {}

def extract_party_from_description(description, party_rules=None):
    """
    Party inference with two layers:
    1) Optional JSON rules: first party whose pattern is a substring of normalized description wins.
    2) Fallback heuristics for bank statement descriptions:
       - Prefer names after common prefixes (TRANSFER TO/FR A/C, INTER-BANK PAYMENT INTO A/C, etc.)
       - Strip obvious noise (trailing refs, '=', '*', digits-heavy tails)
       - Normalize so '...BIN*' and '...BIN' collapse into one party label.
    """
    desc_raw = description or ""
    desc = _normalize_text(desc_raw)

    # Always drop noisy right-hand side after '=' (often translations / extra blobs)
    if "=" in desc:
        desc = desc.split("=", 1)[0].strip()

    # Apply JSON mapping rules (substring match) on normalized text
    if party_rules:
        for party, patterns in party_rules.items():
            for p in patterns:
                p2 = _normalize_text(p)
                if p2 and p2 in desc:
                    return party

    if not desc:
        return "UNKNOWN"

    # Try extract "counterparty" after common prefixes
    prefix_patterns = [
        r"^TRANSFER\s+TO\s+A/C\s+(.+)$",
        r"^TRANSFER\s+FR\s+A/C\s+(.+)$",
        r"^INTER-BANK\s+PAYMENT\s+INTO\s+A/C\s+(.+)$",
        r"^ESI\s+PAYMENT\s+DEBIT\s+(.+)$",
        r"^PAYMENT\s+DEBIT\s*-\s*(.+)$",
        r"^CMS\s*-\s*CR\s+PYMT\s+(.+)$",
        r"^ELECTRONIC\s+REMITTANCE\s*-\s*GIR\s+(.+)$",
    ]
    for pat in prefix_patterns:
        mm = re.search(pat, desc, flags=re.IGNORECASE)
        if mm:
            desc = mm.group(1).strip()
            break

    # If it's the common MARS streams, normalize to stable buckets
    if "MARS CIT COLLECTION" in desc:
        return "MARS CIT COLLECTION"
    if "MARS GPAY" in desc or "GPAY NETWORK" in desc:
        return "MARS GPAY NETWORK"

    # Cut trailing noise after '*' (often reference / note)
    if "*" in desc:
        desc = desc.split("*", 1)[0].strip()

    # Cut common trailing tokens if they appear later in the string
    cut_tokens = [" REF", " REFERENCE", " TRF", " TRANSFER", " DUITNOW", " FPX", " ATM", " POS", " CDM", " CASH", " ONLINE"]
    for t in cut_tokens:
        idx = desc.find(t)
        if idx > 8:
            desc = desc[:idx].strip()
            break

    # Keep letters/numbers/& and normalize whitespace
    desc = re.sub(r"[^A-Z0-9 &]", " ", desc)
    desc = re.sub(r"\s+", " ", desc).strip()

    # Keep first 8 words (a bit wider than 5 to capture 'SDN BHD' fully)
    words = desc.split()
    return " ".join(words[:8]) if words else "UNKNOWN"

def top_parties_by_amount(df, top_n=5):
    if df.empty or "description" not in df.columns:
        return pd.DataFrame(), pd.DataFrame()

    tmp = df.copy()

    tmp["debit_num"] = pd.to_numeric(tmp.get("debit", 0), errors="coerce").fillna(0.0)
    tmp["credit_num"] = pd.to_numeric(tmp.get("credit", 0), errors="coerce").fillna(0.0)

    # default: no rules
    party_rules = {}

    # party already computed upstream if exists
    if "party" not in tmp.columns:
        tmp["party"] = tmp["description"].apply(lambda x: extract_party_from_description(x, party_rules))

    credit_top = (
        tmp.groupby("party", dropna=False)["credit_num"]
           .sum()
           .sort_values(ascending=False)
           .head(int(top_n))
           .reset_index()
           .rename(columns={"credit_num": "total_credit"})
    )

    debit_top = (
        tmp.groupby("party", dropna=False)["debit_num"]
           .sum()
           .sort_values(ascending=False)
           .head(int(top_n))
           .reset_index()
           .rename(columns={"debit_num": "total_debit"})
    )

    return credit_top, debit_top


# ---------------------------------------------------
# DISPLAY RESULTS
# ---------------------------------------------------
if st.session_state.results:

    st.subheader("📊 Extracted Transactions")

    df = pd.DataFrame(st.session_state.results)

    display_cols = [
        "date", "description", "debit", "credit",
        "balance", "page", "bank", "source_file"
    ]
    display_cols = [c for c in display_cols if c in df.columns]

    df_display = df[display_cols]
    st.dataframe(df_display, use_container_width=True)

    monthly_summary = calculate_monthly_summary(st.session_state.results)

    if monthly_summary:
        st.subheader("📅 Monthly Summary")
        summary_df = pd.DataFrame(monthly_summary)
        st.dataframe(summary_df, use_container_width=True)

        st.markdown("---")
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("Total Transactions", summary_df['transaction_count'].sum())
        with col2:
            st.metric("Total Debits", f"RM {summary_df['total_debit'].sum():,.2f}")
        with col3:
            st.metric("Total Credits", f"RM {summary_df['total_credit'].sum():,.2f}")
        with col4:
            net_total = summary_df['net_change'].sum()
            st.metric("Net Change", f"RM {net_total:,.2f}")


    # ---------------------------------------------------
    # FRAUD DETECTION (START SMALL) - TOP COUNTERPARTIES + HIGH VALUE CREDITS
    # ---------------------------------------------------
    st.markdown("---")
    with st.expander("🕵️ Fraud detection (beta): Top 5 parties + high-value credits", expanded=False):

        st.caption("Start small: group by 'party' inferred from transaction description. You can optionally provide matching rules as JSON.")

        default_rules_example = {
            "ACME SDN BHD": ["ACME", "ACME SDN", "ACME SDN BHD"],
            "XYZ TRADING": ["XYZ TRADING", "XYZ TRDG"]
        }

        rules_text = st.text_area(
            "Party matching rules (JSON, optional)",
            value=json.dumps(default_rules_example, indent=2),
            height=160
        )

        top_n = st.number_input("Top N parties", min_value=1, max_value=50, value=5, step=1)

        threshold = st.number_input("High-value credit threshold (RM)", min_value=0.0, value=100000.0, step=1000.0, format="%.2f")
        threshold_mode = st.selectbox("High-value rule", ["Credit ≥ threshold", "Credit ≤ threshold"], index=0)

        party_rules = parse_party_rules(rules_text)

        df_fd = df.copy()
        df_fd["debit_num"] = pd.to_numeric(df_fd.get("debit", 0), errors="coerce").fillna(0.0)
        df_fd["credit_num"] = pd.to_numeric(df_fd.get("credit", 0), errors="coerce").fillna(0.0)
        df_fd["party"] = df_fd["description"].apply(lambda x: extract_party_from_description(x, party_rules))

        credit_top = (
            df_fd.groupby("party", dropna=False)["credit_num"]
                .sum()
                .sort_values(ascending=False)
                .head(int(top_n))
                .reset_index()
                .rename(columns={"credit_num": "total_credit"})
        )

        debit_top = (
            df_fd.groupby("party", dropna=False)["debit_num"]
                .sum()
                .sort_values(ascending=False)
                .head(int(top_n))
                .reset_index()
                .rename(columns={"debit_num": "total_debit"})
        )

        col_a, col_b = st.columns(2)
        with col_a:
            st.subheader("Top parties by total CREDIT")
            st.dataframe(credit_top, use_container_width=True)
        with col_b:
            st.subheader("Top parties by total DEBIT")
            st.dataframe(debit_top, use_container_width=True)

        if threshold_mode == "Credit ≥ threshold":
            high_value = df_fd[(df_fd["credit_num"] > 0) & (df_fd["credit_num"] >= float(threshold))].copy()
        else:
            high_value = df_fd[(df_fd["credit_num"] > 0) & (df_fd["credit_num"] <= float(threshold))].copy()

        high_value = high_value.sort_values("credit_num", ascending=False)

        st.subheader("High-value CREDIT transactions")
        st.dataframe(
            high_value[["date", "description", "party", "credit_num", "debit_num", "balance", "bank", "source_file"]]
                if not high_value.empty else pd.DataFrame(columns=["date","description","party","credit_num"]),
            use_container_width=True
        )

        st.download_button(
            "⬇️ Download fraud signals (JSON)",
            json.dumps({
                "top_credit_parties": credit_top.to_dict(orient="records"),
                "top_debit_parties": debit_top.to_dict(orient="records"),
                "high_value_credits": high_value.to_dict(orient="records"),
                "config": {"top_n": int(top_n), "threshold": float(threshold), "threshold_mode": threshold_mode}
            }, indent=2, default=str),
            "fraud_signals.json",
            "application/json"
        )


    # ---------------------------------------------------
    # DOWNLOAD OPTIONS
    # ---------------------------------------------------
    st.subheader("⬇️ Download Options")
    col1, col2, col3 = st.columns(3)

    with col1:
        st.download_button(
            "📄 Download Transactions (JSON)",
            json.dumps(df_display.to_dict(orient="records"), indent=4),
            "transactions.json",
            "application/json"
        )

    with col2:
        full_report = {
            "summary": {
                "total_transactions": len(df),
                "date_range": f"{df['date'].min()} to {df['date'].max()}",
                "total_files_processed": df['source_file'].nunique()
            },
            "monthly_summary": monthly_summary,
            "transactions": df_display.to_dict(orient="records")
        }
        st.download_button(
            "📊 Download Full Report (JSON)",
            json.dumps(full_report, indent=4),
            "full_report.json",
            "application/json"
        )

    with col3:
        output = BytesIO()
        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            df_display.to_excel(writer, sheet_name="Transactions", index=False)
            if monthly_summary:
                pd.DataFrame(monthly_summary).to_excel(
                    writer, sheet_name="Monthly Summary", index=False
                )

        st.download_button(
            "📊 Download Full Report (XLSX)",
            output.getvalue(),
            "full_report.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

else:
    if uploaded_files:
        st.warning("⚠️ No transactions found — click **Start Processing**.")
