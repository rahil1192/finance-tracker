import streamlit as st
import pandas as pd
import pdfplumber
import re
import os
import json
import plotly.express as px
from datetime import datetime
import logging
from pathlib import Path
import yaml
from typing import Dict, List, Optional, Union
import traceback
import io
from models import (
    get_db, save_transaction, get_all_transactions, save_vendor_mapping,
    get_all_vendor_mappings, update_transaction_category, init_db,
    save_pdf_file, get_pdf_files, get_pdf_content, PDFFile, VendorMapping,
    clear_all_data, get_latest_statement_balance, ensure_vendor_mappings, Transaction
)
from fastapi import FastAPI, HTTPException, Depends, UploadFile, File
from fastapi.security import OAuth2PasswordBearer
from fastapi.middleware.cors import CORSMiddleware
import jwt
from sqlalchemy.orm import Session

# Initialize database tables if needed (won't recreate if they exist)
init_db()

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

# Load configuration


def load_config() -> Dict:
    """Load configuration from config.yaml file."""
    config_path = Path("config.yaml")
    if not config_path.exists():
        # Create default config if it doesn't exist
        default_config = {
            "ui": {
                "page_title": "Finance Categorizer",
                "layout": "wide",
                "theme": "light"
            },
            "processing": {
                "max_file_size_mb": 10,
                "supported_file_types": ["pdf"],
                "date_format": "%Y-%m-%d"
            }
        }
        with open(config_path, "w") as f:
            yaml.dump(default_config, f)
        return default_config

    with open(config_path, "r") as f:
        return yaml.safe_load(f)


# Load configuration
CONFIG = load_config()

# Constants from config
MAX_FILE_SIZE = CONFIG["processing"]["max_file_size_mb"] * \
    1024 * 1024  # Convert to bytes

# Page configuration
st.set_page_config(
    page_title=CONFIG["ui"]["page_title"],
    layout=CONFIG["ui"]["layout"],
    initial_sidebar_state="expanded"
)


def validate_file(file) -> bool:
    """Validate uploaded file size and type."""
    if file.size > MAX_FILE_SIZE:
        st.error(
            f"File size exceeds maximum limit of {CONFIG['processing']['max_file_size_mb']}MB")
        return False
    if not file.type.endswith(tuple(CONFIG['processing']['supported_file_types'])):
        st.error(
            f"Unsupported file type. Please upload {', '.join(CONFIG['processing']['supported_file_types'])} files only.")
        return False
    return True


def check_existing_statement(db, filename: str, month_year: str) -> bool:
    """Check if a statement with the same name and month/year exists."""
    existing_files = get_pdf_files(db)
    return any(f.original_filename == filename and f.month_year == month_year for f in existing_files)


def classify_transaction_type(details: str) -> str:
    """Classify transaction type based on details."""
    text = details.lower()

    credit_keywords = ["rewards", "rebate", "refund", "e-transfer reclaim",
                       "e-transfer paydirect"]
    if any(k in text for k in credit_keywords):
        return "Credit"

    debit_keywords = ["retail", "debit", "purchase", "fulfill request", "e-transfer",
                      "bill", "charge", "petro", "service", "withdrawal"]
    if any(k in text for k in debit_keywords):
        return "Debit"
    return "Credit"


def get_month_year_from_pdf(pdf_content: bytes) -> str:
    """Extract month and year from PDF content."""
    try:
        with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
            for page in pdf.pages:
                lines = page.extract_text().split("\n")
                for line in lines:
                    date_match = re.match(
                        r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}", line)
                    if date_match:
                        return date_match.group(1) + "_" + str(datetime.now().year)
    except Exception as e:
        logger.error(f"Error extracting month from PDF: {e}")
    return datetime.now().strftime("%b_%Y")


