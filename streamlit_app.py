import streamlit as st
from main import (
    get_db, get_all_transactions, get_all_vendor_mappings,
    update_transaction_category, Transaction, PDFFile,
    parse_pdf_transactions, save_pdf_file, auto_categorize_transactions,
    check_existing_statement, get_month_year_from_pdf, save_transaction,
    get_pdf_files, clear_all_data
)
import pandas as pd
from datetime import datetime
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Initialize session state
if "selected_months_filter" not in st.session_state:
    st.session_state.selected_months_filter = []
if "upload_just_processed" not in st.session_state:
    st.session_state.upload_just_processed = False
if "date_range_filter" not in st.session_state:
    st.session_state.date_range_filter = None
if "category_multiselect" not in st.session_state:
    st.session_state.category_multiselect = ["All"]
if "reprocess_triggered" not in st.session_state:
    st.session_state.reprocess_triggered = False
if "upload_success" not in st.session_state:
    st.session_state.upload_success = False
if "current_month_filter" not in st.session_state:
    st.session_state.current_month_filter = []

# Main UI
st.title("💰 Finance Statement Categorizer")

# Copy all the Streamlit UI code from main.py here
# ... (copy all the Streamlit UI code from main.py)

# Remove 'transaction_id' (or 'ID') from all st.data_editor, st.dataframe, and st.table calls
# For debits data editor:
edited_debits = st.data_editor(
    debits_df[[col for col in debits_df.columns if col in [
        "Select", "date", "details", "amount", "category"]]],
    column_config={
        "Select": st.column_config.CheckboxColumn(required=True),
        "category": st.column_config.SelectboxColumn(
            "Category",
            options=[
                "All"] + sorted(df_display["category"].unique().tolist())
        ),
        "details": st.column_config.TextColumn(
            "Details",
            help="Transaction description",
            width="large"
        )
    },
    use_container_width=True,
    hide_index=True,
    key="debits_editor"
)
# For credits data editor:
edited_credits = st.data_editor(
    credits_df[[col for col in credits_df.columns if col in [
        "Select", "date", "details", "amount", "category"]]],
    column_config={
        "Select": st.column_config.CheckboxColumn(required=True),
        "category": st.column_config.SelectboxColumn(
            "Category",
            options=[
                "All"] + sorted(df_display["category"].unique().tolist())
        ),
        "details": st.column_config.TextColumn(
            "Details",
            help="Transaction description",
            width="large"
        )
    },
    use_container_width=True,
    hide_index=True,
    key="credits_editor"
)
# For all st.dataframe and st.table calls, exclude transaction_id/ID:


def show_user_table(df):
    cols = [col for col in df.columns if col.lower() not in ("id",
                                                             "transaction_id")]
    st.dataframe(df[cols], use_container_width=True)
# Replace all st.dataframe(...) calls with show_user_table(...)
# Example:
# show_user_table(credit_summary)
# show_user_table(debit_summary)
# show_user_table(monthly_summary)
# show_user_table(monthly_cashflow)
# show_user_table(df_display) # if you ever show the main table
# Do this after any DataFrame refreshes or updates as well.


# After uploading and saving transactions, add this debug output:
if uploaded_files and not st.session_state.upload_success:
    for file in uploaded_files:
        if validate_file(file):
            try:
                pdf_content = file.read()
                month_year = get_month_year_from_pdf(pdf_content)
                if check_existing_statement(db, file.name, month_year):
                    st.warning(
                        f"Statement '{file.name}' for {month_year} already exists in the database.")
                    continue
                transactions, opening_balance, closing_balance = parse_pdf_transactions(
                    pdf_content)
                if transactions:
                    try:
                        pdf_file = save_pdf_file(
                            db, file.name, pdf_content, month_year,
                            opening_balance=opening_balance if opening_balance > 0 else None,
                            closing_balance=closing_balance if closing_balance > 0 else None
                        )
                        transactions = auto_categorize_transactions(
                            db, transactions)
                        for trans in transactions:
                            trans['pdf_file_id'] = pdf_file.id
                            save_transaction(db, trans)
                        if opening_balance > 0:
                            st.info(
                                f"Found opening balance: C${opening_balance:,.2f}")
                        if closing_balance > 0:
                            st.info(
                                f"Found closing balance: C${closing_balance:,.2f}")
                        st.success(
                            f"✅ Added {len(transactions)} new transactions from {file.name}")
                        st.session_state.upload_success = True
                        # Debug output: show the first few rows of the new transactions
                        st.write("### Debug: Uploaded Transactions Preview")
                        df_uploaded = pd.DataFrame(transactions)
                        st.write(df_uploaded.head())
                        if 'date' in df_uploaded.columns:
                            st.write("Uploaded transaction dates:",
                                     df_uploaded['date'].unique())
                        # Immediately rerun to refresh months filter and sidebar
                        st.rerun()
                    except Exception as e:
                        logger.error(f"Error saving data: {str(e)}")
                        st.error(
                            f"Error saving data from {file.name}. Please try again.")
                else:
                    st.warning(f"No transactions found in {file.name}")
            except Exception as e:
                logger.error(f"Error processing {file.name}: {str(e)}")
                st.error(f"Error processing {file.name}. Please try again.")
# After main display, if no data is shown, add a warning to check the month filter:
# This is an example - uncomment and modify as needed for your actual app
"""
if not df.empty and df.shape[0] > 0 and df_display.empty:
    st.warning("No transactions are visible. Please check your month filter in the sidebar. Available months: {}".format(
        sorted([m for m in df['MonthYear'].unique() if m is not None])))

    # Check if date column exists and has valid values before displaying
    if 'date' in df.columns:
        # Ensure date column is datetime type
        if not pd.api.types.is_datetime64_any_dtype(df['date']):
            df['date'] = pd.to_datetime(df['date'], errors='coerce')

        # Only show valid dates
        valid_dates = df['date'].dropna().unique()
        if len(valid_dates) > 0:
            st.write("All transaction dates in database:", valid_dates)
"""
