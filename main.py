import streamlit as st
import pandas as pd
import pdfplumber
import re
import os
import json
import plotly.express as px
from datetime import datetime

st.set_page_config(page_title="Finance Categorizer", layout="wide")

VENDOR_FILE = "vendor_map.json"
SAVE_DIR = "saved_statements"
os.makedirs(SAVE_DIR, exist_ok=True)


def load_vendor_map():
    if os.path.exists(VENDOR_FILE):
        with open(VENDOR_FILE, "r") as f:
            return json.load(f)
    return {}


def save_vendor_map(mapping):
    with open(VENDOR_FILE, "w") as f:
        json.dump(mapping, f, indent=2)


def classify_transaction_type(details):
    text = details.lower()
    if "rewards" in text or "rebate" in text or "refund" in text:
        return "Credit"
    debit_keywords = ["retail", "debit", "purchase",
                      "bill", "charge", "petro", "service", "withdrawal"]
    if any(k in text for k in debit_keywords):
        return "Debit"
    return "Credit"


def save_uploaded_file(uploaded_file):
    now = pd.Timestamp.now()
    try:
        with pdfplumber.open(uploaded_file) as pdf:
            for page in pdf.pages:
                lines = page.extract_text().split("\n")
                for line in lines:
                    date_match = re.match(
                        r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}", line)
                    if date_match:
                        month_folder = date_match.group(
                            1) + "_" + str(now.year)
                        break
                else:
                    continue
                break
            else:
                month_folder = now.strftime("%b_%Y")
    except:
        month_folder = now.strftime("%b_%Y")

    save_dir = os.path.join(SAVE_DIR, month_folder)
    os.makedirs(save_dir, exist_ok=True)
    file_path = os.path.join(save_dir, uploaded_file.name)
    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return file_path


def parse_pdf_transactions(file):
    data = []
    current_date = None
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            lines = page.extract_text().split("\n")
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                date_match = re.match(
                    r"^((Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2})(.*)", line)
                if date_match:
                    current_date = date_match.group(1).strip()
                    line = date_match.group(3).strip()

                matches = re.findall(r"([\d,]+\.\d{2}) ([\d,]+\.\d{2})", line)
                if matches:
                    parts = re.split(r"[\d,]+\.\d{2} [\d,]+\.\d{2}", line)
                    for i, (amount_str, _) in enumerate(matches):
                        desc = parts[i].strip() if i < len(parts) else ""
                        amount = float(amount_str.replace(",", ""))
                        details = desc
                        trans_type = classify_transaction_type(details)
                        data.append({
                            "Date": pd.to_datetime(current_date + " 2025", errors='coerce'),
                            "Details": details,
                            "Amount": amount,
                            "Debit/Credit": trans_type
                        })
                else:
                    if data:
                        data[-1]["Details"] += " " + line
    return pd.DataFrame(data)


def categorize(df, vendor_map):
    df["Category"] = "Uncategorized"
    for idx, row in df.iterrows():
        details = row["Details"].lower()
        for vendor_substring, cat in vendor_map.items():
            if vendor_substring == "__custom_categories__":
                continue
            if vendor_substring in details:
                df.at[idx, "Category"] = cat
                break
    return df


def auto_apply_category(df, original_df):
    categorized_rows = df[df["Category"] != "Uncategorized"]
    for _, row in categorized_rows.iterrows():
        snippet = row["Details"].lower()[:25]
        category = row["Category"]
        mask = original_df["Details"].str.lower().str.contains(
            re.escape(snippet)) & (original_df["Category"] == "Uncategorized")
        original_df.loc[mask, "Category"] = category
    return original_df


if "custom_categories" not in st.session_state:
    st.session_state.custom_categories = []

st.title("💰 Finance Statement Categorizer")

with st.sidebar:
    st.subheader("📂 Load a previously saved statement")
    saved_files = []
    for root, dirs, files in os.walk(SAVE_DIR):
        for file in files:
            if file.endswith(".pdf"):
                saved_files.append(os.path.join(root, file))

    selected_file = st.selectbox("Choose from saved statements",
                                 ["None"] + saved_files if saved_files else ["No saved files available"])