def parse_pdf_transactions(pdf_content: bytes) -> tuple[List[Dict], float, float]:
    """Parse PDF transactions and return list of transaction dictionaries, opening balance, and closing balance."""
    data = []
    opening_balance = 0.0
    closing_balance = 0.0
    try:
        current_date = None
        with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                lines = text.split("\n")

                # Debug: Log all lines
                logger.info("Searching all lines for opening balance...")

                # First pass: Look for opening balance in all lines
                for line in lines:
                    original_line = line
                    line = line.strip()

                    # Try multiple patterns to match opening balance
                    if "opening balance" in line.lower():
                        logger.info(
                            f"Found potential opening balance line: '{line}'")
                        try:
                            # Pattern 1: Look for decimal number
                            amount_match = re.search(
                                r'(\d{1,3}(?:,\d{3})*\.\d{2})', line)
                            if amount_match:
                                balance_text = amount_match.group(1)
                                opening_balance = float(
                                    balance_text.replace(",", ""))
                                logger.info(
                                    f"Successfully extracted opening balance: ${opening_balance:,.2f}")
                                break

                            # Pattern 2: After "Opening balance"
                            balance_text = line.split("balance")[-1].strip()
                            # Remove $ and any other non-numeric chars except . and ,
                            balance_text = re.sub(r'[^\d.,]', '', balance_text)
                            if balance_text:
                                opening_balance = float(
                                    balance_text.replace(",", ""))
                                logger.info(
                                    f"Successfully extracted opening balance: ${opening_balance:,.2f}")
                                break
                        except ValueError as e:
                            logger.error(
                                f"Error parsing opening balance from '{original_line}': {e}")
                            continue

                # Second pass: Process transactions
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue

                    # Look for closing balance line
                    if "closing balance" in line.lower():
                        try:
                            amount_match = re.search(
                                r'\$?([\d,]+\.\d{2})\s*$', line)
                            if amount_match:
                                closing_balance = float(
                                    amount_match.group(1).replace(",", ""))
                                logger.info(
                                    f"Found closing balance: ${closing_balance:,.2f}")
                                continue
                        except ValueError as e:
                            logger.error(f"Error parsing closing balance: {e}")
                            continue

                    date_match = re.match(
                        r"^((Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2})(.*)", line)
                    if date_match:
                        current_date = date_match.group(1).strip()
                        line = date_match.group(3).strip()

                    # Skip the opening balance line when parsing transactions
                    if "opening balance" in line.lower():
                        continue

                    matches = re.findall(
                        r"([\d,]+\.\d{2}) ([\d,]+\.\d{2})", line)
                    if matches:
                        parts = re.split(r"[\d,]+\.\d{2} [\d,]+\.\d{2}", line)
                        for i, (amount_str, _) in enumerate(matches):
                            desc = parts[i].strip() if i < len(parts) else ""
                            amount = float(amount_str.replace(",", ""))
                            details = desc
                            trans_type = classify_transaction_type(details)
                            data.append({
                                "date": pd.to_datetime(current_date + " 2025", errors='coerce'),
                                "details": details,
                                "amount": amount,
                                "transaction_type": trans_type,
                                "category": "Uncategorized"
                            })
                    else:
                        if data:
                            data[-1]["details"] += " " + line

        logger.info(f"Extracted {len(data)} transactions")
        if opening_balance > 0:
            logger.info(f"Opening balance: ${opening_balance:,.2f}")
        if closing_balance > 0:
            logger.info(f"Final closing balance: ${closing_balance:,.2f}")
        else:
            logger.warning("No closing balance found in statement")

    except Exception as e:
        logger.error(f"Error parsing PDF: {str(e)}\n{traceback.format_exc()}")
        st.error("Error parsing PDF file. Please check the file format.")

    return data, opening_balance, closing_balance


def categorize_transaction(details: str, vendor_map: Dict) -> str:
    """Categorize a transaction based on vendor mapping."""
    if not details or not vendor_map:
        return "Uncategorized"

    # Normalize the transaction details
    details = ' '.join(details.lower().split())
    logger.info(f"Categorizing transaction: {details}")

    # Extract the main part of the transaction
    main_text = re.sub(r'[0-9]+', '', details)
    main_text = re.sub(r'[^\w\s]', ' ', main_text)
    main_text = ' '.join(main_text.split())

    for vendor_substring, category in vendor_map.items():
        if vendor_substring == "__custom_categories__":
            continue

        if not isinstance(vendor_substring, str):
            continue

        vendor_substring = ' '.join(vendor_substring.lower().split())
        if (vendor_substring in details or
            vendor_substring in main_text or
                any(word in details.split() for word in vendor_substring.split())):
            logger.info(f"Found match: '{vendor_substring}' -> '{category}'")
            return category

    logger.info(f"No category match found for: {details}")
    return "Uncategorized"


def auto_categorize_transactions(db, transactions: List[Dict]) -> List[Dict]:
    """Auto-categorize a list of transactions using vendor mappings."""
    # Ensure vendor mappings exist
    vendor_map = ensure_vendor_mappings(db)
    if not vendor_map:
        logger.warning("No vendor mappings available for auto-categorization")
        return transactions

    for trans in transactions:
        trans['category'] = categorize_transaction(
            trans['details'], vendor_map)
    return transactions


def load_vendor_map_from_json() -> Dict:
    """Load vendor mappings from vendor_map.json file."""
    try:
        # Get the absolute path to vendor_map.json
        current_dir = os.path.dirname(os.path.abspath(__file__))
        vendor_map_path = os.path.join(current_dir, 'vendor_map.json')

        logger.info(f"Attempting to load vendor map from: {vendor_map_path}")

        if not os.path.exists(vendor_map_path):
            logger.warning(f"vendor_map.json not found at {vendor_map_path}")
            # Try current working directory
            vendor_map_path = 'vendor_map.json'
            if not os.path.exists(vendor_map_path):
                logger.error(
                    "vendor_map.json not found in current directory either")
                return {}

        with open(vendor_map_path, 'r', encoding='utf-8') as f:
            content = f.read()
            logger.info(f"Read {len(content)} bytes from vendor_map.json")
            mappings = json.loads(content)
            if not isinstance(mappings, dict):
                logger.error(
                    f"Invalid vendor map format: expected dict, got {type(mappings)}")
                return {}
            logger.info(
                f"Successfully loaded {len(mappings)} mappings from vendor_map.json")
            return mappings
    except json.JSONDecodeError as e:
        logger.error(f"Error parsing vendor_map.json: {e}")
        return {}
    except Exception as e:
        logger.error(f"Unexpected error loading vendor map: {e}")
        return {}


