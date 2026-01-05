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

# ---------------------------------------------------
# NEW BANK PARSERS (EXISTING)
# ---------------------------------------------------
from ambank import parse_ambank
from bank_muamalat import parse_transactions_bank_muamalat
from affin_bank import parse_affin_bank
from agro_bank import parse_agro_bank


# ===================================================
# FRAUD DETECTION (MAYBANK ONLY)
# ===================================================
def normalize_text(text):
    text = text.upper()
    text = re.sub(r"[^A-Z0-9 ]", " ", text)
    text = re.sub(r"\b(SDN|BHD|BERHAD|LIMITED|LTD)\b", "", text)
    return re.sub(r"\s+", " ", text).strip()

def fraud_check_maybank(transaction, company_name, enabled=True):
    """
    Simple Maybank fraud detection:
    - Flag TRUE if company name appears in transaction description
    """

    transaction["fraud_flag"] = False

    if not enabled or not company_name:
        return transaction

    desc = transaction.get("description", "")
    if not desc:
        return transaction

    desc_norm = normalize_text(desc)
    company_norm = normalize_text(company_name)

    company_tokens = company_norm.split()
    match_count = sum(1 for t in company_tokens if t in desc_norm)

    if match_count >= 2:
        transaction["fraud_flag"] = True

    return transaction


# ===================================================
# STREAMLIT SETUP
# ===================================================
st.set_page_config(page_title="Bank Statement Parser", layout="wide")
st.title("📄 Bank Statement Parser (Multi-File Support)")
st.write("Upload one or more bank statement PDFs to extract transactions.")


# ===================================================
# SESSION STATE
# ===================================================
if "status" not in st.session_state:
    st.session_state.status = "idle"

if "results" not in st.session_state:
    st.session_state.results = []


# ===================================================
# BANK SELECTION
# ===================================================
bank_choice = st.selectbox(
    "Select Bank Format",
    [
        "Maybank",
        "Public Bank (PBB)",
        "RHB Bank",
        "CIMB Bank",
        "Bank Islam",
        "Bank Rakyat",
        "Ambank",
        "Affin Bank",
        "Bank Muamalat",
        "Agro Bank"
    ]
)


# ===================================================
# FRAUD DETECTION CONTROLS (MAYBANK ONLY)
# ===================================================
st.subheader("🚨 Fraud Detection (Maybank Only)")

enable_fraud_check = st.checkbox("Enable Fraud Detection", value=False)

company_name_input = st.text_input(
    "Company Name (used for inter-transaction detection)",
    placeholder="e.g. CLEAR WATER SERVICE SDN BHD"
)


# ===================================================
# FILE UPLOAD
# ===================================================
uploaded_files = st.file_uploader(
    "Upload PDF files",
    type=["pdf"],
    accept_multiple_files=True
)

if uploaded_files:
    uploaded_files = sorted(uploaded_files, key=lambda x: x.name)


# ===================================================
# START / STOP / RESET
# ===================================================
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


# ===================================================
# MAIN PROCESSING
# ===================================================
all_tx = []

if uploaded_files and st.session_state.status == "running":

    progress_bar = st.progress(0)
    total_files = len(uploaded_files)

    for file_idx, uploaded_file in enumerate(uploaded_files):

        if st.session_state.status == "stopped":
            st.warning("⏹️ Processing stopped by user.")
            break

        st.write(f"### 🗂️ Processing File: **{uploaded_file.name}**")

        try:
            with pdfplumber.open(uploaded_file) as pdf:

                tx = []

                if bank_choice == "Maybank":
                    tx = parse_transactions_maybank(pdf, uploaded_file.name)

                elif bank_choice == "Public Bank (PBB)":
                    tx = parse_transactions_pbb(pdf, uploaded_file.name)

                elif bank_choice == "RHB Bank":
                    tx = parse_transactions_rhb(uploaded_file, uploaded_file.name)

                elif bank_choice == "CIMB Bank":
                    tx = parse_transactions_cimb(pdf, uploaded_file.name)

                elif bank_choice == "Ambank":
                    tx = parse_ambank(pdf, uploaded_file.name)

                elif bank_choice == "Bank Islam":
                    tx = parse_bank_islam(pdf, uploaded_file.name)

                elif bank_choice == "Bank Rakyat":
                    tx = parse_bank_rakyat(pdf, uploaded_file.name)

                elif bank_choice == "Bank Muamalat":
                    tx = parse_transactions_bank_muamalat(pdf, uploaded_file.name)

                elif bank_choice == "Agro Bank":
                    tx = parse_agro_bank(pdf, uploaded_file.name)

                elif bank_choice == "Affin Bank":
                    tx = parse_affin_bank(pdf, uploaded_file.name)

                if tx:
                    st.success(f"✅ Extracted {len(tx)} transactions")
                    all_tx.extend(tx)
                else:
                    st.warning("⚠️ No transactions found")

        except Exception as e:
            st.error(f"❌ Error processing {uploaded_file.name}: {e}")

        progress_bar.progress((file_idx + 1) / total_files)

    st.session_state.results = all_tx


# ===================================================
# APPLY FRAUD DETECTION (POST-PROCESSING)
# ===================================================
if (
    bank_choice == "Maybank"
    and enable_fraud_check
    and company_name_input
    and st.session_state.results
):
    updated = []
    for t in st.session_state.results:
        updated.append(
            fraud_check_maybank(
                transaction=t,
                company_name=company_name_input,
                enabled=True
            )
        )
    st.session_state.results = updated


# ===================================================
# DISPLAY RESULTS
# ===================================================
if st.session_state.results:

    st.subheader("📊 Extracted Transactions")

    df = pd.DataFrame(st.session_state.results)

    display_cols = [
        "date", "description", "debit", "credit",
        "balance", "fraud_flag",
        "page", "bank", "source_file"
    ]
    display_cols = [c for c in display_cols if c in df.columns]

    st.dataframe(df[display_cols], use_container_width=True)


# ===================================================
# DOWNLOAD OPTIONS
# ===================================================
if st.session_state.results:

    st.subheader("⬇️ Download Options")

    col1, col2 = st.columns(2)

    with col1:
        st.download_button(
            "📄 Download JSON",
            json.dumps(df[display_cols].to_dict(orient="records"), indent=4),
            "transactions.json",
            "application/json"
        )

    with col2:
        output = BytesIO()
        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            df[display_cols].to_excel(writer, index=False)
        st.download_button(
            "📊 Download Excel",
            output.getvalue(),
            "transactions.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