uploaded_files = st.file_uploader("Upload your bank statements (PDFs)", type=[
                                  "pdf"], accept_multiple_files=True)

dfs = []
if uploaded_files:
    for file in uploaded_files:
        saved_path = save_uploaded_file(file)
        with open(saved_path, "rb") as f:
            parsed = parse_pdf_transactions(f)
            dfs.append(parsed)
    st.success(f"✅ Processed {len(uploaded_files)} uploaded file(s).")
elif selected_file and os.path.exists(selected_file):
    with open(selected_file, "rb") as f:
        parsed = parse_pdf_transactions(f)
        dfs.append(parsed)
    st.success(f"✅ Loaded saved file: {os.path.basename(selected_file)}")

if dfs:
    df = pd.concat(dfs, ignore_index=True)
    df.sort_values(by="Date", inplace=True)

    min_date = df["Date"].min()
    max_date = df["Date"].max()

    st.subheader("📅 Filter by Date Range")
    date_range = st.date_input("Select date range:", value=(
        min_date, max_date), min_value=min_date, max_value=max_date)

    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_date, end_date = date_range
        df = df[(df["Date"] >= pd.to_datetime(start_date))
                & (df["Date"] <= pd.to_datetime(end_date))]
    else:
        st.error("⚠️ Please select both a start and end date.")

    vendor_map = load_vendor_map()
    saved_custom_cats = vendor_map.get("__custom_categories__", [])
    for cat in saved_custom_cats:
        if cat not in st.session_state.custom_categories:
            st.session_state.custom_categories.append(cat)

    df = categorize(df, vendor_map)

    existing_categories = df["Category"].dropna().unique().tolist()
    all_categories = sorted(
        set(existing_categories + st.session_state.custom_categories + ["Uncategorized"]))

    st.subheader("🔍 Filter by Category")
    selected_categories = st.multiselect(
        "Select category(ies) to view:",
        options=["All"] + all_categories,
        default=["All"]
    )

    if "All" not in selected_categories:
        df = df[df["Category"].isin(selected_categories)]

    st.subheader("➕ Add Custom Category")
    with st.form("add_category_form", clear_on_submit=True):
        new_category = st.text_input("New Category")
        submitted = st.form_submit_button("Add Category")
        if submitted:
            new_category_clean = new_category.strip()
            if new_category_clean and new_category_clean not in st.session_state.custom_categories:
                st.session_state.custom_categories.append(new_category_clean)
                st.success(f"✅ Added new category: {new_category_clean}")
            elif new_category_clean in st.session_state.custom_categories:
                st.warning("⚠️ This category already exists.")
            else:
                st.warning("⚠️ Please enter a valid category.")

    if st.session_state.custom_categories:
        with st.expander("🗑️ Manage Custom Categories"):
            to_delete = st.multiselect(
                "Select categories to remove", st.session_state.custom_categories)
            if st.button("Delete Selected Categories"):
                st.session_state.custom_categories = [
                    cat for cat in st.session_state.custom_categories if cat not in to_delete]
                st.success("🗑️ Selected categories removed.")

    existing_categories = df["Category"].dropna().unique().tolist()
    all_categories = sorted(
        set(existing_categories + st.session_state.custom_categories + ["Uncategorized"]))

    tab1, tab2, tab3, tab4 = st.tabs(
        ["📉 Expenses (Debits)", "📈 Summary", "📥 Payments (Credits)", "📆 Monthly Report"])

    with tab1:
        st.subheader("✏️ Edit Debit Categories")
        debits_df = df[df["Debit/Credit"] == "Debit"].copy()
        edited_debits = st.data_editor(
            debits_df[["Date", "Details", "Amount", "Category"]],
            column_config={"Category": st.column_config.SelectboxColumn(
                "Category", options=all_categories)},
            use_container_width=True,
            hide_index=True,
            key="debits_editor"
        )
        df.update(edited_debits)
        st.subheader("📊 Debit Summary")
        debit_summary = edited_debits.groupby(
            "Category")["Amount"].sum().reset_index()
        debit_summary = debit_summary.sort_values("Amount", ascending=False)
        st.dataframe(debit_summary, use_container_width=True)

        if not debit_summary.empty:
            chart_type = st.radio(
                "Choose Chart Type",
                options=["Pie Chart", "Bar Chart"],
                horizontal=True,
                key="debit_chart_type"
            )

            if chart_type == "Pie Chart":
                fig = px.pie(
                    debit_summary,
                    values="Amount",
                    names="Category",
                    title="Debits by Category",
                    hole=0.4
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                chart = px.bar(
                    debit_summary,
                    x="Category",
                    y="Amount",
                    title="Expenses by Category",
                    color="Category"
                )
                st.plotly_chart(chart, use_container_width=True)

    with tab2:
        st.subheader("📊 Expense Summary")
        debit_summary = df[df["Debit/Credit"] ==
                           "Debit"].groupby("Category")["Amount"].sum().reset_index()
        debit_summary = debit_summary.sort_values("Amount", ascending=False)
        st.dataframe(debit_summary, use_container_width=True)
        chart_type = st.radio("Select chart type:", [
                              "Pie Chart", "Bar Chart"], horizontal=True)
        if not debit_summary.empty:
            if chart_type == "Pie Chart":
                fig = px.pie(debit_summary, values="Amount",
                             names="Category", title="Expenses by Category", hole=0.4)
            else:
                fig = px.bar(debit_summary, x="Category", y="Amount",
                             title="Expenses by Category", color="Category")
            st.plotly_chart(fig, use_container_width=True)

    with tab3:
        st.subheader("💳 Credit Transactions (Income / Transfers)")
        credits_df = df[df["Debit/Credit"] == "Credit"].copy()
        edited_credits = st.data_editor(
            credits_df[["Date", "Details", "Amount", "Category"]],
            column_config={"Category": st.column_config.SelectboxColumn(
                "Category", options=all_categories)},
            use_container_width=True,
            hide_index=True,
            key="credits_editor"
        )
        df.update(edited_credits)
        st.subheader("📊 Income/Transfer Summary")
        credit_summary = credits_df.groupby(
            "Category")["Amount"].sum().reset_index()
        credit_summary = credit_summary.sort_values("Amount", ascending=False)
        st.dataframe(credit_summary, use_container_width=True)
        if not credit_summary.empty:
            fig = px.pie(credit_summary, values="Amount",
                         names="Category", title="Credits by Category", hole=0.4)
            st.plotly_chart(fig, use_container_width=True)

    with tab4:
        st.subheader("📅 Monthly Expense Report")
        if df.empty:
            st.info("No transactions to show.")
        else:
            df["Month"] = df["Date"].dt.to_period("M").astype(str)
            available_months = sorted(df["Month"].unique(), reverse=True)
            selected_month = st.selectbox("Select a Month", available_months)
            filtered_df = df[(df["Month"] == selected_month)
                             & (df["Debit/Credit"] == "Debit")]
            monthly_summary = filtered_df.groupby(
                "Category")["Amount"].sum().reset_index()
            st.write(f"### Expenses for {selected_month}")
            st.dataframe(monthly_summary, use_container_width=True)
            if not monthly_summary.empty:
                chart = px.bar(monthly_summary, x="Category", y="Amount",
                               title=f"Expenses by Category - {selected_month}", color="Category")
                st.plotly_chart(chart, use_container_width=True)

    st.subheader("📥 Apply & Learn")
    if st.button("💾 Apply Changes"):
        combined_df = pd.concat([edited_debits, edited_credits])
        df = auto_apply_category(combined_df, df)
        for _, row in combined_df.iterrows():
            details = row["Details"].lower()
            new_category = row["Category"]
            if new_category == "Uncategorized":
                continue
            matched = False
            for vendor_substring in list(vendor_map.keys()):
                if vendor_substring == "__custom_categories__":
                    continue
                if vendor_substring in details:
                    vendor_map[vendor_substring] = new_category
                    matched = True
                    break
            if not matched:
                vendor_map[details] = new_category
        vendor_map["__custom_categories__"] = st.session_state.custom_categories
        save_vendor_map(vendor_map)
        st.success(
            "✅ Categories saved. Vendor map updated for future auto-categorization!")