def import_vendor_mappings(db) -> int:
    """Import vendor mappings from JSON file to database."""
    try:
        vendor_map = load_vendor_map_from_json()
        if not vendor_map:
            logger.error("No vendor mappings loaded from file")
            return 0

        logger.info(f"Loaded vendor map with {len(vendor_map)} entries")
        imported_count = 0

        # Clear existing mappings first
        try:
            db.query(VendorMapping).delete()
            db.commit()
            logger.info("Cleared existing vendor mappings")
        except Exception as e:
            logger.error(f"Error clearing existing mappings: {e}")
            db.rollback()
            return 0

        for vendor, category in vendor_map.items():
            if vendor == "__custom_categories__":
                continue

            if not isinstance(vendor, str) or not isinstance(category, str):
                logger.warning(
                    f"Skipping invalid mapping: {vendor} -> {category}")
                continue

            try:
                # Normalize the vendor string
                vendor = ' '.join(vendor.lower().split())
                save_vendor_mapping(db, vendor, category)
                imported_count += 1
                logger.info(f"Imported mapping: {vendor} -> {category}")
            except Exception as e:
                logger.error(
                    f"Error saving mapping {vendor} -> {category}: {e}")

        db.commit()
        logger.info(f"Successfully imported {imported_count} vendor mappings")
        return imported_count
    except Exception as e:
        logger.error(
            f"Error importing vendor mappings: {str(e)}\n{traceback.format_exc()}")
        db.rollback()
        return 0


def recategorize_all_transactions(db) -> int:
    """Recategorize all transactions using current vendor mappings."""
    try:
        transactions = get_all_transactions(db)
        vendor_map = get_all_vendor_mappings(db)
        logger.info(
            f"Loaded {len(vendor_map)} vendor mappings for recategorization")

        updated_count = 0
        total_count = len(transactions)
        logger.info(f"Processing {total_count} transactions")

        for trans in transactions:
            try:
                new_category = categorize_transaction(
                    trans.details, vendor_map)
                if new_category != trans.category:
                    logger.info(
                        f"Updating category for '{trans.details}' from '{trans.category}' to '{new_category}'")
                    update_transaction_category(db, trans.id, new_category)
                    updated_count += 1
            except Exception as e:
                logger.error(
                    f"Error processing transaction {trans.id}: {str(e)}")
                continue

        db.commit()
        logger.info(
            f"Updated {updated_count} out of {total_count} transaction categories")
        return updated_count
    except Exception as e:
        logger.error(
            f"Error recategorizing transactions: {str(e)}\n{traceback.format_exc()}")
        db.rollback()
        return 0


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

# Add helpful tooltips and documentation
with st.sidebar:
    st.markdown("""
    ### 📚 Quick Guide
    1. Upload your bank statements (PDF)
    2. Select months to view
    3. Categorize transactions
    4. View summaries and reports
    """)

    st.divider()
    st.subheader("🗓️ Filter by Month")

# Get database session
db = next(get_db())

# Ensure vendor mappings are imported
try:
    import_vendor_mappings(db)
    logger.info("Vendor mappings imported successfully")
except Exception as e:
    logger.error(f"Error importing vendor mappings: {str(e)}")

# Get available months from the database
transactions = get_all_transactions(db)
if transactions:
    df = pd.DataFrame([{
        'date': t.date,
        'details': t.details,
        'amount': t.amount,
        'transaction_type': t.transaction_type,
        'category': t.category,
        'transaction_id': t.id
    } for t in transactions])

    # Create MonthYear column for filtering
    df['MonthYear'] = df['date'].dt.strftime('%Y-%m')
    available_months = sorted(df['MonthYear'].unique(), reverse=True)
else:
    df = pd.DataFrame()
    available_months = []

# Define a callback for month selection


def on_month_select():
    st.session_state.current_month_filter = st.session_state.month_selector
    st.session_state.selected_months_filter = st.session_state.month_selector


# Store the selected months in session state using the callback
selected_months = st.sidebar.multiselect(
    "Select months to view",
    options=available_months,
    default=st.session_state.current_month_filter,
    key="month_selector",
    on_change=on_month_select,
    help="Select one or more months to filter transactions"
)

# Add debug information in sidebar
with st.sidebar.expander("🔍 Debug Information"):
    st.write("Selected Months:", selected_months)
    if not df.empty:
        st.write("Total Transactions:", len(df))
        filtered_df = df[df['MonthYear'].isin(
            selected_months)] if selected_months else df
        st.write("Filtered Transactions:", len(filtered_df))
        st.write("Debits:", len(
            filtered_df[filtered_df["transaction_type"] == "Debit"]))
        st.write("Credits:", len(
            filtered_df[filtered_df["transaction_type"] == "Credit"]))

# Add new statements section
st.sidebar.divider()
st.sidebar.subheader("➕ Add New Statements")

