import streamlit as st
import pdfplumber
import pandas as pd
from io import BytesIO
import json

# -------------------------
# IMPORT MODULES
# -------------------------
from maybank import parse_transactions_maybank
from maybank_security import apply_maybank_security

# -------------------------
# STREAMLIT SETUP
# -------------------------
st.set_page_config(page_title="Maybank Parser + Security", layout="wide")
st.title("📄 Maybank Statement Parser with Security Check")

# -------------------------
# USER INPUTS
# -------------------------
enable_security = st.checkbox("Enable Inter-Transaction Detection", value=False)

company_name = st.text_input(
    "Company Name",
    placeholder="e.g. CLEAR WATER SERVICE SDN BHD"
)

uploaded_files = st.file_uploader(
    "Upload Maybank PDF(s)",
    type=["pdf"],
    accept_multiple_files=True
)

if uploaded_files:
    uploaded_files = sorted(uploaded_files, key=lambda x: x.name)

# -------------------------
# PROCESS
# -------------------------
if uploaded_files and st.button("▶️ Start Processing"):

    all_tx = []

    for uploaded_file in uploaded_files:
        with pdfplumber.open(uploaded_file) as pdf:
            tx = parse_transactions_maybank(pdf, uploaded_file.name)
            all_tx.extend(tx)

    # -------------------------
    # APPLY SECURITY (POST)
    # -------------------------
    all_tx = apply_maybank_security(
        transactions=all_tx,
        company_name=company_name,
        enabled=enable_security
    )

    # -------------------------
    # DISPLAY
    # -------------------------
    df = pd.DataFrame(all_tx)

    display_cols = [
        "date", "description",
        "debit", "credit",
        "balance", "fraud_flag",
        "page", "source_file"
    ]
    display_cols = [c for c in display_cols if c in df.columns]

    st.subheader("📊 Transactions")
    st.dataframe(df[display_cols], use_container_width=True)

    # -------------------------
    # DOWNLOADS
    # -------------------------
    st.subheader("⬇️ Download")

    col1, col2 = st.columns(2)

    with col1:
        st.download_button(
            "Download JSON",
            json.dumps(df[display_cols].to_dict(orient="records"), indent=2),
            "transactions.json",
            "application/json"
        )

    with col2:
        output = BytesIO()
        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            df[display_cols].to_excel(writer, index=False)
        st.download_button(
            "Download Excel",
            output.getvalue(),
            "transactions.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
