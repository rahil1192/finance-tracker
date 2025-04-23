import streamlit as st
import pandas as pd
import os
from datetime import datetime
import re

from finance_categorizer.utils.file_utils import (
    ensure_directories,
    load_vendor_map,
    save_vendor_map,
    save_uploaded_file
)
from finance_categorizer.models.transaction_processor import (
    parse_pdf_transactions,
    categorize,
    auto_apply_category
)
from finance_categorizer.ui.components import (
    display_summary_metrics,
    plot_financial_overview,
    plot_category_summary,
    display_monthly_report
)

# Initialize session state
if "custom_categories" not in st.session_state:
    st.session_state.custom_categories = []

# Set page config
st.set_page_config(page_title="Finance Categorizer", layout="wide")

# Ensure directories exist
ensure_directories()

# Main title
st.title("💰 Finance Statement Categorizer")

# Sidebar for file operations
st.sidebar.subheader("📂 Load a previously saved statement")

# Get saved files
saved_files = []
month_map = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12
}
file_month_map = {}

# Gather files and extract month from folder name
for root, dirs, files in os.walk("saved_statements"):
    for file in files:
        if file.endswith(".pdf"):
            path = os.path.join(root, file)
            saved_files.append(path)
            folder = os.path.basename(os.path.dirname(path)).lower()
            match = re.match(r"([a-z]{3})", folder)
            if match:
                month_str = match.group(1)
                if month_str in month_map:
                    file_month_map[path] = month_map[month_str]

# Find closest file by month
current_month_idx = datetime.now().month


def month_distance(target, current):
    return min((target - current) % 12, (current - target) % 12)


closest_file = None
if file_month_map:
    closest_file = min(file_month_map, key=lambda f: month_distance(
        file_month_map[f], current_month_idx))

# File selection
selected_files = st.sidebar.multiselect(
    "Choose saved statements to load",
    options=saved_files,
    default=[closest_file] if closest_file else []
)

# File upload
uploaded_files = st.sidebar.file_uploader(
    "Upload your bank statements (PDFs)",
    type=["pdf"],
    accept_multiple_files=True
)

# Process files
dfs = []
loaded_months = []  # Track which months are loaded

if uploaded_files:
    for file in uploaded_files:
        saved_path = save_uploaded_file(file)
        with open(saved_path, "rb") as f:
            parsed = parse_pdf_transactions(f)
            dfs.append(parsed)
            # Extract month from the saved path
            folder = os.path.basename(os.path.dirname(saved_path))
            month_match = re.match(r"([A-Za-z]{3})_(\d{4})", folder)
            if month_match:
                month_str, year = month_match.groups()
                month_name = month_str.capitalize()
                loaded_months.append(f"{month_name} {year}")
    st.success(f"✅ Processed {len(uploaded_files)} uploaded file(s).")
elif selected_files:
    for selected_file in selected_files:
        if os.path.exists(selected_file):
            with open(selected_file, "rb") as f:
                parsed = parse_pdf_transactions(f)
                dfs.append(parsed)
                # Extract month from the selected file path
                folder = os.path.basename(os.path.dirname(selected_file))
                month_match = re.match(r"([A-Za-z]{3})_(\d{4})", folder)
                if month_match:
                    month_str, year = month_match.groups()
                    month_name = month_str.capitalize()
                    loaded_months.append(f"{month_name} {year}")
            st.toast(f"✅ Loaded: {os.path.basename(selected_file)}")

# Display loaded statements
if loaded_months:
    st.subheader("📅 Loaded Statements")
    for month in loaded_months:
        st.write(f"• {month}")

if dfs:
    # Combine and process data
    df = pd.concat(dfs, ignore_index=True)
    df.sort_values(by="Date", inplace=True)

    # Load and apply vendor mapping
    vendor_map = load_vendor_map()
    saved_custom_cats = vendor_map.get("__custom_categories__", [])
    for cat in saved_custom_cats:
        if cat not in st.session_state.custom_categories:
            st.session_state.custom_categories.append(cat)

    df = categorize(df, vendor_map)

    # Filter transactions
    st.subheader("🔍 Filter Transactions")
    with st.expander("🔍 Filter Transactions"):
        min_date = df["Date"].min()
        max_date = df["Date"].max()
        date_range = st.date_input(
            "Select date range:",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date
        )

        existing_categories = df["Category"].dropna().unique().tolist()
        all_categories = sorted(
            set(existing_categories +
                st.session_state.custom_categories + ["Uncategorized"])
        )

        all_categories_option = ["All"] + all_categories
        selected_option = st.multiselect(
            "Select Categories to Include",
            options=all_categories_option,
            default=["All"]
        )

        if "All" in selected_option:
            selected_categories = all_categories
        else:
            selected_categories = selected_option

        if isinstance(date_range, tuple) and len(date_range) == 2:
            start_date, end_date = date_range
            df = df[(df["Date"] >= pd.to_datetime(start_date)) &
                    (df["Date"] <= pd.to_datetime(end_date))]
        df = df[df["Category"].isin(selected_categories)]

    # Create tabs for different views
    tab1, tab2, tab3, tab4 = st.tabs([
        "📈 Summary",
        "📉 Expenses (Debits)",
        "📥 Payments (Credits)",
        "📆 Monthly Report"
    ])

    # Summary tab
    with tab1:
        st.subheader("📊 Total Summary")
        display_summary_metrics(df)
        st.markdown("### 📈 Financial Overview Chart")
        st.write("")
        plot_financial_overview(df)

    # Debits tab
    with tab2:
        st.subheader("✏️ Edit Debit Categories")
        debits_df = df[df["Debit/Credit"] == "Debit"].copy()
        edited_debits = st.data_editor(
            debits_df[["Date", "Details", "Amount", "Category"]],
            column_config={
                "Category": st.column_config.SelectboxColumn(
                    "Category",
                    options=all_categories
                )
            },
            use_container_width=True,
            hide_index=True,
            key="debits_editor"
        )
        df.update(edited_debits)

        debit_summary = edited_debits.groupby(
            "Category")["Amount"].sum().reset_index()
        debit_summary = debit_summary.sort_values("Amount", ascending=False)

        st.subheader("📊 Debit Summary")
        with st.expander("Show details"):
            st.dataframe(debit_summary, use_container_width=True)

        st.markdown("### ")
        if not debit_summary.empty:
            chart_type = st.radio(
                "Choose Chart Type",
                options=["Pie Chart", "Bar Chart"],
                horizontal=True,
                key="debit_chart_type"
            )
            plot_category_summary(
                debit_summary, "Debits by Category", chart_type)

    # Credits tab
    with tab3:
        st.subheader("💳 Credit Transactions (Income / Transfers)")
        credits_df = df[df["Debit/Credit"] == "Credit"].copy()
        edited_credits = st.data_editor(
            credits_df[["Date", "Details", "Amount", "Category"]],
            column_config={
                "Category": st.column_config.SelectboxColumn(
                    "Category",
                    options=all_categories
                )
            },
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
            plot_category_summary(credit_summary, "Credits by Category")

    # Monthly report tab
    with tab4:
        display_monthly_report(df)

    # Apply changes
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