# Add Clear Data button
st.sidebar.divider()
with st.sidebar.expander("⚠️ Danger Zone"):
    st.warning("This action cannot be undone!")
    if st.button("🗑️ Clear All Data", type="primary"):
        if st.session_state.get('confirm_clear', False):
            try:
                clear_all_data(db)
                st.success("✅ All data has been cleared successfully!")
                # Reset session state
                st.session_state.selected_months_filter = []
                st.session_state.upload_just_processed = False
                st.session_state.date_range_filter = None
                st.session_state.category_multiselect = ["All"]
                st.session_state.confirm_clear = False
                st.session_state.reprocess_triggered = False
                st.session_state.upload_success = False
                # Force a rerun to refresh the page
                st.rerun()
            except Exception as e:
                st.error(f"Error clearing data: {str(e)}")
        else:
            st.session_state.confirm_clear = True
            st.error("⚠️ Are you sure? Click again to confirm.")
    else:
        # Reset confirmation if button is not clicked
        st.session_state.confirm_clear = False

# Process new uploads
uploaded_files = st.sidebar.file_uploader(
    "Upload new statement PDFs",
    type=CONFIG['processing']['supported_file_types'],
    accept_multiple_files=True,
    help="Upload one or more PDF bank statements"
)

if uploaded_files and not st.session_state.upload_success:
    for file in uploaded_files:
        if validate_file(file):
            try:
                # Read file content
                pdf_content = file.read()

                # Get month/year from PDF content
                month_year = get_month_year_from_pdf(pdf_content)

                # Check if file already exists
                if check_existing_statement(db, file.name, month_year):
                    st.warning(
                        f"Statement '{file.name}' for {month_year} already exists in the database.")
                    continue

                # Parse transactions and balances from PDF content
                logger.info(f"Processing PDF file: {file.name}")
                try:
                    transactions, opening_balance, closing_balance = parse_pdf_transactions(
                        pdf_content)
                except ValueError as e:
                    logger.error(f"Error parsing transactions: {e}")
                    transactions, opening_balance, closing_balance = [], 0.0, 0.0

                if transactions:
                    try:
                        # Save PDF file with balances
                        pdf_file = save_pdf_file(
                            db, file.name, pdf_content, month_year,
                            opening_balance=opening_balance if opening_balance > 0 else None,
                            closing_balance=closing_balance if closing_balance > 0 else None
                        )

                        # Auto-categorize transactions
                        transactions = auto_categorize_transactions(
                            db, transactions)

                        # Save transactions to database with PDF file reference
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
                    except Exception as e:
                        logger.error(f"Error saving data: {str(e)}")
                        st.error(
                            f"Error saving data from {file.name}. Please try again.")
                else:
                    st.warning(f"No transactions found in {file.name}")
            except Exception as e:
                logger.error(f"Error processing {file.name}: {str(e)}")
                st.error(f"Error processing {file.name}. Please try again.")

# Reset flags if no files are uploaded
if not uploaded_files:
    st.session_state.upload_success = False
    st.session_state.reprocess_triggered = False

