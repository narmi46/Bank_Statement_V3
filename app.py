import streamlit as st
import pdfplumber
import json
import pandas as pd
from io import BytesIO
from datetime import datetime

# ---------------------------------------------------
# BANK PARSERS (EXISTING)
# ---------------------------------------------------
from maybank import parse_transactions_maybank
from public_bank import parse_transactions_pbb
from rhb import parse_transactions_rhb
from cimb import parse_transactions_cimb
from bank_islam import parse_bank_islam
from bank_rakyat import parse_bank_rakyat
from hong_leong import parse_hong_leong
from ambank import parse_ambank
from bank_muamalat import parse_transactions_bank_muamalat
from affin_bank import parse_affin_bank
from agro_bank import parse_agro_bank

# ---------------------------------------------------
# FRAUD ENGINE
# ---------------------------------------------------
from fraud import run_fraud_detection


# ---------------------------------------------------
# STREAMLIT SETUP
# ---------------------------------------------------
st.set_page_config(page_title="Bank Statement Parser", layout="wide")
st.title("📄 Bank Statement Parser (Multi-File Support)")


# ---------------------------------------------------
# SESSION STATE
# ---------------------------------------------------
if "status" not in st.session_state:
    st.session_state.status = "idle"

if "results" not in st.session_state:
    st.session_state.results = []


# ---------------------------------------------------
# BANK SELECTION
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
# FILE UPLOAD
# ---------------------------------------------------
uploaded_files = st.file_uploader(
    "Upload PDF files",
    type=["pdf"],
    accept_multiple_files=True
)

if uploaded_files:
    uploaded_files = sorted(uploaded_files, key=lambda x: x.name)


# ---------------------------------------------------
# CONTROLS
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

    progress_bar = st.progress(0)
    total_files = len(uploaded_files)

    for idx, uploaded_file in enumerate(uploaded_files):

        if st.session_state.status == "stopped":
            break

        with pdfplumber.open(uploaded_file) as pdf:

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
            elif bank_choice == "Hong Leong":
                tx = parse_hong_leong(pdf, uploaded_file.name)
            elif bank_choice == "Affin Bank":
                tx = parse_affin_bank(pdf, uploaded_file.name)
            else:
                tx = []

        all_tx.extend(tx)
        progress_bar.progress((idx + 1) / total_files)

    st.session_state.results = all_tx


# ---------------------------------------------------
# DISPLAY RESULTS
# ---------------------------------------------------
if st.session_state.results:

    df = pd.DataFrame(st.session_state.results)

    st.subheader("📊 Extracted Transactions")
    st.dataframe(df, use_container_width=True)

    # ---------------------------------------------------
    # FRAUD DETECTION (FINAL)
    # ---------------------------------------------------
    st.markdown("---")
    st.subheader("🕵️ Fraud Detection")

    fraud_result = run_fraud_detection(st.session_state.results)

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### 🔝 Top Credit Parties")
        st.dataframe(fraud_result["top_credit_parties"], use_container_width=True)

    with col2:
        st.markdown("### 🔻 Top Debit Parties")
        st.dataframe(fraud_result["top_debit_parties"], use_container_width=True)

    st.markdown("### 💰 High-Value Credit Transactions")
    if fraud_result["high_value_credits"]:
        st.dataframe(fraud_result["high_value_credits"], use_container_width=True)
    else:
        st.info("No high-value credit transactions detected.")

    st.download_button(
        "⬇️ Download Fraud Signals (JSON)",
        json.dumps(fraud_result, indent=2),
        "fraud_signals.json",
        "application/json"
    )

else:
    if uploaded_files:
        st.warning("⚠️ No transactions found — click Start Processing.")
