import streamlit as st
import pdfplumber
import json
import pandas as pd
from datetime import datetime
from io import BytesIO
from collections import defaultdict
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



# ==================================================
# Fraud Detection Configuration
# ==================================================
TOP_N = 5
HIGH_VALUE_THRESHOLD = 100_000
THRESHOLD_MODE = "gte"   # "gte" or "lte"


# ==================================================
# Party Normalization
# ==================================================
def normalize_party(description: str) -> str:
    if not description:
        return "UNKNOWN"

    desc = description.upper()

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

    desc = re.sub(r"\s+", " ", desc).strip()

    # Numeric-only descriptions → bank clearing
    if re.fullmatch(r"[0-9 ]+", desc):
        return f"BANK_CLEARING_{desc}"

    # Trim long technical tails
    desc = re.split(r"\d{6,}", desc)[0].strip()

    return desc[:80] if desc else "UNKNOWN"


# ==================================================
# Fraud Detection Engine
# ==================================================
def run_fraud_detection(transactions):
    credit_by_party = defaultdict(float)
    debit_by_party = defaultdict(float)
    high_value_credits = []

    for tx in transactions:
        party = normalize_party(tx.get("description", ""))

        credit = float(tx.get("credit", 0) or 0)
        debit = float(tx.get("debit", 0) or 0)

        if credit > 0:
            credit_by_party[party] += credit

            if (
                (THRESHOLD_MODE == "gte" and credit >= HIGH_VALUE_THRESHOLD)
                or (THRESHOLD_MODE == "lte" and credit <= HIGH_VALUE_THRESHOLD)
            ):
                high_value_credits.append({
                    "date": tx.get("date"),
                    "party": party,
                    "credit": credit,
                    "description": tx.get("description")
                })

        if debit > 0:
            debit_by_party[party] += debit

    top_credit = sorted(
        credit_by_party.items(), key=lambda x: x[1], reverse=True
    )[:TOP_N]

    top_debit = sorted(
        debit_by_party.items(), key=lambda x: x[1], reverse=True
    )[:TOP_N]

    return {
        "top_credit_parties": [
            {"party": p, "total_credit": round(v, 2)}
            for p, v in top_credit
        ],
        "top_debit_parties": [
            {"party": p, "total_debit": round(v, 2)}
            for p, v in top_debit
        ],
        "high_value_credits": high_value_credits,
        "config": {
            "top_n": TOP_N,
            "threshold": HIGH_VALUE_THRESHOLD,
            "threshold_mode": f"Credit {'≥' if THRESHOLD_MODE == 'gte' else '≤'} threshold"
        }
    }


# ==================================================
# Streamlit App
# ==================================================
st.set_page_config(page_title="Bank Statement Analyzer", layout="wide")
st.title("📊 Bank Statement Analyzer + Fraud Detection")

uploaded_file = st.file_uploader("Upload extracted JSON", type=["json"])

if uploaded_file:
    data = json.load(uploaded_file)
    transactions = data.get("transactions", [])

    st.success(f"Loaded {len(transactions)} transactions")

    # -----------------------------
    # Fraud Detection Section
    # -----------------------------
    st.subheader("🚨 Fraud Detection (Rule-based)")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### 🔝 Top Credit Parties")
        fraud_result = run_fraud_detection(transactions)
        st.table(fraud_result["top_credit_parties"])

    with col2:
        st.markdown("### 🔻 Top Debit Parties")
        st.table(fraud_result["top_debit_parties"])

    st.markdown("### 💰 High Value Credit Transactions")
    if fraud_result["high_value_credits"]:
        st.table(fraud_result["high_value_credits"])
    else:
        st.info("No high-value credit transactions detected.")

    # -----------------------------
    # Export
    # -----------------------------
    st.download_button(
        "⬇️ Download Fraud Signals (JSON)",
        json.dumps(fraud_result, indent=2),
        file_name="fraud_signals.json",
        mime="application/json"
    )