# Main display with error handling
try:
    if not df.empty:
        # Apply month filter
        if selected_months:
            df_display = df[df['MonthYear'].isin(selected_months)].copy()
            st.sidebar.write(
                f"Showing transactions for: {', '.join(selected_months)}")
        else:
            df_display = df.copy()
            st.sidebar.write(
                "Showing all transactions (no month filter applied)")

        transactions = get_all_transactions(db)
        pdf_files = get_pdf_files(db)

        if not pdf_files:
            st.info("Upload statement PDFs using the sidebar to begin.")
        else:
            if transactions:
                # Create the initial DataFrame with transaction_id
                df = pd.DataFrame([{
                    'date': t.date,
                    'details': t.details,
                    'amount': t.amount,
                    'transaction_type': t.transaction_type,
                    'category': t.category,
                    'transaction_id': t.id  # Ensure transaction_id is included
                } for t in transactions])

                # Date range filter
                if st.session_state.date_range_filter and isinstance(st.session_state.date_range_filter, tuple) and len(st.session_state.date_range_filter) == 2:
                    start_date, end_date = st.session_state.date_range_filter
                    start_date = pd.to_datetime(start_date).date()
                    end_date = pd.to_datetime(end_date).date()
                    df_display = df_display[(df_display["date"].dt.date >= start_date) &
                                            (df_display["date"].dt.date <= end_date)]

                # Category filter
                if st.session_state.category_multiselect and "All" not in st.session_state.category_multiselect:
                    df_display = df_display[df_display["category"].isin(
                        st.session_state.category_multiselect)]

                # Create filtered debits and credits DataFrames
                debits_df = df_display[df_display["transaction_type"]
                                       == "Debit"].copy()
                credits_df = df_display[df_display["transaction_type"] == "Credit"].copy(
                )

                # Display tabs
                tab1, tab2, tab3, tab4, tab5 = st.tabs(
                    ["🔄 Reconcile", "📈 Summary", "📉 Expenses", "📥 Payments", "📆 Monthly"])

                with tab1:
                    st.subheader("🔄 Balance Reconciliation")
                    # Add reconciliation section
                    with st.expander("Statement Details", expanded=True):
                        col1, col2, col3 = st.columns(3)

                        # Get the statement balances based on selected months
                        if selected_months:
                            # Convert YYYY-MM format to Month_YYYY format used in database
                            db_month_formats = []
                            for month in selected_months:
                                year, month_num = month.split('-')
                                # Convert month number to name
                                month_name = datetime.strptime(
                                    month_num, '%m').strftime('%b')
                                db_month_formats.append(
                                    f"{month_name}_{year}")
                            pdf_files_query = db.query(PDFFile).filter(
                                PDFFile.month_year.in_(db_month_formats)
                            ).order_by(PDFFile.upload_date.asc())
                            pdf_files_list = pdf_files_query.all()
                        else:
                            # If no months selected, fetch ALL statements
                            pdf_files_query = db.query(PDFFile).order_by(PDFFile.upload_date.asc())
                            pdf_files_list = pdf_files_query.all()

                            # Debug information
                            st.sidebar.write("Debug: Statement Matching")
                            if selected_months:
                                st.sidebar.write(f"Looking for months: {db_month_formats}")
                            st.sidebar.write(f"Found {len(pdf_files_list)} matching statements")

                            if pdf_files_list:
                                # Show per-statement reconciliation table if more than one statement is selected OR if no months are selected
                                if len(pdf_files_list) > 1 or not selected_months:
                                    statement_rows = []
                                    for pdf in pdf_files_list:
                                        statement_transactions = [t for t in transactions if getattr(t, "pdf_file_id", None) == pdf.id]
                                        total_debits = sum(t.amount for t in statement_transactions if t.transaction_type == "Debit")
                                        total_credits = sum(t.amount for t in statement_transactions if t.transaction_type == "Credit")
                                        calculated_closing = (pdf.opening_balance or 0) + total_credits - total_debits
                                        difference = (pdf.closing_balance - calculated_closing) if pdf.closing_balance is not None else None

                                        statement_rows.append({
                                            "Statement": pdf.original_filename,
                                            "Month/Year": pdf.month_year,
                                            "Opening Balance": pdf.opening_balance,
                                            "Total Debits": total_debits,
                                            "Total Credits": total_credits,
                                            "Calculated Closing": calculated_closing,
                                            "Closing Balance": pdf.closing_balance,
                                            "Difference": difference
                                        })
                                    df_statements = pd.DataFrame(statement_rows)
                                    st.markdown("### Individual Statement Reconciliation")
                                    st.dataframe(df_statements, use_container_width=True)
                                else:
                                    # Only for a single statement: define and use opening_balance and closing_balance
                                    first_statement = pdf_files_list[0]
                                    opening_balance = first_statement.opening_balance if first_statement.opening_balance is not None else 0.0
                                    last_statement = pdf_files_list[-1]
                                    closing_balance = last_statement.closing_balance if last_statement.closing_balance is not None else None

                                    with col1:
                                        st.metric("Opening Balance",
                                                  f"C${opening_balance:,.2f}")

                                    # Calculate totals for reconciliation
                                    total_debits = df_display[df_display["transaction_type"] == "Debit"]["amount"].sum()
                                    total_credits = df_display[df_display["transaction_type"] == "Credit"]["amount"].sum()
                                    calculated_balance = opening_balance + total_credits - total_debits

                                    # Show reconciliation results
                                    with col2:
                                        if closing_balance is not None:
                                            st.metric("Closing Balance",
                                                      f"C${closing_balance:,.2f}")
                                        else:
                                            st.metric(
                                                "Closing Balance", f"C${calculated_balance:,.2f} (Calculated)")

                                    with col3:
                                        if closing_balance is not None:
                                            difference = closing_balance - calculated_balance
                                            st.metric("Difference from Statement",
                                                      f"C${abs(difference):.2f}",
                                                      delta=f"{'Matches' if abs(difference) < 0.01 else 'Off by ' + f'C${abs(difference):.2f}'}",
                                                      delta_color="normal" if abs(difference) < 0.01 else "inverse")
                                        else:
                                            st.metric("Calculated Balance",
                                                      f"C${calculated_balance:,.2f}")

                                    # Show detailed breakdown and reconciliation status only for single statement
                                    st.markdown("### Reconciliation Details")
                                    col1, col2, col3 = st.columns(3)
                                    col1.metric("\U0001F4B8 Total Debits", f"C${total_debits:,.2f}")
                                    col2.metric("\U0001F4B0 Total Credits",
                                                f"C${total_credits:,.2f}")
                                    col3.metric("\U0001F9FE Net Change",
                                                f"C${total_credits - total_debits:,.2f}")

                                    # Add reconciliation status
                                    if closing_balance is not None:
                                        if abs(calculated_balance - closing_balance) < 0.01:
                                            st.success(
                                                "\u2705 Balances Match! Your transactions are reconciled.")
                                        else:
                                            st.warning(
                                                f"\u26A0\uFE0F Balances Don't Match! There's a difference of C${abs(calculated_balance - closing_balance):.2f}")
                                            st.markdown("""
                                            **Possible reasons for the difference:**
                                            - Missing transactions
                                            - Duplicate transactions
                                            - Incorrect transaction amounts
                                            - Pending transactions not included
                                            - Bank fees or interest not recorded
                                            """)
                            

                with tab2:
                    st.subheader("📊 Total Summary")

                    # Calculate totals
                    total_debits = df_display[df_display["transaction_type"] == "Debit"]["amount"].sum(
                    )
                    total_credits = df_display[df_display["transaction_type"] == "Credit"]["amount"].sum(
                    )
                    net_change = total_credits - total_debits

                    # Show summary metrics
                    st.markdown("### 💰 Cash Flow Overview")
                    col1, col2, col3 = st.columns(3)
                    col1.metric("💸 Total Debits", f"C${total_debits:,.2f}")
                    col2.metric("💰 Total Credits", f"C${total_credits:,.2f}")
                    col3.metric("📊 Net Cash Flow",
                                f"C${net_change:,.2f}",
                                delta=f"{'Positive' if net_change > 0 else 'Negative'} Flow",
                                delta_color="normal" if net_change > 0 else "inverse"
                                )

                    # Add monthly cash flow breakdown
                    st.markdown("### 📅 Monthly Cash Flow")
                    df_display["Month"] = df_display["date"].dt.strftime(
                        "%Y-%m")
                    monthly_cashflow = df_display.groupby("Month").apply(
                        lambda x: pd.Series({
                            "Debits": x[x["transaction_type"] == "Debit"]["amount"].sum(),
                            "Credits": x[x["transaction_type"] == "Credit"]["amount"].sum(),
                            "Net Flow": x[x["transaction_type"] == "Credit"]["amount"].sum() -
                            x[x["transaction_type"] == "Debit"]["amount"].sum()
                        })
                    ).reset_index()

                    # Sort by month
                    monthly_cashflow = monthly_cashflow.sort_values("Month")

                    # Display monthly cash flow table
                    st.dataframe(monthly_cashflow, use_container_width=True)

                    # Plot monthly cash flow
                    fig = px.bar(monthly_cashflow, x="Month", y=["Debits", "Credits", "Net Flow"],
                                 title="Monthly Cash Flow Breakdown",
                                 barmode="group")
                    st.plotly_chart(fig, use_container_width=True)

                    # Add summary charts
                    st.markdown("### 📈 Transaction Summary")
                    summary_df = pd.DataFrame({
                        "Type": ["Credits", "Debits"],
                        "Amount": [total_credits, total_debits]
                    })

                    chart_type = st.radio("Select chart type:", [
                                          "Bar Chart", "Pie Chart"], horizontal=True, key="summary_chart_type")
                    if chart_type == "Bar Chart":
                        fig = px.bar(summary_df, x="Type", y="Amount",
                                     color="Type", title="Financial Overview")
                    else:
                        fig = px.pie(summary_df, values="Amount", names="Type",
                                     title="Financial Overview", hole=0.4)
                    st.plotly_chart(fig, use_container_width=True)

                with tab3:
                    st.subheader("✏️ Edit Debit Categories")
                    st.markdown(
                        "_*ℹ️ Double Click on a transaction's Field to edit it.*_")

                    # Category Management for Expenses
                    with st.expander("🏷️ Manage Expense Categories"):
                        # Get existing vendor mappings
                        vendor_map = get_all_vendor_mappings(db)

                        # Add new category mapping
                        col1, col2 = st.columns(2)
                        with col1:
                            new_vendor = st.text_input(
                                "Vendor Name/Keyword",
                                help="Enter vendor name or keyword to categorize",
                                key="expense_vendor_input"
                            )
                        with col2:
                            new_category = st.text_input(
                                "Category",
                                help="Enter category name",
                                key="expense_category_input"
                            )
                        if st.button("Add Category", key="expense_add_category_btn"):
                            if new_vendor and new_category:
                                save_vendor_mapping(
                                    db, new_vendor.lower(), new_category)
                                st.success(
                                    f"Added mapping: {new_vendor} → {new_category}")
                                vendor_map = get_all_vendor_mappings(
                                    db)  # Refresh mappings
                                # Recategorize all transactions with new mapping
                                recategorize_all_transactions(db)
                                st.success(
                                    "🔄 Updated all transaction categories")
                            else:
                                st.error(
                                    "Please enter both vendor and category")

                    if not debits_df.empty:
                        debits_df["Select"] = False

                        # First render the data editor to check selections
                        edited_debits = st.data_editor(
                            debits_df[["Select", "date",
                                       "details", "amount", "category", "transaction_id"]],
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
                                ),
                                "transaction_id": st.column_config.Column(
                                    "ID",
                                    disabled=True,
                                    required=True,
                                    help="Internal transaction ID"
                                )
                            },
                            use_container_width=True,
                            hide_index=True,
                            key="debits_editor"
                        )

                        # Then add the switch button with the correct disabled state
                        col1, col2 = st.columns([2, 8])
                        with col1:
                            has_selections = edited_debits["Select"].any()
                            if st.button(
                                "🔄 Switch Selected to Credits",
                                key="switch_debits_to_credits",
                                disabled=not has_selections,
                                type="primary" if has_selections else "secondary"
                            ):
                                selected_rows = edited_debits[edited_debits["Select"]]
                                selected_trans_ids = selected_rows["transaction_id"].tolist(
                                )

                                switched_count = 0
                                for trans_id in selected_trans_ids:
                                    transaction = db.query(Transaction).filter(
                                        Transaction.id == trans_id).first()
                                    if transaction:
                                        transaction.transaction_type = "Credit"
                                        switched_count += 1

                                if switched_count > 0:
                                    db.commit()
                                    st.success(
                                        f"Switched {switched_count} transaction(s) to Credit")
                                    # Preserve the current month filter before rerunning
                                    st.session_state.current_month_filter = st.session_state.selected_months_filter
                                    st.rerun()
                                else:
                                    st.warning("No transactions were switched")

                        # Update categories in database
                        for idx, row in edited_debits.iterrows():
                            if row["Select"]:
                                trans_id = row["transaction_id"]
                                update_transaction_category(
                                    db, trans_id, row["category"])

                        # Refresh the data after updating
                        df_display = pd.DataFrame([{
                            'date': t.date,
                            'details': t.details,
                            'amount': t.amount,
                            'transaction_type': t.transaction_type,
                            'category': t.category,
                            'transaction_id': t.id  # Ensure transaction_id is included in refresh
                        } for t in get_all_transactions(db)])

                        debit_summary = edited_debits.groupby(
                            "category")["amount"].sum().reset_index()
                        debit_summary = debit_summary.sort_values(
                            "amount", ascending=False)

                        st.subheader("📊 Debit Summary")
                        with st.expander("Show details"):
                            st.dataframe(
                                debit_summary, use_container_width=True)

                        if not debit_summary.empty:
                            chart_type = st.radio("Choose Chart Type", [
                                "Pie Chart", "Bar Chart"], horizontal=True, key="debit_chart_type")
                            if chart_type == "Pie Chart":
                                fig = px.pie(debit_summary, values="amount",
                                             names="category", title="Debits by Category", hole=0.4)
                            else:
                                fig = px.bar(debit_summary, x="category", y="amount",
                                             title="Expenses by Category", color="category")
                            st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.info(
                            "No debit transactions found in the selected period.")

                with tab4:
                    st.subheader("💳 Credit Transactions")
                    st.markdown(
                        "_*ℹ️ Click on a transaction's 'Details' text below to edit it.*_")

                    # Category Management for Credits
                    with st.expander("🏷️ Manage Income Categories"):
                        # Get existing vendor mappings
                        vendor_map = get_all_vendor_mappings(db)

                        # Add new category mapping
                        col1, col2 = st.columns(2)
                        with col1:
                            new_vendor = st.text_input(
                                "Vendor Name/Keyword",
                                help="Enter vendor name or keyword to categorize",
                                key="income_vendor_input"
                            )
                        with col2:
                            new_category = st.text_input(
                                "Category",
                                help="Enter category name",
                                key="income_category_input"
                            )
                        if st.button("Add Category", key="income_add_category_btn"):
                            if new_vendor and new_category:
                                save_vendor_mapping(
                                    db, new_vendor.lower(), new_category)
                                st.success(
                                    f"Added mapping: {new_vendor} → {new_category}")
                                vendor_map = get_all_vendor_mappings(
                                    db)  # Refresh mappings
                                # Recategorize all transactions with new mapping
                                recategorize_all_transactions(db)
                                st.success(
                                    "🔄 Updated all transaction categories")
                            else:
                                st.error(
                                    "Please enter both vendor and category")

                    if not credits_df.empty:
                        credits_df["Select"] = False

                        # First render the data editor to check selections
                        edited_credits = st.data_editor(
                            credits_df[["Select", "date",
                                        "details", "amount", "category"]],
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
                                ),
                                "transaction_id": st.column_config.Column(
                                    "ID",
                                    disabled=True,
                                    required=True,
                                    help="Internal transaction ID"
                                )
                            },
                            use_container_width=True,
                            hide_index=True,
                            key="credits_editor"
                        )

                        # Then add the switch button with the correct disabled state
                        col1, col2 = st.columns([2, 8])
                        with col1:
                            has_selections = edited_credits["Select"].any()
                            if st.button(
                                "🔄 Switch Selected to Debits",
                                key="switch_credits_to_debits",
                                disabled=not has_selections,
                                type="primary" if has_selections else "secondary"
                            ):
                                selected_rows = edited_credits[edited_credits["Select"]]
                                selected_trans_ids = selected_rows["transaction_id"].tolist(
                                )

                                switched_count = 0
                                for trans_id in selected_trans_ids:
                                    transaction = db.query(Transaction).filter(
                                        Transaction.id == trans_id).first()
                                    if transaction:
                                        transaction.transaction_type = "Debit"
                                        switched_count += 1

                                if switched_count > 0:
                                    db.commit()
                                    st.success(
                                        f"Switched {switched_count} transaction(s) to Debit")
                                    # Preserve the current month filter before rerunning
                                    st.session_state.current_month_filter = st.session_state.selected_months_filter
                                    st.rerun()
                                else:
                                    st.warning("No transactions were switched")

                        # Update categories in database
                        for idx, row in edited_credits.iterrows():
                            if row["Select"]:
                                trans_id = row["transaction_id"]
                                update_transaction_category(
                                    db, trans_id, row["category"])

                        # Refresh the data after updating
                        df_display = pd.DataFrame([{
                            'date': t.date,
                            'details': t.details,
                            'amount': t.amount,
                            'transaction_type': t.transaction_type,
                            'category': t.category,
                            'transaction_id': t.id  # Ensure transaction_id is included in refresh
                        } for t in get_all_transactions(db)])

                        credit_summary = edited_credits.groupby(
                            "category")["amount"].sum().reset_index()
                        credit_summary = credit_summary.sort_values(
                            "amount", ascending=False)

                        st.subheader("📊 Income/Transfer Summary")
                        st.dataframe(credit_summary, use_container_width=True)

                        if not credit_summary.empty:
                            fig = px.pie(credit_summary, values="amount",
                                         names="category", title="Credits by Category", hole=0.4)
                            st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.info(
                            "No credit transactions found in the selected period.")

                with tab5:
                    st.subheader("📅 Monthly Expense Report")
                    if df_display.empty:
                        st.info(
                            "No transactions to show for the selected period.")
                    else:
                        df_display["Month"] = df_display["date"].dt.to_period(
                            "M").astype(str)
                        available_months = sorted(
                            df_display["Month"].unique(), reverse=True)
                        selected_month = st.selectbox(
                            "Select a Month", available_months)

                        filtered_df = df_display[
                            (df_display["Month"] == selected_month) &
                            (df_display["transaction_type"] == "Debit")
                        ]

                        if not filtered_df.empty:
                            monthly_summary = filtered_df.groupby(
                                "category")["amount"].sum().reset_index()
                            st.write(f"### Expenses for {selected_month}")
                            st.dataframe(monthly_summary,
                                         use_container_width=True)

                            chart = px.bar(
                                monthly_summary,
                                x="category",
                                y="amount",
                                title=f"Expenses by Category - {selected_month}",
                                color="category"
                            )
                            st.plotly_chart(chart, use_container_width=True)
                        else:
                            st.info(
                                "No debit transactions found for the selected month.")
            else:
                st.info(
                    "No transactions found in the uploaded statements. Try uploading a new statement.")
