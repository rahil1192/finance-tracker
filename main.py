import streamlit as st
import pandas as pd
import pdfplumber
import re
import os
import json
import plotly.express as px

st.set_page_config(page_title="Finance Categorizer", layout="wide")

VENDOR_FILE = "vendor_map.json"

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
    debit_keywords = ["retail", "debit", "purchase", "bill", "charge", "petro", "service", "withdrawal"]
    if any(k in text for k in debit_keywords):
        return "Debit"
    return "Credit"

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
                date_match = re.match(r"^((Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2})(.*)", line)
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
        mask = original_df["Details"].str.lower().str.contains(re.escape(snippet)) & (original_df["Category"] == "Uncategorized")
        original_df.loc[mask, "Category"] = category
    return original_df

# ➕ Added: Save PDF to month folder
def save_pdf_locally(file, df):
    if df.empty:
        return

    first_date = df["Date"].min()
    if pd.isna(first_date):
        return

    folder_name = f"statements/{first_date.strftime('%Y-%m')}"
    os.makedirs(folder_name, exist_ok=True)

    file_path = os.path.join(folder_name, file.name)
    with open(file_path, "wb") as f:
        f.write(file.getbuffer())

# ➕ Added: List and delete saved PDFs
def list_saved_pdfs():
    base_path = "statements"
    saved_files = {}
    if not os.path.exists(base_path):
        return saved_files

    for folder in sorted(os.listdir(base_path)):
        folder_path = os.path.join(base_path, folder)
        if os.path.isdir(folder_path):
            files = [f for f in os.listdir(folder_path) if f.endswith(".pdf")]
            saved_files[folder] = files
    return saved_files

def delete_pdf(month_folder, filename):
    file_path = os.path.join("statements", month_folder, filename)
    if os.path.exists(file_path):
        os.remove(file_path)
        return True
    return False

# Session state init
if "custom_categories" not in st.session_state:
    st.session_state.custom_categories = []

st.title("💰 Finance Statement Categorizer")
uploaded_files = st.file_uploader("Upload your bank statements (PDFs)", type=["pdf"], accept_multiple_files=True)

if uploaded_files:
    dfs = []
    for file in uploaded_files:
        parsed = parse_pdf_transactions(file)
        if not parsed.empty:
            save_pdf_locally(file, parsed)
            dfs.append(parsed)
    df = pd.concat(dfs, ignore_index=True)
    df.sort_values(by="Date", inplace=True)
    st.success(f"✅ Processed {len(uploaded_files)} PDF file(s).")

    # ➕ Added: Show and manage saved PDFs
    with st.expander("🗂️ View & Manage Saved PDFs"):
        saved_pdfs = list_saved_pdfs()

        if not saved_pdfs:
            st.info("No saved PDFs found.")
        else:
            for month, files in saved_pdfs.items():
                st.markdown(f"#### 📅 {month}")
                for filename in files:
                    col1, col2 = st.columns([6, 1])
                    col1.write(filename)
                    delete_button = col2.button("❌ Delete", key=f"del_{month}_{filename}")
                    if delete_button:
                        if delete_pdf(month, filename):
                            st.success(f"Deleted `{filename}` from `{month}`.")
                            st.experimental_rerun()

    min_date = df["Date"].min()
    max_date = df["Date"].max()

    st.subheader("📅 Filter by Date Range")
    date_range = st.date_input(
        "Select date range:",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date
    )

    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_date, end_date = date_range
        df = df[(df["Date"] >= pd.to_datetime(start_date)) & (df["Date"] <= pd.to_datetime(end_date))]
    else:
        st.error("⚠️ Please select both a start and end date.")

    vendor_map = load_vendor_map()

    saved_custom_cats = vendor_map.get("__custom_categories__", [])
    for cat in saved_custom_cats:
        if cat not in st.session_state.custom_categories:
            st.session_state.custom_categories.append(cat)

    df = categorize(df, vendor_map)

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
            to_delete = st.multiselect("Select categories to remove", st.session_state.custom_categories)
            if st.button("Delete Selected Categories"):
                st.session_state.custom_categories = [cat for cat in st.session_state.custom_categories if cat not in to_delete]
                st.success("🗑️ Selected categories removed.")

    existing_categories = df["Category"].dropna().unique().tolist()
    all_categories = sorted(set(existing_categories + st.session_state.custom_categories + ["Uncategorized"]))

    tab1, tab2, tab3, tab4 = st.tabs(["📉 Expenses (Debits)", "📈 Summary", "📥 Payments (Credits)", "📆 Monthly Report"])

    with tab1:
        st.subheader("✏️ Edit Debit Categories")
        debits_df = df[df["Debit/Credit"] == "Debit"].copy()
        edited_debits = st.data_editor(
            debits_df[["Date", "Details", "Amount", "Category"]],
            column_config={"Category": st.column_config.SelectboxColumn("Category", options=all_categories)},
            use_container_width=True,
            hide_index=True,
            key="debits_editor"
        )
        df.update(edited_debits)
        st.subheader("📊 Debit Summary")
        debit_summary = edited_debits.groupby("Category")["Amount"].sum().reset_index()
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
        summary = df[df["Debit/Credit"] == "Debit"].groupby("Category")["Amount"].sum().reset_index()
        summary = summary.sort_values("Amount", ascending=False)
        st.dataframe(summary, use_container_width=True)
        if not summary.empty:
            fig = px.pie(summary, values="Amount", names="Category", title="Expenses by Category", hole=0.4)
            st.plotly_chart(fig, use_container_width=True)

    with tab3:
        st.subheader("💳 Credit Transactions (Income / Transfers)")
        credits_df = df[df["Debit/Credit"] == "Credit"].copy()
        edited_credits = st.data_editor(
            credits_df[["Date", "Details", "Amount", "Category"]],
            column_config={"Category": st.column_config.SelectboxColumn("Category", options=all_categories)},
            use_container_width=True,
            hide_index=True,
            key="credits_editor"
        )
        df.update(edited_credits)

        st.subheader("📊 Income/Transfer Summary")
        credit_summary = credits_df.groupby("Category")["Amount"].sum().reset_index()
        credit_summary = credit_summary.sort_values("Amount", ascending=False)
        st.dataframe(credit_summary, use_container_width=True)
        if not credit_summary.empty:
            fig = px.pie(credit_summary, values="Amount", names="Category", title="Credits by Category", hole=0.4)
            st.plotly_chart(fig, use_container_width=True)

    with tab4:
        st.subheader("📅 Monthly Expense Report")
        if df.empty:
            st.info("No transactions to show.")
        else:
            df["Month"] = df["Date"].dt.to_period("M").astype(str)
            available_months = sorted(df["Month"].unique(), reverse=True)
            selected_month = st.selectbox("Select a Month", available_months)

            filtered_df = df[(df["Month"] == selected_month) & (df["Debit/Credit"] == "Debit")]
            monthly_summary = filtered_df.groupby("Category")["Amount"].sum().reset_index()

            st.write(f"### Expenses for {selected_month}")
            st.dataframe(monthly_summary, use_container_width=True)

            if not monthly_summary.empty:
                chart = px.bar(
                    monthly_summary,
                    x="Category",
                    y="Amount",
                    title=f"Expenses by Category - {selected_month}",
                    color="Category"
                )
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

        st.success("✅ Categories saved. Vendor map updated for future auto-categorization!")