except Exception as e:
    logger.error(f"Error in main display: {e}")
    st.error("An error occurred. Please try refreshing the page.")
    st.stop()

# Create FastAPI app
api = FastAPI(title="Finance Categorizer API")

# Add CORS middleware
api.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Update this with your mobile app's domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API endpoints for mobile app


@api.get("/api/transactions")
async def get_transactions(
    month: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get transactions with optional month filter"""
    try:
        transactions = get_all_transactions(db)
        if month:
            # Filter transactions by month if specified
            filtered_transactions = [
                t for t in transactions
                if t.date.strftime('%Y-%m') == month
            ]
            return filtered_transactions
        return transactions
    except Exception as e:
        logger.error(f"Error getting transactions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api.post("/api/statements/upload")
async def upload_statement(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """Handle PDF statement upload"""
    try:
        if not file.filename.endswith('.pdf'):
            raise HTTPException(
                status_code=400, detail="Only PDF files are allowed")

        content = await file.read()
        month_year = get_month_year_from_pdf(content)

        # Check if statement already exists
        if check_existing_statement(db, file.filename, month_year):
            raise HTTPException(
                status_code=400,
                detail=f"Statement for {month_year} already exists"
            )

        # Parse transactions
        transactions, opening_balance, closing_balance = parse_pdf_transactions(
            content)

        if transactions:
            # Save PDF file
            pdf_file = save_pdf_file(
                db, file.filename, content, month_year,
                opening_balance=opening_balance if opening_balance > 0 else None,
                closing_balance=closing_balance if closing_balance > 0 else None
            )

            # Auto-categorize and save transactions
            transactions = auto_categorize_transactions(db, transactions)
            for trans in transactions:
                trans['pdf_file_id'] = pdf_file.id
                save_transaction(db, trans)

            return {
                "message": f"Successfully processed {len(transactions)} transactions",
                "opening_balance": opening_balance,
                "closing_balance": closing_balance
            }
        else:
            raise HTTPException(
                status_code=400, detail="No transactions found in statement")

    except Exception as e:
        logger.error(f"Error processing statement: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api.post("/api/transactions/{transaction_id}/category")
async def update_transaction_category(
    transaction_id: int,
    category: str,
    db: Session = Depends(get_db)
):
    """Update transaction category"""
    try:
        update_transaction_category(db, transaction_id, category)
        return {"message": "Category updated successfully"}
    except Exception as e:
        logger.error(f"Error updating category: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api.post("/api/transactions/{transaction_id}/type")
async def switch_transaction_type(
    transaction_id: int,
    new_type: str,
    db: Session = Depends(get_db)
):
    """Switch transaction between debit and credit"""
    try:
        if new_type not in ["Debit", "Credit"]:
            raise HTTPException(
                status_code=400, detail="Invalid transaction type")

        transaction = db.query(Transaction).filter(
            Transaction.id == transaction_id).first()
        if transaction:
            transaction.transaction_type = new_type
            db.commit()
            return {"message": f"Switched transaction to {new_type}"}
        else:
            raise HTTPException(
                status_code=404, detail="Transaction not found")
    except Exception as e:
        logger.error(f"Error switching transaction type: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Add this at the end of the file
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(api, host="0.0.0.0", port=8000)
