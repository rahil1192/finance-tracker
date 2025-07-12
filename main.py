import fitz  # PyMuPDF
import sys
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
from typing import Dict, List, Optional, Union, Tuple
import traceback
import io
import numpy as np
from pdf2image import convert_from_bytes
import pytesseract
from PIL import Image
import cv2
from sklearn.cluster import DBSCAN
import layoutparser as lp
from models import (
    get_db, save_transaction, get_all_transactions, save_vendor_mapping,
    get_all_vendor_mappings, update_transaction_category, init_db,
    save_pdf_file, get_pdf_files, get_pdf_content, PDFFile, VendorMapping,
    clear_all_data, get_latest_statement_balance, ensure_vendor_mappings, Transaction,
    SessionLocal, update_transaction_details, CategoryMapping
)
from transaction_utils import apply_category_to_similar_transactions
from fastapi import FastAPI, HTTPException, Depends, UploadFile, File
from fastapi.security import OAuth2PasswordBearer
from fastapi.middleware.cors import CORSMiddleware
import jwt
from sqlalchemy.orm import Session

# Initialize database tables if needed (won't recreate if they exist)
init_db()


def get_latest_balances(db):
    """Get the latest balances for each account type and bank."""
    try:
        # Get all PDF files
        pdf_files = db.query(PDFFile).all()

        # Initialize latest balances by bank and type
        latest_balances = {
            "chequing": {},  # {bank: {"balance": amount, "date": date}}
            "savings": {},
            "credit": {}
        }

        for pdf in pdf_files:
            if pdf.closing_balance is None or not pdf.statement_type:
                continue

            # Convert month_year to datetime for comparison
            try:
                date = datetime.strptime(pdf.month_year, "%b_%Y")
            except:
                continue

            # Use "Unknown" as bank if None
            bank = pdf.bank if pdf.bank else "Unknown"
            statement_type = pdf.statement_type.lower()

            # Map statement type to our categories
            if statement_type == "chequing":
                category = "chequing"
            elif statement_type == "savings":
                category = "savings"
            elif statement_type == "credit card":
                category = "credit"
            else:
                continue

            # Update balance if this is the latest statement for this bank and type
            if (bank not in latest_balances[category] or
                    latest_balances[category][bank]["date"] < date):
                latest_balances[category][bank] = {
                    "balance": pdf.closing_balance,
                    "date": date
                }

        return latest_balances
    except Exception as e:
        logger.error(f"Error getting latest balances: {str(e)}")
        return {
            "chequing": {},
            "savings": {},
            "credit": {}
        }


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

# Initialize session state variables if they don't exist
if "selected_statement" not in st.session_state:
    st.session_state.selected_statement = None
if "active_tab" not in st.session_state:
    st.session_state.active_tab = "reconcile"
if "all_pdf_files" not in st.session_state:
    st.session_state.all_pdf_files = None
if "target_tab_for_navigation" not in st.session_state:
    st.session_state.target_tab_for_navigation = "expenses"
# Note: statement_target_tab will be initialized by the radio button widget

# Define a function to switch tabs


def switch_to_tab(tab_name, statement_name=None):
    """Switch to the specified tab and optionally set a selected statement."""
    if "tab_to_switch_to" not in st.session_state:
        st.session_state.tab_to_switch_to = None

    if "statement_to_select" not in st.session_state:
        st.session_state.statement_to_select = None

    st.session_state.tab_to_switch_to = tab_name
    st.session_state.statement_to_select = statement_name

    # Force a rerun to apply the changes
    st.rerun()


# Get the current tab from query parameters or session state
if "tab_to_switch_to" in st.session_state and st.session_state.tab_to_switch_to:
    current_tab = st.session_state.tab_to_switch_to
    # Clear it after using it
    st.session_state.tab_to_switch_to = None
else:
    current_tab = "reconcile"  # Default tab

# Update selected statement if provided in session state
if "statement_to_select" in st.session_state and st.session_state.statement_to_select:
    st.session_state.selected_statement = st.session_state.statement_to_select
    # Clear it after using it
    st.session_state.statement_to_select = None

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


def classify_transaction_type(details: str, amount: float = None) -> str:
    """Classify transaction type based on details and optionally amount.

    Args:
        details: The transaction description text
        amount: Optional transaction amount (positive = debit, negative = credit)

    Returns:
        "Debit" or "Credit" classification
    """
    # Normalize the text for better matching
    text = details.lower().strip()

    # Log the transaction details for debugging
    logger.info(f"Classifying transaction type for: '{text}'")

    # If amount is provided, use it as a strong signal
    if amount is not None:
        # Negative amounts are typically credits, positive are debits
        suggested_type = "Credit" if amount < 0 else "Debit"
        logger.info(f"Amount-based classification suggests: {suggested_type}")
    else:
        suggested_type = None

    # Comprehensive list of credit keywords
    credit_keywords = [
        "rewards", "rebate", "refund", "e-transfer reclaim", "e-transfer paydirect", "deposit", "credit", "payment received", "payment thank you",
        "interest", "direct deposit", "salary", "payroll", "income", "transfer in",
        "reimbursement", "cashback", "dividend", "tax return", "reversal"
    ]

    # Comprehensive list of debit keywords
    debit_keywords = [
        "retail", "debit", "purchase", "fulfill request", "e-transfer sent", "internet transfer",
        "bill", "charge", "petro", "service", "withdrawal", "payment to",
        "payment sent", "fee", "subscription", "transfer out", "atm", "cash",
        "pos purchase", "online purchase", "insurance", "mortgage", "rent",
        "utility", "phone", "internet", "cable", "grocery", "restaurant", "dining"
    ]

    # Check for credit keywords
    credit_matches = [k for k in credit_keywords if k in text]
    if credit_matches:
        logger.info(f"Credit keywords found: {credit_matches}")
        # If amount suggests debit but keywords strongly suggest credit, log the conflict
        if suggested_type == "Debit":
            logger.warning(
                f"Keyword-amount conflict: Keywords suggest Credit but amount suggests Debit for '{text}'")
        return "Credit"

    # Check for debit keywords
    debit_matches = [k for k in debit_keywords if k in text]
    if debit_matches:
        logger.info(f"Debit keywords found: {debit_matches}")
        # If amount suggests credit but keywords strongly suggest debit, log the conflict
        if suggested_type == "Credit":
            logger.warning(
                f"Keyword-amount conflict: Keywords suggest Debit but amount suggests Credit for '{text}'")
        return "Debit"

    # If no keywords match but we have an amount-based suggestion, use that
    if suggested_type:
        logger.info(
            f"No keywords matched, using amount-based classification: {suggested_type}")
        return suggested_type

    # Default fallback - analyze the transaction pattern
    # Most transactions are debits (expenses) unless proven otherwise
    logger.info(f"No clear classification, defaulting to Debit for: '{text}'")
    return "Debit"


def get_month_year_from_pdf(pdf_content: bytes) -> str:
    """Extract month and year from PDF content."""
    try:
        with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if not text:
                    continue
                normalized_text = text.replace('\n', ' ').replace(' ', '')

                # Try to match the format: STATEMENT DATE: February 06, 2025
                match = re.search(
                    r"STATEMENTDATE:([A-Za-z]+)\d{1,2},(\d{4})", normalized_text)
                if match:
                    month, year = match.groups()
                    # Shorten month to 3 letters like "Feb_2025"
                    return f"{month[:3]}_{year}"

                # Fallback: search for any "MMM dd, yyyy" style date
                date_match = re.search(
                    r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},\s+(\d{4})", text)
                if date_match:
                    month, year = date_match.groups()
                    return f"{month}_{year}"

        return "Unknown_Date"
    except Exception as e:
        logger.error(f"Error extracting month from PDF: {e}")
        return datetime.now().strftime("%b_%Y")


def check_poppler_installation():
    """Check if poppler is properly installed and configured."""
    try:
        from pdf2image.exceptions import PDFInfoNotInstalledError
        import os
        import sys

        # Common poppler installation paths
        poppler_paths = [
            r"C:\Program Files\poppler\bin",
            r"C:\Program Files (x86)\poppler\bin",
            r"C:\poppler\bin",
            os.path.join(os.path.expanduser("~"), "poppler", "bin"),
            # Check Python installation directory
            os.path.join(os.path.dirname(sys.executable), "poppler", "bin")
        ]

        # Check if poppler is already in PATH
        if "poppler" in os.environ["PATH"].lower():
            st.success("✅ Poppler found in PATH")
            return True

        # Try to find poppler in common locations
        for path in poppler_paths:
            if os.path.exists(path):
                # Add to PATH if not already there
                if path not in os.environ["PATH"]:
                    os.environ["PATH"] = path + os.pathsep + os.environ["PATH"]
                st.success(f"✅ Found and added poppler to PATH: {path}")
                return True

        # If we get here, poppler wasn't found
        st.error("""
        ❌ Poppler is not installed or not found. Please follow these steps:

        1. Download Poppler for Windows from:
           https://github.com/oschwartz10612/poppler-windows/releases/

        2. Extract the downloaded zip file to one of these locations:
           - C:\\Program Files\\poppler
           - C:\\Program Files (x86)\\poppler
           - C:\\poppler
           - Your user directory\\poppler

        3. Add the bin directory to your PATH:
           a) Open System Properties (Windows + Pause/Break)
           b) Click 'Advanced system settings'
           c) Click 'Environment Variables'
           d) Under 'System Variables', find and select 'Path'
           e) Click 'Edit'
           f) Click 'New'
           g) Add the path to the poppler bin directory (e.g., 'C:\\Program Files\\poppler\\bin')
           h) Click 'OK' on all windows

        4. Restart your computer

        Or run these commands in PowerShell as Administrator:
        ```
        $url = "https://github.com/oschwartz10612/poppler-windows/releases/download/v23.07.0-0/Release-23.07.0-0.zip"
        $output = "$env:TEMP\\poppler.zip"
        Invoke-WebRequest -Uri $url -OutFile $output
        Expand-Archive -Path $output -DestinationPath "C:\\Program Files\\poppler" -Force
        $path = [Environment]::GetEnvironmentVariable("Path", "Machine")
        [Environment]::SetEnvironmentVariable("Path", $path + ";C:\\Program Files\\poppler\\bin", "Machine")
        ```
        """)
        return False

    except Exception as e:
        st.error(f"Error checking poppler installation: {str(e)}")
        logger.error(
            f"Poppler check error: {str(e)}\n{traceback.format_exc()}")
        return False


def convert_pdf_to_images(pdf_content: bytes, first_page: int = 1, last_page: int = 1) -> List[np.ndarray]:
    """Convert PDF pages to images with better error handling."""
    try:
        # Check poppler installation first
        if not check_poppler_installation():
            st.error("Cannot convert PDF to images without poppler installed.")
            return []

        # Try conversion with pdf2image
        images = convert_from_bytes(
            pdf_content,
            dpi=300,
            first_page=first_page,
            last_page=last_page,
            poppler_path=None  # Will use PATH
        )
        return [np.array(img) for img in images]

    except Exception as e:
        st.error(f"Error converting PDF to images: {str(e)}")
        logger.error(
            f"PDF conversion error: {str(e)}\n{traceback.format_exc()}")
        return []


def detect_statement_format(first_page_text: str) -> tuple[str, str]:
    """Detects bank name and statement type from merged PDF text."""
    bank_name = "Unknown Bank"
    statement_type = "Unknown Type"

    # Clean the text
    text = first_page_text.lower().replace(" ", "").replace("\n", "")

    # TD detection
    if "tdcanadatrust" in text or "tdbank" in text:
        bank_name = "TD"
        if "statementdate" in text and "previousstatement" in text:
            statement_type = "Credit Card"
        elif "openingbalance" in text and "closingbalance" in text:
            statement_type = "Chequing or Savings"

    # RBC detection
    elif "royalbankofcanada" in text or "rbcroyalbank" in text:
        bank_name = "RBC"
        if "accountsummary" in text and "openingbalance" in text:
            statement_type = "Chequing or Savings"
        elif "visaaccount" in text:
            statement_type = "Credit Card"

    # CIBC detection
    elif "cibc" in text:
        bank_name = "CIBC"
        if "accountsummary" in text and "availablecredit" in text:
            statement_type = "Credit Card"
        elif "accountstatement" in text or "depositsandwithdrawals" in text:
            statement_type = "Chequing or Savings"

    # BMO detection
    elif "bankofmontreal" in text or "bmo" in text:
        bank_name = "BMO"
        if "bmomastercard" in text or "creditlimit" in text:
            statement_type = "Credit Card"
        elif "accountsummary" in text or "chequingaccount" in text:
            statement_type = "Chequing or Savings"

    return bank_name, statement_type


def parse_td_credit_card_statement(pdf_content: bytes) -> tuple[list[dict], float, float]:
    """Robust TD Credit Card parser with fixed amount parsing and year rollover handling."""
    data = []
    opening_balance = 0.0
    closing_balance = 0.0
    buffer_line = ""

    try:
        with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
            lines = []
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    lines.extend(text.splitlines())

            # Flattened string for balance lookups
            raw_text = ''.join(line.lower().replace(
                " ", "").replace("\n", "") for line in lines)

            # Extract statement year and month
            statement_year = pd.Timestamp.now().year
            statement_month = "jan"
            statement_match = re.search(
                r"statementdate:([a-z]+)(\d{1,2}),(\d{4})", raw_text)
            if statement_match:
                statement_month = statement_match.group(1)
                statement_year = int(statement_match.group(3))

            # --- OPENING BALANCE ---
            opening_match = re.search(
                r"previousstatementbalance[:\s]?\$(-?[\d,]+\.\d{2})", raw_text)
            if opening_match:
                opening_balance = float(
                    opening_match.group(1).replace(",", ""))
            else:
                alt_opening = re.search(
                    r"payment-thankyou-\$(-?[\d,]+\.\d{2})", raw_text)
                if alt_opening:
                    opening_balance = float(
                        alt_opening.group(1).replace(",", ""))

            # --- CLOSING BALANCE ---
            closing_match = re.search(
                r"newbalance[:\s]?\$(-?[\d,]+\.\d{2})", raw_text)
            if closing_match:
                closing_balance = float(
                    closing_match.group(1).replace(",", ""))
            else:
                closing_balance = 0.0

            # --- TRANSACTION PARSING ---
            month_pattern = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)"

            month_to_num = {'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5,
                            'jun': 6, 'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12}
            statement_month_num = month_to_num.get(statement_month, 1)
            logger.info(
                f"TD Credit Card: Detected statement_month={statement_month}, statement_year={statement_year}")
            for line in lines:
                line = line.strip().lower()

                if not line or "statement" in line or "summary" in line or "balance" in line:
                    continue

                # Match transaction line with amount like $2,397.36 or $-2,397.36
                trans_match = re.match(
                    rf"({month_pattern})(\d{{1,2}})\s*({month_pattern})(\d{{1,2}})\s+(.*?)(-?)\$(\d[\d,]+\.\d{{2}})", line
                )

                if trans_match:
                    post_month, post_day, trans_month, trans_day, desc, negative_sign, amount_text = trans_match.groups()

                    txn_month = post_month
                    txn_day = post_day
                    txn_month_num = month_to_num.get(txn_month, 1)
                    if txn_month_num > statement_month_num:
                        txn_year = statement_year - 1
                    else:
                        txn_year = statement_year
                    date_str = f"{txn_month} {txn_day} {txn_year}"
                    logger.info(
                        f"TD Credit Card: Parsed transaction line='{line}', assigned date={date_str}")

                    # Clean amount string
                    amount_str = f"-{amount_text}" if negative_sign == "-" else amount_text
                    amount_signed = float(amount_str.replace(",", ""))
                    amount = abs(amount_signed)

                    # Use both amount sign and transaction details to determine type
                    # For credit cards, positive amounts are typically debits (charges)
                    # But also check the description for additional clues
                    trans_type = classify_transaction_type(
                        desc.strip(), amount_signed)

                    data.append({
                        "date": pd.to_datetime(date_str, errors='coerce'),
                        "details": desc.strip(),
                        "amount": amount,
                        "transaction_type": trans_type,
                        "category": "Uncategorized",
                        "bank": "TD",
                        "statement_type": "Credit Card"
                    })

                    buffer_line = ""

                else:
                    # If the line starts like a new transaction, it's just a failed match — skip it
                    if re.match(r"^(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\d{1,2}", line):
                        tx = try_parse_fallback(
                            line, statement_month, statement_year)
                        if tx:
                            data.append(tx)
                            continue  # Parsed successfully
        # Otherwise, it's probably a continuation of the previous description
                    if data:
                        data[-1]["details"] += " " + line.strip()
                    else:
                        buffer_line += " " + line.strip()

    except Exception as e:
        import streamlit as st
        st.error(f"Error parsing TD Credit Card: {str(e)}")

    return data, opening_balance, closing_balance


def looks_like_transaction_start(line: str) -> bool:
    return re.match(r"^(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\d{1,2}", line)


def try_parse_fallback(line: str, statement_month: str, statement_year: int):
    """Try to parse line using looser fallback pattern."""
    month_pattern = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)"
    fallback_match = re.match(
        rf"({month_pattern}\d{{1,2}})\s*({month_pattern}\d{{1,2}})\s+(.+?)\s*\$(-?[\d,]+\.\d{{2}})", line
    )
    if fallback_match:
        post_date_str, trans_date_str, desc, amt_str = fallback_match.groups()
        txn_month = post_date_str[:3]
        txn_day = post_date_str[3:]
        month_to_num = {'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5,
                        'jun': 6, 'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12}
        txn_month_num = month_to_num.get(txn_month, 1)
        statement_month_num = month_to_num.get(statement_month, 1)
        if txn_month_num > statement_month_num:
            txn_year = statement_year - 1
        else:
            txn_year = statement_year
        date_str = f"{txn_month} {txn_day} {txn_year}"
        amount_signed = float(amt_str.replace(",", ""))
        amount = abs(amount_signed)
        trans_type = classify_transaction_type(desc.strip(), amount_signed)
        return {
            "date": pd.to_datetime(date_str, errors="coerce"),
            "details": desc.strip(),
            "amount": amount,
            "transaction_type": trans_type,
            "category": "Uncategorized",
            "bank": "TD",
            "statement_type": "Credit Card"
        }
    return None


def parse_td_chequing_statement(pdf_content: bytes) -> tuple[list[dict], float, float]:
    """Parse TD Bank Chequing PDF transactions."""
    data = []
    opening_balance = 0.0
    closing_balance = 0.0
    try:
        current_date = None
        with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
            first_page_text = pdf.pages[0].extract_text()

            # Detect bank and year
            bank_name, _ = detect_statement_format(first_page_text)
            year_match = re.search(
                r"STATEMENT DATE:\s+[A-Za-z]+\s+\d{1,2},\s+(\d{4})", first_page_text)
            statement_year = int(year_match.group(
                1)) if year_match else pd.Timestamp.now().year

            for page in pdf.pages:
                text = page.extract_text()
                lines = text.split("\n")

                logger.info("Searching all lines for opening balance...")

                for line in lines:
                    original_line = line
                    line = line.strip()

                    if "opening balance" in line.lower():
                        logger.info(
                            f"Found potential opening balance line: '{line}'")
                        try:
                            amount_match = re.search(
                                r'(\d{1,3}(?:,\d{3})*\.\d{2})', line)
                            if amount_match:
                                balance_text = amount_match.group(1)
                                opening_balance = float(
                                    balance_text.replace(",", ""))
                                logger.info(
                                    f"Successfully extracted opening balance: ${opening_balance:,.2f}")
                                break
                        except ValueError as e:
                            logger.error(
                                f"Error parsing opening balance from '{original_line}': {e}")
                            continue

                for line in lines:
                    line = line.strip()
                    if not line:
                        continue

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
                            trans_type = classify_transaction_type(
                                details, amount)
                            data.append({
                                "date": pd.to_datetime(current_date + f" {statement_year}", errors='coerce'),
                                "details": details,
                                "amount": amount,
                                "transaction_type": trans_type,
                                "category": "Uncategorized",
                                "bank": bank_name,
                                "statement_type": "Chequing"
                            })
                    else:
                        if data:
                            data[-1]["details"] += " " + line

        logger.info(f"Extracted {len(data)} transactions")

    except Exception as e:
        logger.error(f"Error parsing PDF: {str(e)}\n{traceback.format_exc()}")
        st.error("Error parsing TD Chequing PDF file.")

    return data, opening_balance, closing_balance


def preprocess_image(image: Image.Image) -> np.ndarray:
    """Preprocess image for better OCR results."""
    # Convert to grayscale
    gray = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2GRAY)

    # Apply adaptive thresholding
    thresh = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, 11, 2
    )

    # Denoise
    denoised = cv2.fastNlMeansDenoising(thresh)

    return denoised


def detect_table_regions(image: np.ndarray) -> List[Tuple[int, int, int, int]]:
    """Detect table regions in the image using layout analysis."""
    # Initialize layout parser
    model = lp.Detectron2LayoutModel(
        'lp://PubLayNet/mask_rcnn_X_101_32x8d_FPN_3x/config',
        extra_config=["MODEL.ROI_HEADS.SCORE_THRESH_TEST", 0.8],
        label_map={0: "Text", 1: "Title", 2: "List", 3: "Table", 4: "Figure"}
    )

    # Detect layouts
    layouts = model.detect(image)

    # Filter for table regions
    table_regions = []
    for layout in layouts:
        if layout.type == "Table":
            x1, y1, x2, y2 = layout.coordinates
            table_regions.append((int(x1), int(y1), int(x2), int(y2)))

    return table_regions


def extract_text_from_region(image: np.ndarray, region: Tuple[int, int, int, int]) -> str:
    """Extract text from a specific region using OCR."""
    x1, y1, x2, y2 = region
    roi = image[y1:y2, x1:x2]

    # Run OCR on the region
    text = pytesseract.image_to_string(
        roi,
        config='--psm 6'  # Assume uniform block of text
    )

    return text.strip()


def cluster_transactions(text_lines: List[str]) -> List[List[str]]:
    """Cluster text lines into transactions using DBSCAN."""
    # Convert lines to feature vectors (simple length-based for now)
    X = np.array([[len(line)] for line in text_lines])

    # Cluster using DBSCAN
    clustering = DBSCAN(eps=50, min_samples=1).fit(X)

    # Group lines by cluster
    clusters = {}
    for i, label in enumerate(clustering.labels_):
        if label not in clusters:
            clusters[label] = []
        clusters[label].append(text_lines[i])

    return list(clusters.values())


def advanced_ocr_extract(pdf_content: bytes) -> Tuple[List[Dict], float, float]:
    """Advanced OCR extraction with layout analysis."""
    data = []
    opening_balance = 0.0
    closing_balance = 0.0

    try:
        # Convert PDF to images
        images = convert_from_bytes(pdf_content, dpi=300)

        for page_num, image in enumerate(images, 1):
            # Preprocess image
            processed_image = preprocess_image(image)

            # Detect table regions
            table_regions = detect_table_regions(processed_image)

            if not table_regions:
                st.warning(f"No table regions detected on page {page_num}")
                continue

            # Extract text from each table region
            for region in table_regions:
                text = extract_text_from_region(processed_image, region)
                lines = [line.strip()
                         for line in text.split('\n') if line.strip()]

                # Cluster lines into transactions
                transaction_clusters = cluster_transactions(lines)

                # Process each transaction cluster
                for cluster in transaction_clusters:
                    # Join cluster lines and parse transaction
                    transaction_text = ' '.join(cluster)
                    transaction = parse_transaction_text(transaction_text)
                    if transaction:
                        data.append(transaction)

            # Try to extract balances from the page
            if page_num == 1:  # Usually on first page
                opening_balance, closing_balance = ocr_extract_balances(
                    pdf_content)

    except Exception as e:
        st.error(f"Advanced OCR extraction failed: {str(e)}")
        logger.error(f"Advanced OCR error: {str(e)}\n{traceback.format_exc()}")

    return data, opening_balance, closing_balance


def parse_transaction_text(text: str) -> Optional[Dict]:
    """Parse transaction text into structured data."""
    # Enhanced regex pattern for transaction parsing
    pattern = r"""
        (?P<date>\d{2}/\d{2}/\d{4})  # Date
        \s+
        (?P<description>.*?)          # Description
        \s+
        (?P<amount>-?\$[\d,]+\.\d{2}) # Amount
    """

    match = re.search(pattern, text, re.VERBOSE)
    if match:
        date_str = match.group('date')
        description = match.group('description').strip()
        amount_str = match.group('amount').replace('$', '').replace(',', '')

        amount = float(amount_str)
        trans_type = "Debit" if amount > 0 else "Credit"

        return {
            "date": pd.to_datetime(date_str),
            "details": description,
            "amount": abs(amount),
            "transaction_type": trans_type,
            "category": "Uncategorized",
            "bank": "TD",  # This should be detected from the statement
            "statement_type": "Credit Card"  # This should be detected from the statement
        }

    return None


def preprocess_balance_region(image: np.ndarray) -> np.ndarray:
    """Special preprocessing for balance regions."""
    # Convert to grayscale
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)

    # Apply adaptive thresholding with larger block size
    thresh = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, 21, 11
    )

    # Apply morphological operations to clean up
    kernel = np.ones((3, 3), np.uint8)
    cleaned = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)

    return cleaned


def find_balance_regions(image: np.ndarray) -> List[Tuple[int, int, int, int]]:
    """Find regions likely to contain balance information."""
    # Convert to grayscale
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)

    # Apply edge detection
    edges = cv2.Canny(gray, 50, 150)

    # Find contours
    contours, _ = cv2.findContours(
        edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    balance_regions = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        # Filter for regions that might contain balance information
        if 100 < w < 500 and 20 < h < 100:  # Typical balance line dimensions
            balance_regions.append((x, y, x + w, y + h))

    return balance_regions


def check_tesseract_installation():
    """Check if Tesseract is properly installed and configured."""
    try:
        import os

        # Define default Tesseract path
        default_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

        # First try the default installation path
        if os.path.exists(default_path):
            pytesseract.pytesseract.tesseract_cmd = default_path
            st.success(
                f"✅ Found Tesseract at default location: {default_path}")
            return True

        # Try alternative paths
        alt_paths = [
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            os.path.join(os.path.expanduser("~"), "AppData", "Local",
                         "Programs", "Tesseract-OCR", "tesseract.exe")
        ]

        for path in alt_paths:
            if os.path.exists(path):
                pytesseract.pytesseract.tesseract_cmd = path
                st.success(f"✅ Found Tesseract at: {path}")
                return True

        # If we get here, Tesseract wasn't found
        st.error("""
        ❌ Tesseract OCR is not installed or not found. Please follow these steps:

        1. Download Tesseract installer from:
           https://github.com/UB-Mannheim/tesseract/wiki

        2. Install to the default location:
           C:\\Program Files\\Tesseract-OCR

        3. Add to PATH:
           a) Open System Properties (Windows + Pause/Break)
           b) Click 'Advanced system settings'
           c) Click 'Environment Variables'
           d) Under 'System Variables', find and select 'Path'
           e) Click 'Edit'
           f) Click 'New'
           g) Add 'C:\\Program Files\\Tesseract-OCR'
           h) Click 'OK' on all windows

        4. Restart your computer

        Alternative: Run in PowerShell as Administrator:
        ```
        choco install tesseract
        ```
        """)
        return False

    except Exception as e:
        st.error(f"Error checking Tesseract installation: {str(e)}")
        logger.error(
            f"Tesseract check error: {str(e)}\n{traceback.format_exc()}")
        return False


def ocr_extract_balances(pdf_content: bytes) -> Tuple[float, float]:
    """Enhanced OCR extraction for opening and closing balances with multiple attempts."""
    opening_balance = 0.0
    closing_balance = 0.0

    try:
        # Check and configure Tesseract
        if not check_tesseract_installation():
            st.error("Cannot perform OCR without Tesseract properly configured.")
            return 0.0, 0.0

        # Verify Tesseract is working
        try:
            version = pytesseract.get_tesseract_version()
            st.info(f"Using Tesseract version: {version}")
        except Exception as e:
            st.error(f"Error verifying Tesseract: {str(e)}")
            return 0.0, 0.0

        # Check poppler installation
        if not check_poppler_installation():
            st.error("Cannot convert PDF to images without poppler installed.")
            return 0.0, 0.0

        # Convert first two pages to images with better error handling
        images = convert_pdf_to_images(pdf_content, first_page=1, last_page=2)
        if not images:
            st.warning(
                "Could not convert PDF to images. OCR balance extraction skipped.")
            return 0.0, 0.0

        for page_num, image_np in enumerate(images, 1):
            # Try different OCR configurations
            configs = [
                '--psm 6 -c tessedit_char_whitelist=0123456789,.$',  # Strict number mode
                '--psm 6',  # Assume uniform block of text
                '--psm 3',  # Auto page segmentation
                '--psm 11'  # Sparse text with OSD
            ]

            for config in configs:
                # Try full page first
                processed_full = preprocess_balance_region(image_np)
                text = pytesseract.image_to_string(
                    processed_full, config=config)

                # Look for balance patterns
                lines = text.lower().split('\n')
                for line in lines:
                    # Opening balance patterns
                    if any(pattern in line for pattern in [
                        'opening balance', 'previous balance', 'beginning balance',
                        'balance forward', 'previous statement'
                    ]):
                        matches = re.findall(r'\$?\s*([\d,]+\.\d{2})', line)
                        if matches:
                            potential_balance = float(
                                matches[0].replace(',', ''))
                            if 0 < potential_balance < 1000000:  # Sanity check
                                opening_balance = potential_balance
                                st.info(
                                    f"🔍 OCR found opening balance on page {page_num}: ${opening_balance:,.2f}")

                    # Closing balance patterns
                    if any(pattern in line for pattern in [
                        'closing balance', 'new balance', 'ending balance',
                        'current balance', 'balance due', 'statement balance'
                    ]):
                        matches = re.findall(r'\$?\s*([\d,]+\.\d{2})', line)
                        if matches:
                            potential_balance = float(
                                matches[0].replace(',', ''))
                            if 0 < potential_balance < 1000000:  # Sanity check
                                closing_balance = potential_balance
                                st.info(
                                    f"🔍 OCR found closing balance on page {page_num}: ${closing_balance:,.2f}")

                # If we found both balances, we can stop
                if opening_balance > 0 and closing_balance > 0:
                    st.success(
                        "✅ Successfully extracted both balances using OCR!")
                    return opening_balance, closing_balance

                # Try specific regions if full page didn't work
                balance_regions = find_balance_regions(image_np)
                for region in balance_regions:
                    x1, y1, x2, y2 = region
                    roi = image_np[y1:y2, x1:x2]
                    processed_roi = preprocess_balance_region(roi)

                    text = pytesseract.image_to_string(
                        processed_roi, config=config)
                    lines = text.lower().split('\n')

                    for line in lines:
                        # Try to find balances in the region
                        if opening_balance == 0 and any(pattern in line for pattern in [
                            'opening', 'previous', 'beginning', 'forward'
                        ]):
                            matches = re.findall(
                                r'\$?\s*([\d,]+\.\d{2})', line)
                            if matches:
                                potential_balance = float(
                                    matches[0].replace(',', ''))
                                if 0 < potential_balance < 1000000:
                                    opening_balance = potential_balance
                                    st.info(
                                        f"🔍 OCR found opening balance in region: ${opening_balance:,.2f}")

                        if closing_balance == 0 and any(pattern in line for pattern in [
                            'closing', 'new', 'ending', 'due'
                        ]):
                            matches = re.findall(
                                r'\$?\s*([\d,]+\.\d{2})', line)
                            if matches:
                                potential_balance = float(
                                    matches[0].replace(',', ''))
                                if 0 < potential_balance < 1000000:
                                    closing_balance = potential_balance
                                    st.info(
                                        f"🔍 OCR found closing balance in region: ${closing_balance:,.2f}")

        if opening_balance == 0 or closing_balance == 0:
            st.warning(
                "⚠️ Could not find all balances using OCR. Some values may be missing.")

    except Exception as e:
        st.warning(f"OCR balance extraction failed: {str(e)}")
        logger.error(f"OCR balance error: {str(e)}\n{traceback.format_exc()}")

    return opening_balance, closing_balance


def parse_pdf_transactions(pdf_content: bytes) -> Tuple[List[Dict], float, float]:
    """Main dispatcher that compares balances from OCR and regular parsing."""
    try:
        # Get balances from OCR
        ocr_opening_balance, ocr_closing_balance = ocr_extract_balances(
            pdf_content)
        logger.info(
            f"OCR Balances - Opening: ${ocr_opening_balance:,.2f}, Closing: ${ocr_closing_balance:,.2f}")

        # Parse transactions and get balances from regular parsing
        with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
            first_page_text = pdf.pages[0].extract_text()
            bank_name, statement_type = detect_statement_format(
                first_page_text)
            logger.info(
                f"Detected Bank: {bank_name}, Statement Type: {statement_type}")

            if bank_name == "TD" and statement_type == "Credit Card":
                transactions, reg_opening_balance, reg_closing_balance = parse_td_credit_card_statement(
                    pdf_content)
            elif bank_name == "CIBC" and statement_type == "Chequing or Savings":
                transactions, reg_opening_balance, reg_closing_balance = parse_td_chequing_statement(
                    pdf_content)
            else:
                # Try advanced OCR for transactions
                st.warning("Using advanced OCR for transaction extraction...")
                transactions, reg_opening_balance, reg_closing_balance = advanced_ocr_extract(
                    pdf_content)

            # Add bank name to all transactions
            for trans in transactions:
                trans['bank'] = bank_name
                trans['statement_type'] = statement_type

            logger.info(
                f"Regular Parsing Balances - Opening: ${reg_opening_balance:,.2f}, Closing: ${reg_closing_balance:,.2f}")

            # Compare and select the most reliable balances
            opening_balance = select_most_reliable_balance(
                ocr_opening_balance, reg_opening_balance)
            closing_balance = select_most_reliable_balance(
                ocr_closing_balance, reg_closing_balance)

            # Log the selected balances
            if opening_balance > 0:
                st.info(f"Selected Opening Balance: ${opening_balance:,.2f}")
                if abs(ocr_opening_balance - reg_opening_balance) > 0.01 and ocr_opening_balance > 0 and reg_opening_balance > 0:
                    st.warning(
                        f"Opening balance discrepancy detected - OCR: ${ocr_opening_balance:,.2f}, Regular: ${reg_opening_balance:,.2f}")

            if closing_balance > 0:
                st.info(f"Selected Closing Balance: ${closing_balance:,.2f}")
                if abs(ocr_closing_balance - reg_closing_balance) > 0.01 and ocr_closing_balance > 0 and reg_closing_balance > 0:
                    st.warning(
                        f"Closing balance discrepancy detected - OCR: ${ocr_closing_balance:,.2f}, Regular: ${reg_closing_balance:,.2f}")

            return transactions, opening_balance, closing_balance, bank_name, statement_type

    except Exception as e:
        logger.error(f"Error in parse_pdf_transactions: {str(e)}")
        st.error("Error parsing PDF file. Please check the file format.")
        return [], 0.0, 0.0, "Unknown", "Unknown"


def select_most_reliable_balance(ocr_balance: float, regular_balance: float) -> float:
    """Select the most reliable balance between OCR and regular parsing results."""
    # If both values are present and equal (within a small tolerance)
    if ocr_balance > 0 and regular_balance > 0:
        if abs(ocr_balance - regular_balance) < 0.01:  # 1 cent tolerance
            return ocr_balance  # They're effectively equal, return either
        else:
            # If they differ, prefer the regular parsing method as it's usually more reliable
            # But log the discrepancy for debugging
            logger.info(
                f"Balance discrepancy - OCR: ${ocr_balance:,.2f}, Regular: ${regular_balance:,.2f}")
            return regular_balance

    # If only one value is present, use that
    if ocr_balance > 0:
        return ocr_balance
    if regular_balance > 0:
        return regular_balance

    # If neither value is present
    return 0.0


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

    # Debug vendor map
    logger.info(f"Vendor map has {len(vendor_map)} entries")

    for vendor_substring, category in vendor_map.items():
        if vendor_substring == "__custom_categories__":
            continue

        if not isinstance(vendor_substring, str) or not isinstance(category, str):
            logger.warning(
                f"Invalid mapping: {vendor_substring} -> {category}")
            continue

        # Normalize the vendor substring
        vendor_substring = ' '.join(vendor_substring.lower().split())

        # Check if vendor substring is in the transaction details
        if vendor_substring in details:
            logger.info(f"Found match: '{vendor_substring}' -> '{category}'")
            return category

        # Check if vendor substring is in the main text (without numbers and special chars)
        if vendor_substring in main_text:
            logger.info(
                f"Found match in main text: '{vendor_substring}' -> '{category}'")
            return category

        # Check if any word in vendor substring is in the transaction details
        if any(word in details.split() for word in vendor_substring.split() if len(word) > 3):
            logger.info(
                f"Found partial match: '{vendor_substring}' -> '{category}'")
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

    # Debug output of vendor mappings
    logger.info(
        f"Auto-categorizing {len(transactions)} transactions with {len(vendor_map)} vendor mappings")
    for vendor, category in list(vendor_map.items())[:5]:
        logger.info(f"Sample mapping: '{vendor}' -> '{category}'")

    # Process each transaction
    for trans in transactions:
        # Get the original category if it exists
        original_category = trans.get('category', 'Uncategorized')

        # Apply categorization
        trans['category'] = categorize_transaction(
            trans['details'], vendor_map)

        # Log if category changed
        if trans['category'] != original_category:
            logger.info(
                f"Auto-categorized: '{trans['details']}' from '{original_category}' to '{trans['category']}'")

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
if "uploaded_files_key" not in st.session_state:
    st.session_state.uploaded_files_key = 0
if "vendor_mappings_imported" not in st.session_state:
    st.session_state.vendor_mappings_imported = False
if "show_expense_date_filter" not in st.session_state:
    st.session_state.show_expense_date_filter = False
if "show_payments_date_filter" not in st.session_state:
    st.session_state.show_payments_date_filter = False
if "selected_statement_type" not in st.session_state:
    st.session_state.selected_statement_type = None

# Initialize session state for transaction editing
if "previous_debits_df" not in st.session_state:
    st.session_state.previous_debits_df = pd.DataFrame()
if "previous_credits_df" not in st.session_state:
    st.session_state.previous_credits_df = pd.DataFrame()
if "current_debits_df" not in st.session_state:
    st.session_state.current_debits_df = pd.DataFrame()
if "current_credits_df" not in st.session_state:
    st.session_state.current_credits_df = pd.DataFrame()

# Initialize database tables if needed (won't recreate if they exist)
init_db()

# Get database session
db = next(get_db())

# Always load vendor mappings from database at startup
try:
    vendor_mappings = get_all_vendor_mappings(db)
    st.session_state.vendor_mappings = vendor_mappings
    logger.info(f"Loaded {len(vendor_mappings)} vendor mappings from database")
except Exception as e:
    logger.error(f"Error loading vendor mappings: {str(e)}")
    st.session_state.vendor_mappings = {}

# Main UI
st.title("💰 Finance Statement Categorizer")

# Add helpful tooltips and documentation
with st.sidebar:
    st.markdown("""
    ### 📚 Quick Guide
    1. Upload your bank statements (PDF)
    2. Categorize transactions
    3. View summaries and reports
    """)

    st.divider()
    # Removed "Filter Options" subheader

# Get all PDF files for statement filter
all_pdf_files = db.query(PDFFile).order_by(PDFFile.upload_date.desc()).all()
if all_pdf_files:
    # Create a list of statement options with file name and month/year
    statement_options = ["All Statements"] + [
        f"{pdf.original_filename} ({pdf.month_year})" for pdf in all_pdf_files
    ]

    # Initialize session state for statement filter - always set to "All Statements"
    if "selected_statements" not in st.session_state:
        st.session_state.selected_statements = ["All Statements"]
    else:
        # Keep "All Statements" as the default selection
        st.session_state.selected_statements = ["All Statements"]

    # No UI element for statement selection, just use the session state value
    selected_statements = st.session_state.selected_statements

# Get available months from the database
transactions = get_all_transactions(db)
if transactions:
    # We now always use "All Statements", so no need to filter by selected statements
    # Just create the DataFrame with all transactions
    df = pd.DataFrame([{
        'date': t.date,
        'details': t.details,
        'amount': t.amount,
        'transaction_type': t.transaction_type,
        'category': t.category,
        'transaction_id': t.id,
        # Ensure this is present
        'pdf_file_id': getattr(t, "pdf_file_id", None)
    } for t in transactions])

    # Create MonthYear column for filtering
    df['MonthYear'] = df['date'].dt.strftime('%Y-%m')
    available_months = sorted(df['MonthYear'].unique(), reverse=True)
else:
    df = pd.DataFrame()
    available_months = []

# Get all unique account holders
all_accounts = sorted({pdf.account for pdf in all_pdf_files if pdf.account})

# Initialize account filter in session state if not exists
if "selected_account" not in st.session_state:
    st.session_state.selected_account = "All Accounts"
else:
    # Always set to "All Accounts" since we're removing the dropdown
    st.session_state.selected_account = "All Accounts"

# Remove account filter from sidebar and initialize with empty list
selected_months = []

# Add new statements section
st.sidebar.divider()
st.sidebar.subheader("➕ Add New Statements")

# Initialize necessary session state variables
if "upload_account_holder" not in st.session_state:
    st.session_state.upload_account_holder = None
if "selected_statement_type" not in st.session_state:
    st.session_state.selected_statement_type = None

# Fixed account holders
account_holders = ["Apeksha", "Rahil Dinesh Shah"]

# Account holder selection dropdown - simplified to just use the fixed options
selected_upload_account = st.sidebar.selectbox(
    "Select Account Holder",
    options=account_holders,
    index=0,  # Default to first account (Apeksha)
    key="upload_account_selector",
    help="Select the account holder for this statement"
)
st.session_state.upload_account_holder = selected_upload_account

# Show statement type selection
if st.session_state.upload_account_holder:
    # Add statement type dropdown
    statement_type_options = ["Credit Card", "Chequing", "Savings"]
    selected_statement_type = st.sidebar.selectbox(
        "Select Statement Type",
        options=statement_type_options,
        index=0,  # Default to Credit Card
        key="statement_type_selector",
        help="Select the type of statement you are uploading"
    )
    st.session_state.selected_statement_type = selected_statement_type

    # Show file uploader
    uploaded_files = st.sidebar.file_uploader(
        f"Upload {st.session_state.selected_statement_type} PDFs",
        type=CONFIG['processing']['supported_file_types'],
        accept_multiple_files=True,
        help=f"Upload one or more {st.session_state.selected_statement_type} statement PDFs",
        key=f"file_uploader_{st.session_state.uploaded_files_key}"
    )
else:
    # This should not happen with the fixed dropdown
    uploaded_files = None
    st.session_state.selected_statement_type = None


def fix_td_statement_dates(db):
    """Fix month/year for TD bank statements."""
    try:
        updated = 0
        for pdf in db.query(PDFFile).filter(PDFFile.bank == 'TD').all():
            # Get the PDF content
            pdf_content = get_pdf_content(db, pdf.id)
            if pdf_content:
                # Extract text from first page
                with pdfplumber.open(io.BytesIO(pdf_content)) as pdf_doc:
                    text = pdf_doc.pages[0].extract_text()
                    if text:
                        # Look for TD statement date format
                        credit_card_match = re.search(
                            r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+(\d{4})", text)
                        if credit_card_match:
                            # Get first 3 letters of month
                            month = credit_card_match.group(1)[:3]
                            year = credit_card_match.group(2)
                            new_month_year = f"{month}_{year}"

                            if new_month_year != pdf.month_year:
                                logger.info(
                                    f"Updating month/year for {pdf.original_filename} from {pdf.month_year} to {new_month_year}")
                                pdf.month_year = new_month_year
                                db.add(pdf)
                                updated += 1

        if updated > 0:
            db.commit()
            return updated
        return 0
    except Exception as e:
        logger.error(f"Error fixing TD statement dates: {str(e)}")
        db.rollback()
        return 0


# Add maintenance tools
st.sidebar.divider()
with st.sidebar.expander("🛠️ Maintenance Tools"):
    # Add button to detect account holders in existing statements
    if st.button("🔄 Detect Account Holders", help="Run account detection on all statements"):
        try:
            updated = 0
            for pdf in all_pdf_files:
                if pdf.account in ["Unknown", None, ""]:
                    pdf_content = get_pdf_content(db, pdf.id)
                    if pdf_content:
                        new_account = parse_account_holder_from_pdf(
                            pdf_content)
                        if new_account and new_account != "Unknown":
                            pdf.account = new_account
                            db.add(pdf)
                            updated += 1

            if updated > 0:
                db.commit()
                st.success(
                    f"✅ Updated account holder for {updated} statements!")
                st.rerun()
            else:
                st.info("No statements needed account holder updates.")
        except Exception as e:
            st.error(f"Error detecting account holders: {str(e)}")

    # Add button to fix TD statement dates
    if st.button("📅 Fix TD Statement Dates", help="Fix month/year for TD bank statements"):
        try:
            updated = fix_td_statement_dates(db)
            if updated > 0:
                st.success(
                    f"✅ Updated month/year for {updated} TD statements!")
                st.rerun()
            else:
                st.info("No TD statements needed date updates.")
        except Exception as e:
            st.error(f"Error fixing TD statement dates: {str(e)}")

    # Add button to update bank names
    if st.button("🔄 Update Bank Names", help="Update bank names for all statements"):
        try:
            updated_count = 0
            for pdf in all_pdf_files:
                # Get transactions for this statement
                statement_transactions = [t for t in transactions if getattr(
                    t, "pdf_file_id", None) == pdf.id]

                if statement_transactions:
                    # Get the first transaction to determine bank
                    first_trans = statement_transactions[0]
                    if first_trans and first_trans.bank:
                        # Update the PDF file with the correct bank
                        pdf.bank = first_trans.bank
                        # Ensure the PDF file is added to the session
                        db.add(pdf)

                        # Update all transactions for this statement
                        for trans in statement_transactions:
                            if trans.bank != first_trans.bank:
                                trans.bank = first_trans.bank
                                db.add(trans)
                                updated_count += 1

                        logger.info(
                            f"Updating bank for {pdf.original_filename} to {first_trans.bank}")

            if updated_count > 0:
                db.commit()
                logger.info(
                    f"Successfully updated {updated_count} bank names")
                st.success(
                    f"✅ Updated bank names for {updated_count} transactions")
                # Force refresh of the page
                st.rerun()
            else:
                st.info("No bank names needed updating")
        except Exception as e:
            logger.error(
                f"Error updating bank names: {str(e)}")
            st.error(
                "Error updating bank names. Please try again.")
            db.rollback()

    # Add button to reprocess all PDFs
    if st.button("🔄 Reprocess All PDFs", help="Re-parse all PDF statements"):
        try:
            reprocessed_count = 0
            for pdf in all_pdf_files:
                try:
                    # Get the PDF content
                    pdf_content = get_pdf_content(
                        db, pdf.id)
                    if not pdf_content:
                        logger.warning(
                            f"Could not get content for PDF: {pdf.original_filename}")
                        continue

                    # Parse transactions and balances from PDF content
                    logger.info(
                        f"Reprocessing PDF file: {pdf.original_filename}")
                    new_transactions, opening_balance, closing_balance, bank_name, statement_type = parse_pdf_transactions(
                        pdf_content)

                    if new_transactions:
                        # Delete existing transactions for this PDF
                        existing_transactions = [t for t in transactions if getattr(
                            t, "pdf_file_id", None) == pdf.id]
                        for trans in existing_transactions:
                            db.delete(trans)

                        # Update PDF file with new balances
                        pdf.opening_balance = opening_balance if opening_balance > 0 else None
                        pdf.closing_balance = closing_balance if closing_balance > 0 else None
                        db.add(pdf)

                        # Auto-categorize and save new transactions
                        new_transactions = auto_categorize_transactions(
                            db, new_transactions)
                        for trans in new_transactions:
                            trans['pdf_file_id'] = pdf.id
                            save_transaction(db, trans)

                        reprocessed_count += 1
                        logger.info(
                            f"Successfully reprocessed {pdf.original_filename}")
                except Exception as e:
                    logger.error(
                        f"Error reprocessing {pdf.original_filename}: {str(e)}")
                    continue

            if reprocessed_count > 0:
                db.commit()
                logger.info(
                    f"Successfully reprocessed {reprocessed_count} PDF files")
                st.success(
                    f"✅ Reprocessed {reprocessed_count} PDF files")
                # Force refresh of the page
                st.rerun()
            else:
                st.info("No PDFs needed reprocessing")
        except Exception as e:
            logger.error(
                f"Error in reprocessing: {str(e)}")
            st.error(
                "Error reprocessing PDFs. Please try again.")
            db.rollback()

    # Add button to recategorize all transactions
    if st.button("🏷️ Recategorize All Transactions", help="Apply vendor mappings to all transactions"):
        try:
            # Ensure vendor mappings are up to date
            vendor_map = ensure_vendor_mappings(db)
            if not vendor_map:
                st.error(
                    "No vendor mappings found. Please add some vendor mappings first.")
            else:
                # Run recategorization
                updated_count = recategorize_all_transactions(db)
                if updated_count > 0:
                    st.success(
                        f"✅ Updated categories for {updated_count} transactions!")
                    # Force refresh of session state
                    st.session_state.vendor_mappings = get_all_vendor_mappings(
                        db)
                    st.rerun()
                else:
                    st.info("No transactions needed category updates.")
        except Exception as e:
            st.error(f"Error recategorizing transactions: {str(e)}")

    # Add button to fix account holder names for all statements
    if st.button("👤 Fix Account Holders", help="Fix account holder detection for all statements"):
        try:
            # Define a local function to detect account holders to avoid circular imports
            def detect_account_holder(pdf_content):
                """Extract account holder name from the PDF content."""
                known_names = [
                    "Apeksha",
                    "Rahil Dinesh Shah",
                ]
                try:
                    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
                        first_page = pdf.pages[0]
                        text = first_page.extract_text()
                        if not text:
                            return "Unknown"

                        # Check if this is a TD credit card statement
                        is_td_credit_card = False
                        text_normalized = text.lower().replace(" ", "").replace("\n", "")
                        if ("tdcanadatrust" in text_normalized or "tdbank" in text_normalized) and \
                           ("statementdate" in text_normalized and "previousstatement" in text_normalized):
                            is_td_credit_card = True
                            logger.info(
                                "Detected TD credit card statement for account holder extraction")

                        # For TD credit card statements, look in specific locations
                        if is_td_credit_card:
                            # Extract lines for analysis
                            lines = text.splitlines()

                            # TD credit card statements typically have the cardholder name in the first few lines
                            # Look for lines that match name patterns in the first 15 lines
                            for i, line in enumerate(lines[:15]):
                                # Skip lines with transaction-like patterns (dates, amounts)
                                if re.search(r'\$\d+\.\d{2}', line) or re.match(r'^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}', line):
                                    continue

                                # Look for exact matches of known names
                                for name in known_names:
                                    if name.lower() in line.lower():
                                        logger.info(
                                            f"Found account holder name in TD statement: {name}")
                                        return name

                            # If no exact match found, look for name patterns in the header section
                            for i, line in enumerate(lines[:15]):
                                # Skip lines with common header text
                                if any(header in line.lower() for header in ["statement", "account", "balance", "payment", "credit", "limit"]):
                                    continue

                                # Look for lines that might be names (all caps, no numbers, reasonable length)
                                if line.isupper() and not any(c.isdigit() for c in line) and 10 <= len(line) <= 40:
                                    # Check if any known name parts are in this line
                                    for name in known_names:
                                        name_parts = name.lower().split()
                                        if any(part in line.lower() for part in name_parts if len(part) > 3):
                                            logger.info(
                                                f"Found potential account holder in TD header: {name}")
                                            return name

                        # For non-TD statements or if TD-specific search failed, use general approach

                        # Check for known names first (case-insensitive)
                        text_lower = text.lower()
                        for name in known_names:
                            # Use word boundaries to avoid matching substrings in transaction descriptions
                            name_pattern = r'\b' + \
                                re.escape(name.lower()) + r'\b'
                            if re.search(name_pattern, text_lower):
                                logger.info(
                                    f"Found account holder name with word boundaries: {name}")
                                return name

                        # Try to find partial matches for the known names, but be more strict
                        for name in known_names:
                            name_parts = name.lower().split()
                            # Only count matches for parts with length > 3 (avoid matching common words)
                            # and require more parts to match (at least 2 for 3-part names, all parts for 2-part names)
                            significant_parts = [
                                part for part in name_parts if len(part) > 3]
                            matches = sum(1 for part in significant_parts if re.search(
                                r'\b' + re.escape(part) + r'\b', text_lower))
                            required_matches = len(significant_parts) if len(
                                name_parts) <= 2 else 2

                            if matches >= required_matches:
                                logger.info(
                                    f"Found strict partial match for account holder: {name}")
                                return name

                        # Default to first known name if no match is found
                        logger.warning(
                            "Could not determine account holder, defaulting to first known name")
                        return known_names[0]
                except Exception as e:
                    logger.error(f"Error extracting account holder: {e}")
                return "Unknown"

            updated = 0
            processed = 0

            # Process all statements, not just those marked as TD
            for pdf in all_pdf_files:
                pdf_content = get_pdf_content(db, pdf.id)
                if pdf_content:
                    processed += 1

                    # First, check if this is a TD statement by examining the content
                    is_td_statement = False
                    try:
                        with pdfplumber.open(io.BytesIO(pdf_content)) as pdf_doc:
                            first_page_text = pdf_doc.pages[0].extract_text()
                            text_normalized = first_page_text.lower().replace(" ", "").replace("\n", "")
                            if "tdcanadatrust" in text_normalized or "tdbank" in text_normalized:
                                is_td_statement = True
                                # Update the bank field if it's not already set
                                if pdf.bank != "TD":
                                    pdf.bank = "TD"
                                    db.add(pdf)
                                    logger.info(
                                        f"Updated bank to TD for {pdf.original_filename}")
                    except Exception as e:
                        logger.error(
                            f"Error checking if statement is TD: {str(e)}")

                    # Re-detect account holder with improved algorithm
                    new_account = detect_account_holder(pdf_content)
                    if new_account and new_account != "Unknown" and new_account != pdf.account:
                        logger.info(
                            f"Updating account holder for {pdf.original_filename}: {pdf.account} -> {new_account}")
                        pdf.account = new_account
                        db.add(pdf)
                        updated += 1

            if updated > 0 or processed > 0:
                db.commit()
                st.success(
                    f"✅ Fixed account holder names for {updated} statements out of {processed} processed!")
                st.rerun()
            else:
                st.info("No statements found or no account holder fixes needed.")
        except Exception as e:
            st.error(f"Error fixing account holders: {str(e)}")

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
                st.session_state.selected_account = "All Accounts"
                st.session_state.selected_statement_type = None  # Reset statement type
                # Increment the file uploader key to force a reset
                st.session_state.uploaded_files_key += 1
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


def parse_account_holder_from_pdf(pdf_content: bytes) -> str:
    """Extract account holder name from the first page of the PDF.

    Specifically looks for "RAHIL DINESH SHAH" or "APEKSHA" in the PDF.
    Handles TD credit card statements specially to avoid misidentifying transactions.
    """
    known_names = [
        "Apeksha",
        "Rahil Dinesh Shah",
        # Add more known names here if needed
    ]
    try:
        with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
            first_page = pdf.pages[0]
            text = first_page.extract_text()
            if not text:
                return "Unknown"

            # First, detect if this is a TD credit card statement
            is_td_credit_card = False
            text_normalized = text.lower().replace(" ", "").replace("\n", "")
            if ("tdcanadatrust" in text_normalized or "tdbank" in text_normalized) and \
               ("statementdate" in text_normalized and "previousstatement" in text_normalized):
                is_td_credit_card = True
                logger.info(
                    "Detected TD credit card statement for account holder extraction")

            # For TD credit card statements, look in specific locations
            if is_td_credit_card:
                # Extract lines for analysis
                lines = text.splitlines()

                # TD credit card statements typically have the cardholder name in the first few lines
                # Look for lines that match name patterns in the first 15 lines
                for i, line in enumerate(lines[:15]):
                    # Skip lines with transaction-like patterns (dates, amounts)
                    if re.search(r'\$\d+\.\d{2}', line) or re.match(r'^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}', line):
                        continue

                    # Look for exact matches of known names
                    for name in known_names:
                        if name.lower() in line.lower():
                            logger.info(
                                f"Found account holder name in TD statement: {name}")
                            return name

                # If no exact match found, look for name patterns in the header section
                for i, line in enumerate(lines[:15]):
                    # Skip lines with common header text
                    if any(header in line.lower() for header in ["statement", "account", "balance", "payment", "credit", "limit"]):
                        continue

                    # Look for lines that might be names (all caps, no numbers, reasonable length)
                    if line.isupper() and not any(c.isdigit() for c in line) and 10 <= len(line) <= 40:
                        # Check if any known name parts are in this line
                        for name in known_names:
                            name_parts = name.lower().split()
                            if any(part in line.lower() for part in name_parts if len(part) > 3):
                                logger.info(
                                    f"Found potential account holder in TD header: {name}")
                                return name

            # For non-TD statements or if TD-specific search failed, use general approach

            # Check for known names first (case-insensitive)
            text_lower = text.lower()
            for name in known_names:
                # Use word boundaries to avoid matching substrings in transaction descriptions
                name_pattern = r'\b' + re.escape(name.lower()) + r'\b'
                if re.search(name_pattern, text_lower):
                    logger.info(
                        f"Found account holder name with word boundaries: {name}")
                    return name

            # Try to find partial matches for the known names, but be more strict
            for name in known_names:
                name_parts = name.lower().split()
                # Only count matches for parts with length > 3 (avoid matching common words)
                # and require more parts to match (at least 2 for 3-part names, all parts for 2-part names)
                significant_parts = [
                    part for part in name_parts if len(part) > 3]
                matches = sum(1 for part in significant_parts if re.search(
                    r'\b' + re.escape(part) + r'\b', text_lower))
                required_matches = len(significant_parts) if len(
                    name_parts) <= 2 else 2

                if matches >= required_matches:
                    logger.info(
                        f"Found strict partial match for account holder: {name}")
                    return name

            # Try OCR-based extraction for more difficult PDFs
            try:
                # Convert first page to image
                images = convert_from_bytes(
                    pdf_content, dpi=300, first_page=1, last_page=1)
                if images:
                    image = images[0]
                    # Run OCR on the top portion of the image where names typically appear
                    width, height = image.size
                    top_region = image.crop((0, 0, width, int(height * 0.2)))
                    ocr_text = pytesseract.image_to_string(top_region)

                    # Check for known names in OCR text with word boundaries
                    ocr_text_lower = ocr_text.lower()
                    for name in known_names:
                        name_pattern = r'\b' + re.escape(name.lower()) + r'\b'
                        if re.search(name_pattern, ocr_text_lower):
                            logger.info(
                                f"Found account holder via OCR with word boundaries: {name}")
                            return name

                    # Try partial matching with OCR text
                    for name in known_names:
                        name_parts = name.lower().split()
                        significant_parts = [
                            part for part in name_parts if len(part) > 3]
                        matches = sum(1 for part in significant_parts if re.search(
                            r'\b' + re.escape(part) + r'\b', ocr_text_lower))
                        required_matches = len(significant_parts) if len(
                            name_parts) <= 2 else 2

                        if matches >= required_matches:
                            logger.info(
                                f"Found strict partial match for account holder via OCR: {name}")
                            return name
            except Exception as e:
                logger.error(f"OCR extraction failed: {str(e)}")

            # Default to first known name if no match is found
            logger.warning(
                "Could not determine account holder, defaulting to first known name")
            return known_names[0]
    except Exception as e:
        logger.error(f"Error extracting account holder: {e}")
    return "Unknown"


if uploaded_files and not st.session_state.upload_success:
    processed_files = 0
    for idx, file in enumerate(uploaded_files):
        if validate_file(file):
            try:
                # Read file content
                pdf_content = file.read()

                # Get month/year from PDF content
                month_year = get_month_year_from_pdf(pdf_content)

                # Use the manually selected account holder instead of auto-detecting
                account_holder = st.session_state.upload_account_holder

                # Check if file already exists
                if check_existing_statement(db, file.name, month_year):
                    st.warning(
                        f"Statement '{file.name}' for {month_year} already exists in the database.")
                    continue

                # Parse transactions and balances from PDF content
                logger.info(f"Processing PDF file: {file.name}")
                try:
                    transactions, opening_balance, closing_balance, bank_name, _ = parse_pdf_transactions(
                        pdf_content)
                    # Use the selected statement type from dropdown instead of auto-detected one
                    statement_type = st.session_state.selected_statement_type
                except ValueError as e:
                    logger.error(f"Error parsing transactions: {e}")
                    transactions, opening_balance, closing_balance, bank_name, _ = [
                    ], 0.0, 0.0, "Unknown", "Unknown"
                    statement_type = st.session_state.selected_statement_type

                if transactions:
                    try:
                        # Log the account holder and bank
                        logger.info(f"Using account holder: {account_holder}")
                        logger.info(f"Detected bank: {bank_name}")
                        logger.info(f"Using statement type: {statement_type}")
                        st.info(
                            f"Assigned to account holder: {account_holder}")
                        st.info(f"Detected bank: {bank_name}")
                        st.info(f"Statement type: {statement_type}")

                        # Save PDF file with balances, account, bank, and statement type
                        pdf_file = save_pdf_file(
                            db, file.name, pdf_content, month_year,
                            opening_balance=opening_balance if opening_balance > 0 else None,
                            closing_balance=closing_balance if closing_balance > 0 else None,
                            account=account_holder,
                            bank=bank_name,
                            statement_type=statement_type
                        )

                        # Auto-categorize transactions
                        transactions = auto_categorize_transactions(
                            db, transactions)

                        # Save transactions to database with PDF file reference and statement type
                        for trans in transactions:
                            trans['pdf_file_id'] = pdf_file.id
                            # Add statement type to transaction if not already present
                            if 'statement_type' not in trans or not trans['statement_type']:
                                trans['statement_type'] = statement_type
                            save_transaction(db, trans)

                        if opening_balance > 0:
                            st.info(
                                f"Found opening balance: C${opening_balance:,.2f}")
                        if closing_balance > 0:
                            st.info(
                                f"Found closing balance: C${closing_balance:,.2f}")

                        st.success(
                            f"✅ Added {len(transactions)} new transactions from {file.name}")
                        processed_files += 1

                        # Increment the file uploader key to force a reset
                        st.session_state.uploaded_files_key += 1
                        # Force a rerun after each successful file processing
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

    # Set upload success flag only if at least one file was processed
    if processed_files > 0:
        st.session_state.upload_success = True
        st.success(f"✅ Successfully processed {processed_files} files")
        # Increment the file uploader key to force a reset
        st.session_state.uploaded_files_key += 1
        st.rerun()
    else:
        st.warning("No files were processed successfully")

# Reset flags if no files are uploaded
if not uploaded_files:
    st.session_state.upload_success = False
    st.session_state.reprocess_triggered = False

# Main display with error handling
try:
    if not df.empty:
        # First apply account filter
        if st.session_state.selected_account != "All Accounts":
            account_filtered_df = df[df["pdf_file_id"].map(lambda x: next(
                (pdf.id for pdf in all_pdf_files if pdf.id ==
                 x and pdf.account == st.session_state.selected_account),
                None) is not None)].copy()
        else:
            account_filtered_df = df.copy()

        # No month filter now, use all transactions or default to the latest month
            if not account_filtered_df.empty:
                latest_month = account_filtered_df['MonthYear'].max()
                df_display = account_filtered_df[account_filtered_df['MonthYear'] == latest_month].copy(
                )
            else:
                df_display = account_filtered_df.copy()

    transactions = get_all_transactions(db)
    pdf_files = get_pdf_files(db)

    # Store PDF files in session state for use in other tabs
    st.session_state.all_pdf_files = pdf_files

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
                'transaction_id': t.id,
                # Ensure transaction_id is included
                'pdf_file_id': getattr(t, "pdf_file_id", None)
            } for t in transactions])

            # Create a copy of the dataframe for display
            df_display = df.copy()

            # Log the initial dataframe info
            logger.info(f"Initial df columns: {df.columns.tolist()}")
            logger.info(f"Initial df shape: {df.shape}")
            logger.info(
                f"Initial pdf_file_id values: {df['pdf_file_id'].unique().tolist()}")

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
            if not df_display.empty:
                # Log the columns in df_display
                logger.info(
                    f"df_display columns: {df_display.columns.tolist()}")
                logger.info(f"df_display shape: {df_display.shape}")

                # Create copies of the filtered dataframes
                debits_df = df_display[df_display["transaction_type"] == "Debit"].copy(
                )
                credits_df = df_display[df_display["transaction_type"] == "Credit"].copy(
                )

                # Log the shapes of the filtered dataframes
                logger.info(f"debits_df shape: {debits_df.shape}")
                logger.info(f"credits_df shape: {credits_df.shape}")

                # Ensure pdf_file_id is preserved and log its values
                logger.info(
                    f"pdf_file_id values in df_display: {df_display['pdf_file_id'].unique().tolist()}")

                # Make sure pdf_file_id is preserved in the filtered dataframes
                # This is the key fix - we need to ensure the pdf_file_id column is properly copied
                debits_df["pdf_file_id"] = df_display[df_display["transaction_type"]
                                                      == "Debit"]["pdf_file_id"].values
                credits_df["pdf_file_id"] = df_display[df_display["transaction_type"]
                                                       == "Credit"]["pdf_file_id"].values

                # Log the pdf_file_id values in the filtered dataframes
                logger.info(
                    f"pdf_file_id values in debits_df: {debits_df['pdf_file_id'].unique().tolist()}")
                logger.info(
                    f"pdf_file_id values in credits_df: {credits_df['pdf_file_id'].unique().tolist()}")

                # Add select column for checkboxes
                debits_df["select"] = False
                credits_df["select"] = False

                # Log the final columns in the dataframes
                logger.info(
                    f"Final debits_df columns: {debits_df.columns.tolist()}")
                logger.info(
                    f"Final credits_df columns: {credits_df.columns.tolist()}")
            else:
                debits_df = pd.DataFrame()
                credits_df = pd.DataFrame()
                logger.warning(
                    "df_display is empty, created empty debits_df and credits_df")

            # Display tabs
            tab_names = ["🔄 Reconcile", "📈 Summary",
                         "📉 Expenses", "📥 Payments", "📆 Monthly"]
            tab_mapping = {
                "reconcile": "🔄 Reconcile",
                "summary": "📈 Summary",
                "expenses": "📉 Expenses",
                "payments": "📥 Payments",
                "monthly": "📆 Monthly"
            }

            # Get the index of the selected tab
            tab_index = list(tab_mapping.keys()).index(
                current_tab) if current_tab in tab_mapping else 0

            # Create tabs with the selected tab active
            tabs = st.tabs(tab_names)
            tab1, tab2, tab3, tab4, tab5 = tabs

            # Add debug logging
            logger.info(f"Current tab from query params: {current_tab}")
            logger.info(
                f"Selected statement: {st.session_state.selected_statement}")

            # Get the active tab from query parameters
            active_tab = st.query_params.get("tab", "reconcile")

            # Log the active tab
            logger.info(f"Active tab from query parameters: {active_tab}")

            # Store the active tab in session state for reference
            st.session_state.active_tab = active_tab

            # Handle statement click
            def handle_statement_click(statement_name, target_tab="expenses"):
                """Handle statement click and tab switching."""
                st.session_state.selected_statement = statement_name
                # Use a different session state variable to track the target tab
                st.session_state.target_tab_for_navigation = target_tab
                # Set the query parameter to switch tabs
                st.query_params["tab"] = target_tab
                logger.info(
                    f"Selected statement: {statement_name}, navigating to {target_tab} tab")
                st.rerun()

            with tab1:
                st.subheader("🔄 Balance Reconciliation")
                # Add reconciliation section
                with st.expander("Statement Details", expanded=True):
                    col1, col2, col3 = st.columns(3)

                    # Get all PDF files regardless of month selection
                    pdf_files_query = db.query(PDFFile).order_by(
                        PDFFile.upload_date.asc())
                    pdf_files_list = pdf_files_query.all()

                    # Add account holder filter
                    unique_accounts = sorted(
                        {pdf.account for pdf in pdf_files_list if pdf.account and pdf.account != "Unknown"})
                    if unique_accounts:
                        account_filter = ["All Accounts"] + unique_accounts
                        selected_reconcile_account = st.selectbox(
                            "Filter by Account Holder",
                            options=account_filter,
                            index=0,
                            key="reconcile_account_filter"
                        )

                        # Apply account filtering
                        if selected_reconcile_account != "All Accounts":
                            pdf_files_list = [
                                pdf for pdf in pdf_files_list if pdf.account == selected_reconcile_account]
                            st.info(
                                f"Filtered statements for account holder: {selected_reconcile_account}")

                    # Filter PDFs based on selected statements
                    if st.session_state.selected_statements and "All Statements" not in st.session_state.selected_statements:
                        selected_filenames = [s.split(
                            " (")[0] for s in st.session_state.selected_statements]
                        pdf_files_list = [
                            pdf for pdf in pdf_files_list if pdf.original_filename in selected_filenames]
                        st.info(
                            f"Showing reconciliation for selected statements: {', '.join(selected_filenames)}")

                    # Removed "Showing reconciliation for all statements" message

                    if pdf_files_list:
                        # Always show per-statement reconciliation table
                        statement_rows = []
                        for pdf in pdf_files_list:
                            statement_transactions = [t for t in transactions if getattr(
                                t, "pdf_file_id", None) == pdf.id]

                            # Get the first transaction to determine bank and statement type
                            first_trans = statement_transactions[0] if statement_transactions else None
                            bank = pdf.bank if pdf.bank else (
                                first_trans.bank if first_trans else "Unknown")
                            statement_type = pdf.statement_type if pdf.statement_type else "Unknown"
                            account_holder = pdf.account if pdf.account else "Unknown"

                            total_debits = sum(
                                t.amount for t in statement_transactions if t.transaction_type == "Debit")
                            total_credits = sum(
                                t.amount for t in statement_transactions if t.transaction_type == "Credit")

                            # Calculate closing balance based on bank and statement type
                            if bank == "TD" and statement_type == "Credit Card":
                                # For TD Credit Cards: closing = opening + debits - credits
                                calculated_closing = (
                                    pdf.opening_balance or 0) + total_debits - total_credits
                            else:
                                # For other accounts: closing = opening - debits + credits
                                calculated_closing = (
                                    pdf.opening_balance or 0) - total_debits + total_credits

                            difference = (
                                pdf.closing_balance - calculated_closing) if pdf.closing_balance is not None else None

                            statement_rows.append({
                                "Statement": pdf.original_filename,
                                "Bank": bank,
                                "Statement Type": statement_type,
                                "Account": account_holder,
                                "Month/Year": pdf.month_year,
                                "Opening Balance": f"${pdf.opening_balance:,.2f}" if pdf.opening_balance else "N/A",
                                "Total Debits": f"${total_debits:,.2f}",
                                "Total Credits": f"${total_credits:,.2f}",
                                "Closing Balance": f"${pdf.closing_balance:,.2f}" if pdf.closing_balance else "N/A",
                                "Difference": f"${difference:,.2f}" if difference is not None else "N/A"
                            })

                        # Sort the statements by Month/Year
                        df_statements = pd.DataFrame(statement_rows)
                        if not df_statements.empty:
                            # Convert Month/Year to datetime for proper sorting, with fallback for invalid dates
                            def parse_month_year(x):
                                try:
                                    return pd.to_datetime(f"01_{x}" if '_' in x else x, format='%d_%b_%Y')
                                except:
                                    # If parsing fails, use current date as fallback
                                    return pd.Timestamp.now()

                            df_statements['Sort_Date'] = df_statements['Month/Year'].apply(
                                parse_month_year)
                            df_statements = df_statements.sort_values(
                                'Sort_Date')
                            df_statements = df_statements.drop(
                                'Sort_Date', axis=1)  # Remove the sorting column

                        st.markdown("### Individual Statement Reconciliation")

                        # Create direct links to tabs with statement selection
                        def create_statement_link(statement_name, target_tab="expenses"):
                            """Create a direct link to a tab with statement selection."""
                            # This function creates a direct link that will be used in buttons
                            return f"?tab={target_tab}&statement={statement_name}"

                        # Add a radio button to select which tab to navigate to
                        col1, col2 = st.columns([3, 1])
                        with col1:
                            target_tab = st.radio(
                                "Select tab to view transactions:",
                                ["expenses", "payments"],
                                horizontal=True,
                                format_func=lambda x: "📉 Expenses" if x == "expenses" else "📥 Payments",
                                key="statement_target_tab"
                            )

                        # Add a clear selection button if a statement is selected
                        with col2:
                            if st.session_state.selected_statement:
                                # Create a button to clear the selection
                                if st.button("🔄 Clear Selection", key="clear_statement_selection"):
                                    st.session_state.selected_statement = None
                                    switch_to_tab("reconcile")

                        # Initialize pagination
                        if "reconcile_page" not in st.session_state:
                            st.session_state.reconcile_page = 0

                        # Calculate pagination
                        if not df_statements.empty:
                            statements_per_page = 5
                            total_pages = (
                                len(df_statements) + statements_per_page - 1) // statements_per_page

                            # Ensure current page is valid
                            if st.session_state.reconcile_page >= total_pages:
                                st.session_state.reconcile_page = total_pages - 1
                            if st.session_state.reconcile_page < 0:
                                st.session_state.reconcile_page = 0

                            # Get statements for current page
                            start_idx = st.session_state.reconcile_page * statements_per_page
                            end_idx = min(
                                start_idx + statements_per_page, len(df_statements))
                            page_df_statements = df_statements.iloc[start_idx:end_idx]

                            # Add pagination controls
                            col1, col2, col3 = st.columns([1, 2, 1])
                            with col1:
                                if st.button("◀️ Previous",
                                             disabled=st.session_state.reconcile_page <= 0,
                                             key="prev_page_btn"):
                                    st.session_state.reconcile_page -= 1
                                    st.rerun()

                            with col2:
                                st.markdown(f"**Page {st.session_state.reconcile_page + 1} of {total_pages}** "
                                            f"(Showing statements {start_idx + 1}-{end_idx} of {len(df_statements)})")

                            with col3:
                                if st.button("Next ▶️",
                                             disabled=st.session_state.reconcile_page >= total_pages - 1,
                                             key="next_page_btn"):
                                    st.session_state.reconcile_page += 1
                                    st.rerun()
                        else:
                            # If no statements, just use empty DataFrame for the page
                            page_df_statements = df_statements

                        # Create a custom clickable table
                        # First, display column headers
                        cols = st.columns(
                            [3, 1, 1, 1, 1, 1.5, 1.5, 1.5, 1.5, 1.5])
                        cols[0].markdown("**Statement**")
                        cols[1].markdown("**Bank**")
                        cols[2].markdown("**Type**")
                        cols[3].markdown("**Account**")
                        cols[4].markdown("**Month/Year**")
                        cols[5].markdown("**Opening Balance**")
                        cols[6].markdown("**Total Debits**")
                        cols[7].markdown("**Total Credits**")
                        cols[8].markdown("**Closing Balance**")
                        cols[9].markdown("**Difference**")

                        # Display each row with a clickable statement name
                        for i, row in page_df_statements.iterrows():
                            cols = st.columns(
                                [3, 1, 1, 1, 1, 1.5, 1.5, 1.5, 1.5, 1.5])

                            # Check if this statement is currently selected
                            is_selected = st.session_state.selected_statement == row['Statement']

                            # Make the statement name clickable with visual indicator if selected
                            button_text = f"📄 {row['Statement']}" if not is_selected else f"🔍 {row['Statement']} (Selected)"
                            button_help = f"Click to view transactions for {row['Statement']}"

                            # Get the current target tab from the radio button
                            current_target_tab = st.session_state.statement_target_tab

                            # Create a button that will call our switch_to_tab function
                            button_type = "primary" if is_selected else "secondary"
                            if cols[0].button(button_text, key=f"statement_btn_{i}",
                                              help=button_help,
                                              type=button_type):
                                # When clicked, switch to the target tab with the selected statement
                                switch_to_tab(current_target_tab,
                                              row['Statement'])

                            # Display other columns
                            cols[1].write(row['Bank'])
                            cols[2].write(row['Statement Type'])
                            cols[3].write(row['Account'])
                            cols[4].write(row['Month/Year'])
                            cols[5].write(row['Opening Balance'])
                            cols[6].write(row['Total Debits'])
                            cols[7].write(row['Total Credits'])
                            cols[8].write(row['Closing Balance'])
                            cols[9].write(row['Difference'])
                    else:
                        st.warning("No statements found for reconciliation.")

            with tab2:
                st.subheader("📊 Total Summary")

                # Get latest balances
                latest_balances = get_latest_balances(db)

                # Calculate total wealth
                total_chequing = sum(
                    bank_data["balance"] for bank_data in latest_balances["chequing"].values())
                total_savings = sum(
                    bank_data["balance"] for bank_data in latest_balances["savings"].values())
                total_credit = sum(
                    bank_data["balance"] for bank_data in latest_balances["credit"].values())
                total_wealth = total_chequing + total_savings - total_credit

                # Display total wealth prominently
                st.markdown("### 💰 Total Wealth")
                st.metric(
                    "Total Wealth",
                    f"C${total_wealth:,.2f}",
                    help="Sum of all Chequing + Sum of all Savings - Sum of all Credit Card Balances"
                )

                # Show breakdown by account type
                st.markdown("#### Account Balances")

                # Chequing Accounts
                if latest_balances["chequing"]:
                    st.markdown("##### 💳 Chequing Accounts")
                    cols = st.columns(len(latest_balances["chequing"]))
                    for i, (bank, data) in enumerate(latest_balances["chequing"].items()):
                        cols[i].metric(
                            f"{bank} Chequing",
                            f"C${data['balance']:,.2f}",
                            help=f"From {data['date'].strftime('%B %Y')}"
                        )

                # Savings Accounts
                if latest_balances["savings"]:
                    st.markdown("##### 💰 Savings Accounts")
                    cols = st.columns(len(latest_balances["savings"]))
                    for i, (bank, data) in enumerate(latest_balances["savings"].items()):
                        cols[i].metric(
                            f"{bank} Savings",
                            f"C${data['balance']:,.2f}",
                            help=f"From {data['date'].strftime('%B %Y')}"
                        )

                # Credit Card Accounts
                if latest_balances["credit"]:
                    st.markdown("##### 💳 Credit Card Accounts")
                    cols = st.columns(len(latest_balances["credit"]))
                    for i, (bank, data) in enumerate(latest_balances["credit"].items()):
                        cols[i].metric(
                            f"{bank} Credit Card",
                            f"C${data['balance']:,.2f}",
                            help=f"From {data['date'].strftime('%B %Y')}"
                        )

                # Show totals for each type
                st.markdown("#### Summary")
                col1, col2, col3 = st.columns(3)
                col1.metric(
                    "Total Chequing",
                    f"C${total_chequing:,.2f}",
                    help="Sum of all chequing accounts"
                )
                col2.metric(
                    "Total Savings",
                    f"C${total_savings:,.2f}",
                    help="Sum of all savings accounts"
                )
                col3.metric(
                    "Total Credit Card",
                    f"C${total_credit:,.2f}",
                    help="Sum of all credit card balances"
                )

                st.divider()

                # Always use all transactions for summary, regardless of month selection
                df_summary = df.copy()

                # Calculate totals
                total_debits = df_summary[df_summary["transaction_type"] == "Debit"]["amount"].sum(
                )
                total_credits = df_summary[df_summary["transaction_type"] == "Credit"]["amount"].sum(
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
                            delta_color="normal" if net_change > 0 else "inverse")

                # Add monthly cash flow breakdown
                st.markdown("### 📅 Monthly Cash Flow")
                df_summary["Month"] = df_summary["date"].dt.strftime(
                    "%Y-%m")
                monthly_cashflow = df_summary.groupby("Month").apply(
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
                st.plotly_chart(fig, use_container_width=True,
                                key="monthly_cashflow_chart")

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
                st.plotly_chart(fig, use_container_width=True,
                                key="financial_overview_chart")

            with tab3:
                st.subheader("✏️ Edit Debit Categories")
                st.markdown(
                    "_*ℹ️ Double Click on a transaction's Field to edit it.*_")

                # Category Management for Expenses
                with st.expander("🏷️ Manage Expense Categories"):
                    # Add new category section
                    new_category = st.text_input(
                        "New Category Name", key="expense_new_category_input")
                    if st.button("Add New Category", key="expense_add_new_category_btn"):
                        if new_category:
                            try:
                                # Create a unique vendor mapping for the category
                                temp_vendor = f"__temp_expense_{new_category.lower()}"
                                logger.info(
                                    f"Adding new expense category: {new_category}")
                                mapping = save_vendor_mapping(
                                    db, temp_vendor, new_category)
                                if mapping:
                                    # Force refresh of vendor mappings
                                    st.session_state.vendor_mappings = get_all_vendor_mappings(
                                        db)
                                    st.success(
                                        f"✅ Added new expense category: {new_category}")
                                    # Force a rerun to update all dropdowns
                                    st.rerun()
                                else:
                                    st.error("Failed to save the new category")
                            except Exception as e:
                                logger.error(
                                    f"Error adding new category: {str(e)}")
                                st.error(
                                    f"Error adding new category: {str(e)}")
                        else:
                            st.error("Please enter a category name")

                # Get existing vendor mappings
                vendor_map = st.session_state.vendor_mappings if "vendor_mappings" in st.session_state else get_all_vendor_mappings(
                    db)
                if "vendor_mappings" not in st.session_state:
                    st.session_state.vendor_mappings = vendor_map
                    logger.info(
                        f"Initialized vendor mappings with {len(vendor_map)} entries")

                # Get all unique categories for the dropdown
                all_categories = [
                    "All"] + sorted(set([v for v in vendor_map.values() if v != "Uncategorized"]))

                filtered_debits_df = debits_df
                # Check if a statement is selected from the reconcile tab
                if st.session_state.selected_statement:
                    # Get PDF files from session state
                    if st.session_state.all_pdf_files:
                        # Find the PDF file ID for the selected statement
                        selected_pdf = next(
                            (pdf for pdf in st.session_state.all_pdf_files if pdf.original_filename == st.session_state.selected_statement), None)

                        # Log the selected statement and PDF info
                        logger.info(
                            f"Looking for statement: {st.session_state.selected_statement}")
                        logger.info(
                            f"Found PDF files: {[pdf.original_filename for pdf in st.session_state.all_pdf_files]}")

                        if selected_pdf:
                            # Debug info
                            logger.info(f"Selected PDF ID: {selected_pdf.id}")
                            logger.info(
                                f"Debits DataFrame columns: {debits_df.columns.tolist()}")
                            logger.info(
                                f"PDF file IDs in debits_df: {debits_df['pdf_file_id'].unique().tolist()}")

                        # Filter transactions for the selected statement
                        # Check if pdf_file_id is in the columns
                        if "pdf_file_id" in debits_df.columns:
                            filtered_debits_df = debits_df[debits_df["pdf_file_id"]
                                                           == selected_pdf.id]
                            logger.info(f"Filtered using pdf_file_id column")
                        else:
                            logger.error(
                                f"pdf_file_id column not found in debits_df")
                            st.error(
                                "Error: Could not filter transactions by statement. Please try again.")

                        # Log the number of transactions found
                        logger.info(
                            f"Found {len(filtered_debits_df)} transactions for statement: {st.session_state.selected_statement}")

                        st.info(
                            f"Showing transactions for statement: {st.session_state.selected_statement}")

                        # Create a button to clear the statement filter
                        if st.button("🔄 Clear Statement Filter", key="clear_statement_filter_expenses"):
                            st.session_state.selected_statement = None
                            switch_to_tab("expenses")

                # --- Category Filter for Expenses Tab (toggle version) ---
                show_expense_category_filter = st.checkbox(
                    "Filter by Category", key="expense_category_filter_chk")
                selected_category = None
                if show_expense_category_filter:
                    selected_category = st.selectbox(
                        "Select Category",
                        options=all_categories,
                        index=0,
                        key="expenses_category_filter"
                    )
                    if selected_category != "All":
                        filtered_debits_df = filtered_debits_df[filtered_debits_df["Category"]
                                                                == selected_category]
                # If not checked, show all categories (no filter)

                # --- Date Range Filter for Expenses Tab (toggle version) ---
                show_expense_date_filter = st.checkbox(
                    "Filter by Date Range", key="expense_date_filter_chk")
                date_range_expense = None
                if show_expense_date_filter:
                    min_date = filtered_debits_df["Date"].min().date(
                    ) if not filtered_debits_df.empty else None
                    max_date = filtered_debits_df["Date"].max().date(
                    ) if not filtered_debits_df.empty else None
                    date_range_expense = st.date_input(
                        "Select date range (Expenses)",
                        value=(min_date, max_date),
                        min_value=min_date,
                        max_value=max_date,
                        key="expense_date_range_picker"
                    )
                    if date_range_expense and isinstance(date_range_expense, tuple) and len(date_range_expense) == 2:
                        start_date, end_date = date_range_expense
                        filtered_debits_df = filtered_debits_df[
                            (filtered_debits_df["Date"].dt.date >= start_date) &
                            (filtered_debits_df["Date"].dt.date <= end_date)
                        ]
                else:
                    if "expense_date_range_picker" in st.session_state:
                        del st.session_state["expense_date_range_picker"]

                # --- Display Expenses ---
                # Prepare the display dataframe with transaction IDs
                display_df = filtered_debits_df[[
                    "select", "date", "details", "amount", "category", "transaction_id"]].copy()
                display_df.rename(columns={
                    "date": "Date",
                    "details": "Details",
                    "amount": "Amount",
                    "category": "Category",
                    "select": "Select",
                    "transaction_id": "_transaction_id"  # Keep transaction_id for reference
                }, inplace=True)

                # Use the data editor and capture the edited data
                edited_df = st.data_editor(
                    display_df,
                    column_config={
                        "Select": st.column_config.CheckboxColumn(
                            "Select",
                            help="Select transactions to update",
                            default=False,
                        ),
                        "Date": st.column_config.DateColumn(
                            "Date",
                            format="DD/MM/YYYY",
                        ),
                        "Details": st.column_config.TextColumn(
                            "Details",
                            help="Transaction details",
                        ),
                        "Amount": st.column_config.NumberColumn(
                            "Amount",
                            help="Transaction amount",
                            format="₹%.2f",
                        ),
                        "Category": st.column_config.SelectboxColumn(
                            "Category",
                            help="Select category",
                            options=all_categories,
                            required=True,
                        ),
                        "_transaction_id": st.column_config.Column(
                            "ID",
                            help="Transaction ID",
                            disabled=True,
                            required=True,
                            width="small"
                        ),
                    },
                    hide_index=True,
                    key="expenses_editor",
                    # Disable editing of transaction ID
                    disabled=["_transaction_id"],
                )

                # Add buttons for saving changes and auto-categorizing
                col1, col2 = st.columns([1, 1])
                save_clicked = col1.button(
                    "💾 Save Category Changes", key="save_expense_changes")
                auto_categorize_clicked = col2.button(
                    "🔄 Auto-Categorize Similar", key="auto_categorize_expenses", help="Apply selected categories to similar transactions")

                if save_clicked:
                    updates = False
                    for idx, row in edited_df.iterrows():
                        try:
                            # Get the original category from the database
                            transaction = db.query(Transaction).filter(
                                Transaction.id == row['_transaction_id']).first()
                            if transaction:
                                # Check if category has changed
                                if transaction.category != row['Category']:
                                    logger.info(
                                        f"Saving category for transaction {row['_transaction_id']} from '{transaction.category}' to '{row['Category']}'")
                                    transaction.category = row['Category']
                                    db.add(transaction)

                                    # Store the vendor mapping for future auto-categorization
                                    if row['Category'] != "Uncategorized":
                                        # Create a vendor mapping using the transaction details
                                        # Extract a more effective vendor key from the transaction details
                                        def extract_vendor_key(details):
                                            """Extract a more effective vendor key from transaction details."""
                                            # Normalize and clean the text
                                            text = details.lower().strip()

                                            # Remove dates in various formats (MM/DD, YYYY-MM-DD, etc.)
                                            text = re.sub(
                                                r'\d{1,2}/\d{1,2}', '', text)
                                            text = re.sub(
                                                r'\d{4}-\d{1,2}-\d{1,2}', '', text)

                                            # Remove transaction IDs and reference numbers
                                            text = re.sub(
                                                r'ref\s*#?\s*\d+', '', text, flags=re.IGNORECASE)
                                            text = re.sub(
                                                r'transaction\s*#?\s*\d+', '', text, flags=re.IGNORECASE)
                                            text = re.sub(
                                                r'id\s*#?\s*\d+', '', text, flags=re.IGNORECASE)

                                            # Remove special characters but keep spaces
                                            text = re.sub(r'[^\w\s]', '', text)

                                            # Remove common words that don't help identify the vendor
                                            common_words = ['purchase', 'payment', 'online', 'retail', 'store',
                                                            'service', 'fee', 'charge', 'debit', 'credit', 'transaction',
                                                            'interac', 'etransfer', 'transfer', 'withdrawal', 'deposit']
                                            words = text.split()
                                            filtered_words = [word for word in words
                                                              if word not in common_words and len(word) > 2]

                                            # If we have words left, join them; otherwise use the original text
                                            if filtered_words:
                                                return ' '.join(filtered_words)
                                            else:
                                                # Fallback to original text with minimal cleaning
                                                return ' '.join(text.split())

                                        # Use our new function to extract a better vendor key
                                        vendor_key = extract_vendor_key(
                                            row['Details'])

                                        if vendor_key:
                                            try:
                                                # Check if mapping already exists
                                                existing_mapping = db.query(VendorMapping).filter(
                                                    VendorMapping.vendor_substring == vendor_key
                                                ).first()

                                                if not existing_mapping:
                                                    # Create new mapping
                                                    save_vendor_mapping(
                                                        db, vendor_key, row['Category'])
                                                    logger.info(
                                                        f"Created new vendor mapping: {vendor_key} -> {row['Category']}")

                                                    # Apply this category to similar transactions
                                                    updated_count = apply_category_to_similar_transactions(
                                                        db, row['Details'], row['Category'])
                                                    if updated_count > 0:
                                                        logger.info(
                                                            f"Auto-applied category to {updated_count} similar transactions")
                                                elif existing_mapping.category != row['Category']:
                                                    # Update existing mapping
                                                    existing_mapping.category = row['Category']
                                                    db.add(existing_mapping)
                                                    logger.info(
                                                        f"Updated vendor mapping: {vendor_key} -> {row['Category']}")

                                                    # Apply this category to similar transactions
                                                    updated_count = apply_category_to_similar_transactions(
                                                        db, row['Details'], row['Category'])
                                                    if updated_count > 0:
                                                        logger.info(
                                                            f"Auto-applied category to {updated_count} similar transactions")
                                            except Exception as e:
                                                logger.error(
                                                    f"Error saving vendor mapping: {str(e)}")

                                    updates = True
                                # Check if details have changed
                                if transaction.details != row['Details']:
                                    logger.info(
                                        f"Saving details for transaction {row['_transaction_id']}")
                                    transaction.details = row['Details']
                                    db.add(transaction)
                                    updates = True
                        except Exception as e:
                            logger.error(
                                f"Error saving transaction {row['_transaction_id']}: {str(e)}")

                    if updates:
                        db.commit()
                        # Refresh vendor mappings in session state
                        st.session_state.vendor_mappings = get_all_vendor_mappings(
                            db)
                        st.success("✅ Changes saved successfully!")
                    else:
                        st.info("No changes to save.")

                # Handle auto-categorize button click
                if auto_categorize_clicked:
                    # Get selected rows (or all rows if none selected)
                    if edited_df["Select"].any():
                        selected_rows = edited_df[edited_df["Select"]]
                    else:
                        selected_rows = edited_df

                    # Only process rows with non-Uncategorized categories
                    categorized_rows = selected_rows[selected_rows["Category"]
                                                     != "Uncategorized"]

                    if categorized_rows.empty:
                        st.warning(
                            "Please select at least one categorized transaction.")
                    else:
                        total_updated = 0
                        for _, row in categorized_rows.iterrows():
                            # Apply the category to similar transactions
                            updated_count = apply_category_to_similar_transactions(
                                db, row['Details'], row['Category'])
                            total_updated += updated_count

                        if total_updated > 0:
                            st.success(
                                f"✅ Applied categories to {total_updated} similar transactions!")
                            # Refresh the page to show updated categories
                            st.rerun()
                        else:
                            st.info("No similar transactions found to update.")

                # Add switch button for Expenses
                col1, col2 = st.columns([2, 8])
                with col1:
                    # Use edited_df instead of display_df to check for selections
                    has_selections = edited_df["Select"].any()
                    if st.button(
                        "🔄 Switch Selected to Credits",
                        key="switch_debits_to_credits",
                        disabled=not has_selections,
                        type="primary" if has_selections else "secondary"
                    ):
                        # Use edited_df to get the selected rows
                        selected_rows = edited_df[edited_df["Select"]]
                        selected_trans_ids = selected_rows["_transaction_id"].tolist(
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
                            st.rerun()
                        else:
                            st.warning("No transactions were switched")

                # Show expense summary
                debit_summary = display_df.groupby(
                    "Category")["Amount"].sum().reset_index()
                debit_summary = debit_summary.sort_values(
                    "Amount", ascending=False)

                st.subheader("📊 Expense Summary")
                st.dataframe(debit_summary, use_container_width=True)

                if not debit_summary.empty:
                    chart_type = st.radio("Choose Chart Type", [
                        "Pie Chart", "Bar Chart"], horizontal=True, key="debit_chart_type")
                    if chart_type == "Pie Chart":
                        fig = px.pie(debit_summary, values="Amount",
                                     names="Category", title="Expenses by Category", hole=0.4)
                    else:
                        fig = px.bar(debit_summary, x="Category", y="Amount",
                                     title="Expenses by Category", color="Category")
                    st.plotly_chart(fig, use_container_width=True,
                                    key="debits_by_category_chart")
                else:
                    st.info(
                        "No debit transactions found in the selected period.")

                # Store the current state in session state for reference
                st.session_state.current_debits_df = edited_df.copy()

            with tab4:
                st.subheader("💳 Credit Transactions")
                st.markdown(
                    "_*ℹ️ Click on a transaction's 'Details' text below to edit it.*_")

                # Category Management for Credits (in expander)
                with st.expander("🏷️ Manage Income Categories"):
                    # Add new category section
                    new_category = st.text_input(
                        "New Category Name", key="income_new_category_input_tab4")
                    if st.button("Add New Category", key="income_add_new_category_btn_tab4"):
                        if new_category:
                            try:
                                # Create a unique vendor mapping for the category
                                temp_vendor = f"__temp_income_{new_category.lower()}"
                                logger.info(
                                    f"Adding new income category: {new_category}")
                                mapping = save_vendor_mapping(
                                    db, temp_vendor, new_category)
                                if mapping:
                                    # Force refresh of vendor mappings
                                    st.session_state.vendor_mappings = get_all_vendor_mappings(
                                        db)
                                    st.success(
                                        f"✅ Added new income category: {new_category}")
                                    # Force a rerun to update all dropdowns
                                    st.rerun()
                                else:
                                    st.error("Failed to save the new category")
                            except Exception as e:
                                logger.error(
                                    f"Error adding new category: {str(e)}")
                                st.error(
                                    f"Error adding new category: {str(e)}")
                        else:
                            st.error("Please enter a category name")

                # Get existing vendor mappings
                vendor_map = st.session_state.vendor_mappings if "vendor_mappings" in st.session_state else get_all_vendor_mappings(
                    db)
                if "vendor_mappings" not in st.session_state:
                    st.session_state.vendor_mappings = vendor_map
                    logger.info(
                        f"Initialized vendor mappings with {len(vendor_map)} entries")

                # Get all unique categories for the dropdown
                all_categories = [
                    "All"] + sorted(set([v for v in vendor_map.values() if v != "Uncategorized"]))

                filtered_credits_df = credits_df
                # Check if a statement is selected from the reconcile tab
                if st.session_state.selected_statement:
                    # Get PDF files from session state
                    if st.session_state.all_pdf_files:
                        # Find the PDF file ID for the selected statement
                        selected_pdf = next(
                            (pdf for pdf in st.session_state.all_pdf_files if pdf.original_filename == st.session_state.selected_statement), None)

                        # Log the selected statement and PDF info
                        logger.info(
                            f"Looking for statement: {st.session_state.selected_statement}")
                        logger.info(
                            f"Found PDF files: {[pdf.original_filename for pdf in st.session_state.all_pdf_files]}")

                        if selected_pdf:
                            # Debug info
                            logger.info(f"Selected PDF ID: {selected_pdf.id}")
                            logger.info(
                                f"Credits DataFrame columns: {credits_df.columns.tolist()}")
                            logger.info(
                                f"PDF file IDs in credits_df: {credits_df['pdf_file_id'].unique().tolist()}")

                        # Filter transactions for the selected statement
                        # Check if pdf_file_id is in the columns
                        if "pdf_file_id" in credits_df.columns:
                            filtered_credits_df = credits_df[credits_df["pdf_file_id"]
                                                             == selected_pdf.id]
                            logger.info(f"Filtered using pdf_file_id column")
                        else:
                            logger.error(
                                f"pdf_file_id column not found in credits_df")
                            st.error(
                                "Error: Could not filter transactions by statement. Please try again.")

                        # Log the number of transactions found
                        logger.info(
                            f"Found {len(filtered_credits_df)} transactions for statement: {st.session_state.selected_statement}")

                        st.info(
                            f"Showing transactions for statement: {st.session_state.selected_statement}")

                        # Create a button to clear the statement filter
                        if st.button("🔄 Clear Statement Filter", key="clear_statement_filter_payments"):
                            st.session_state.selected_statement = None
                            switch_to_tab("payments")

                # --- Category Filter for Payments Tab (toggle version) ---
                show_payments_category_filter = st.checkbox(
                    "Filter by Category", key="payments_category_filter_chk")
                selected_category = None
                if show_payments_category_filter:
                    selected_category = st.selectbox(
                        "Select Category", options=all_categories, index=0, key="payments_category_filter")
                    if selected_category != "All":
                        filtered_credits_df = filtered_credits_df[filtered_credits_df["Category"]
                                                                  == selected_category]

                # --- Date Range Filter for Payments Tab (toggle version) ---
                show_payments_date_filter = st.checkbox(
                    "Filter by Date Range", key="payments_date_filter_chk")
                date_range_payments = None
                if show_payments_date_filter:
                    min_date = filtered_credits_df["Date"].min().date(
                    ) if not filtered_credits_df.empty else None
                    max_date = filtered_credits_df["Date"].max().date(
                    ) if not filtered_credits_df.empty else None
                    date_range_payments = st.date_input("Select date range (Payments)", value=(
                        min_date, max_date), min_value=min_date, max_value=max_date, key="payments_date_range_picker")
                    if date_range_payments and isinstance(date_range_payments, tuple) and len(date_range_payments) == 2:
                        start_date, end_date = date_range_payments
                        filtered_credits_df = filtered_credits_df[(filtered_credits_df["Date"].dt.date >= start_date) & (
                            filtered_credits_df["Date"].dt.date <= end_date)]

                # --- Display Payments ---
                # Prepare the display dataframe with transaction IDs
                display_df = filtered_credits_df[[
                    "select", "date", "details", "amount", "category", "transaction_id"]].copy()
                display_df.rename(columns={
                    "date": "Date",
                    "details": "Details",
                    "amount": "Amount",
                    "category": "Category",
                    "select": "Select",
                    "transaction_id": "_transaction_id"  # Keep transaction_id for reference
                }, inplace=True)

                # Use the data editor and capture the edited data
                edited_df = st.data_editor(
                    display_df,
                    column_config={
                        "Select": st.column_config.CheckboxColumn("Select", help="Select transactions to update", default=False),
                        "Date": st.column_config.DateColumn("Date", format="DD/MM/YYYY"),
                        "Details": st.column_config.TextColumn("Details", help="Transaction details"),
                        "Amount": st.column_config.NumberColumn("Amount", help="Transaction amount", format="₹%.2f"),
                        "Category": st.column_config.SelectboxColumn("Category", help="Select category", options=all_categories, required=True),
                        "_transaction_id": st.column_config.Column(
                            "ID",
                            help="Transaction ID",
                            disabled=True,
                            required=True,
                            width="small"
                        ),
                    },
                    hide_index=True,
                    key="payments_editor",
                    # Disable editing of transaction ID
                    disabled=["_transaction_id"],
                )

                # Add buttons for saving changes and auto-categorizing
                col1, col2 = st.columns([1, 1])
                save_clicked = col1.button(
                    "💾 Save Category Changes", key="save_payment_changes")
                auto_categorize_clicked = col2.button(
                    "🔄 Auto-Categorize Similar", key="auto_categorize_payments", help="Apply selected categories to similar transactions")

                if save_clicked:
                    updates = False
                    for idx, row in edited_df.iterrows():
                        try:
                            # Get the original category from the database
                            transaction = db.query(Transaction).filter(
                                Transaction.id == row['_transaction_id']).first()
                            if transaction:
                                # Check if category has changed
                                if transaction.category != row['Category']:
                                    logger.info(
                                        f"Saving category for transaction {row['_transaction_id']} from '{transaction.category}' to '{row['Category']}'")
                                    transaction.category = row['Category']
                                    db.add(transaction)

                                    # Store the vendor mapping for future auto-categorization
                                    if row['Category'] != "Uncategorized":
                                        # Create a vendor mapping using the transaction details
                                        # Extract a more effective vendor key from the transaction details
                                        def extract_vendor_key(details):
                                            """Extract a more effective vendor key from transaction details."""
                                            # Normalize and clean the text
                                            text = details.lower().strip()

                                            # Remove dates in various formats (MM/DD, YYYY-MM-DD, etc.)
                                            text = re.sub(
                                                r'\d{1,2}/\d{1,2}', '', text)
                                            text = re.sub(
                                                r'\d{4}-\d{1,2}-\d{1,2}', '', text)

                                            # Remove transaction IDs and reference numbers
                                            text = re.sub(
                                                r'ref\s*#?\s*\d+', '', text, flags=re.IGNORECASE)
                                            text = re.sub(
                                                r'transaction\s*#?\s*\d+', '', text, flags=re.IGNORECASE)
                                            text = re.sub(
                                                r'id\s*#?\s*\d+', '', text, flags=re.IGNORECASE)

                                            # Remove special characters but keep spaces
                                            text = re.sub(r'[^\w\s]', '', text)

                                            # Remove common words that don't help identify the vendor
                                            common_words = ['purchase', 'payment', 'online', 'retail', 'store',
                                                            'service', 'fee', 'charge', 'debit', 'credit', 'transaction',
                                                            'interac', 'etransfer', 'transfer', 'withdrawal', 'deposit']
                                            words = text.split()
                                            filtered_words = [word for word in words
                                                              if word not in common_words and len(word) > 2]

                                            # If we have words left, join them; otherwise use the original text
                                            if filtered_words:
                                                return ' '.join(filtered_words)
                                            else:
                                                # Fallback to original text with minimal cleaning
                                                return ' '.join(text.split())

                                        # Use our new function to extract a better vendor key
                                        vendor_key = extract_vendor_key(
                                            row['Details'])

                                        if vendor_key:
                                            try:
                                                # Check if mapping already exists
                                                existing_mapping = db.query(VendorMapping).filter(
                                                    VendorMapping.vendor_substring == vendor_key
                                                ).first()

                                                if not existing_mapping:
                                                    # Create new mapping
                                                    save_vendor_mapping(
                                                        db, vendor_key, row['Category'])
                                                    logger.info(
                                                        f"Created new vendor mapping: {vendor_key} -> {row['Category']}")

                                                    # Apply this category to similar transactions
                                                    updated_count = apply_category_to_similar_transactions(
                                                        db, row['Details'], row['Category'])
                                                    if updated_count > 0:
                                                        logger.info(
                                                            f"Auto-applied category to {updated_count} similar transactions")
                                                elif existing_mapping.category != row['Category']:
                                                    # Update existing mapping
                                                    existing_mapping.category = row['Category']
                                                    db.add(existing_mapping)
                                                    logger.info(
                                                        f"Updated vendor mapping: {vendor_key} -> {row['Category']}")

                                                    # Apply this category to similar transactions
                                                    updated_count = apply_category_to_similar_transactions(
                                                        db, row['Details'], row['Category'])
                                                    if updated_count > 0:
                                                        logger.info(
                                                            f"Auto-applied category to {updated_count} similar transactions")
                                            except Exception as e:
                                                logger.error(
                                                    f"Error saving vendor mapping: {str(e)}")

                                    updates = True
                                # Check if details have changed
                                if transaction.details != row['Details']:
                                    logger.info(
                                        f"Saving details for transaction {row['_transaction_id']}")
                                    transaction.details = row['Details']
                                    db.add(transaction)
                                    updates = True
                        except Exception as e:
                            logger.error(
                                f"Error saving transaction {row['_transaction_id']}: {str(e)}")

                    if updates:
                        db.commit()
                        # Refresh vendor mappings in session state
                        st.session_state.vendor_mappings = get_all_vendor_mappings(
                            db)
                        st.success("✅ Changes saved successfully!")
                    else:
                        st.info("No changes to save.")

                # Handle auto-categorize button click
                if auto_categorize_clicked:
                    # Get selected rows (or all rows if none selected)
                    if edited_df["Select"].any():
                        selected_rows = edited_df[edited_df["Select"]]
                    else:
                        selected_rows = edited_df

                    # Only process rows with non-Uncategorized categories
                    categorized_rows = selected_rows[selected_rows["Category"]
                                                     != "Uncategorized"]

                    if categorized_rows.empty:
                        st.warning(
                            "Please select at least one categorized transaction.")
                    else:
                        total_updated = 0
                        for _, row in categorized_rows.iterrows():
                            # Apply the category to similar transactions
                            updated_count = apply_category_to_similar_transactions(
                                db, row['Details'], row['Category'])
                            total_updated += updated_count

                        if total_updated > 0:
                            st.success(
                                f"✅ Applied categories to {total_updated} similar transactions!")
                            # Refresh the page to show updated categories
                            st.rerun()
                        else:
                            st.info("No similar transactions found to update.")

                # Add switch button for Payments
                col1, col2 = st.columns([2, 8])
                with col1:
                    # Use edited_df instead of display_df to check for selections
                    has_selections = edited_df["Select"].any()
                    if st.button("🔄 Switch Selected to Debits", key="switch_credits_to_debits", disabled=not has_selections, type="primary" if has_selections else "secondary"):
                        # Use edited_df to get the selected rows
                        selected_rows = edited_df[edited_df["Select"]]
                        selected_trans_ids = selected_rows["_transaction_id"].tolist(
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
                            st.rerun()
                        else:
                            st.warning("No transactions were switched")

                # Show income summary
                credit_summary = display_df.groupby(
                    "Category")["Amount"].sum().reset_index()
                credit_summary = credit_summary.sort_values(
                    "Amount", ascending=False)

                st.subheader("📊 Income Summary")
                st.dataframe(credit_summary, use_container_width=True)

                if not credit_summary.empty:
                    chart_type = st.radio("Choose Chart Type", [
                                          "Pie Chart", "Bar Chart"], horizontal=True, key="credit_chart_type")
                    if chart_type == "Pie Chart":
                        fig = px.pie(credit_summary, values="Amount",
                                     names="Category", title="Income by Category", hole=0.4)
                    else:
                        fig = px.bar(credit_summary, x="Category", y="Amount",
                                     title="Income by Category", color="Category")
                    st.plotly_chart(fig, use_container_width=True,
                                    key="credits_by_category_chart")
                else:
                    st.info("No credit transactions found in the selected period.")

                # Store the current state in session state for reference
                st.session_state.current_credits_df = edited_df.copy()

            with tab5:
                st.subheader("📅 Monthly Expense Report")
                # --- Account Filter for Monthly Tab (toggle version) ---
                show_monthly_account_filter = st.checkbox(
                    "Filter by Account", key="monthly_account_filter_chk")
                selected_account = None
                df_monthly = df_display.copy()
                all_accounts = sorted(
                    {pdf.account for pdf in all_pdf_files if pdf.account})
                if show_monthly_account_filter and all_accounts:
                    selected_account = st.selectbox(
                        "Select Account", all_accounts, key="monthly_account_filter")
                    df_monthly = df_monthly[df_monthly["pdf_file_id"].map(lambda x: next(
                        (pdf.id for pdf in all_pdf_files if pdf.id == x and pdf.account == selected_account), None) is not None)]
                # Use df_monthly for the rest of the Monthly tab logic
                if df_monthly.empty:
                    st.info(
                        "No transactions to show for the selected period.")
                else:
                    df_monthly["Month"] = df_monthly["date"].dt.to_period(
                        "M").astype(str)
                    available_months = sorted(
                        df_monthly["Month"].unique(), reverse=True)
                    selected_month = st.selectbox(
                        "Select a Month", available_months)

                    filtered_df = df_monthly[
                        (df_monthly["Month"] == selected_month)
                    ]

                    # Cashflow overview for the selected month
                    total_debits = filtered_df[filtered_df["transaction_type"] == "Debit"]["amount"].sum(
                    )
                    total_credits = filtered_df[filtered_df["transaction_type"] == "Credit"]["amount"].sum(
                    )
                    net_change = total_credits - total_debits
                    st.markdown("### 💰 Cash Flow Overview (Selected Month)")
                    col1, col2, col3 = st.columns(3)
                    col1.metric("💸 Total Debits", f"C${total_debits:,.2f}")
                    col2.metric("💰 Total Credits", f"C${total_credits:,.2f}")
                    col3.metric("📊 Net Cash Flow",
                                f"C${net_change:,.2f}",
                                delta=f"{'Positive' if net_change > 0 else 'Negative'} Flow",
                                delta_color="normal" if net_change > 0 else "inverse")

                    filtered_df = filtered_df[
                        filtered_df["transaction_type"] == "Debit"
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
                        st.plotly_chart(
                            chart, use_container_width=True, key="monthly_expenses_chart")
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


def apply_category_to_similar_transactions(db, transaction_details, category):
    """Apply a category to all similar transactions in the database.

    Args:
        db: Database session
        transaction_details: The details text of the transaction
        category: The category to apply

    Returns:
        int: Number of transactions updated
    """
    try:
        # Extract a vendor key from the transaction details
        def extract_vendor_key(details):
            """Extract a more effective vendor key from transaction details."""
            # Normalize and clean the text
            text = details.lower().strip()

            # Remove dates in various formats (MM/DD, YYYY-MM-DD, etc.)
            text = re.sub(r'\d{1,2}/\d{1,2}', '', text)
            text = re.sub(r'\d{4}-\d{1,2}-\d{1,2}', '', text)

            # Remove transaction IDs and reference numbers
            text = re.sub(r'ref\s*#?\s*\d+', '', text, flags=re.IGNORECASE)
            text = re.sub(r'transaction\s*#?\s*\d+',
                          '', text, flags=re.IGNORECASE)
            text = re.sub(r'id\s*#?\s*\d+', '', text, flags=re.IGNORECASE)

            # Remove special characters but keep spaces
            text = re.sub(r'[^\w\s]', '', text)

            # Remove common words that don't help identify the vendor
            common_words = ['purchase', 'payment', 'online', 'retail', 'store',
                            'service', 'fee', 'charge', 'debit', 'credit', 'transaction',
                            'interac', 'etransfer', 'transfer', 'withdrawal', 'deposit']
            words = text.split()
            filtered_words = [word for word in words
                              if word not in common_words and len(word) > 2]

            # If we have words left, join them; otherwise use the original text
            if filtered_words:
                return ' '.join(filtered_words)
            else:
                # Fallback to original text with minimal cleaning
                return ' '.join(text.split())

        # Get the vendor key
        vendor_key = extract_vendor_key(transaction_details)
        if not vendor_key:
            logger.warning(
                f"Could not extract vendor key from: {transaction_details}")
            return 0

        # Find all transactions with similar details
        similar_transactions = db.query(Transaction).filter(
            # Only update transactions with different categories
            Transaction.category != category,
            # Find transactions containing the vendor key
            Transaction.details.ilike(f"%{vendor_key}%")
        ).all()

        # Update the transactions
        updated_count = 0
        for trans in similar_transactions:
            logger.info(
                f"Updating category for similar transaction: {trans.details} from '{trans.category}' to '{category}'")
            trans.category = category
            db.add(trans)
            updated_count += 1

        if updated_count > 0:
            db.commit()
            logger.info(
                f"Updated {updated_count} similar transactions with category: {category}")

        return updated_count
    except Exception as e:
        logger.error(
            f"Error applying category to similar transactions: {str(e)}")
        db.rollback()
        return 0


def fix_td_statement_dates(db):
    """Fix month/year for TD bank statements."""
    try:
        updated = 0
        for pdf in db.query(PDFFile).filter(PDFFile.bank == 'TD').all():
            # Get the PDF content
            pdf_content = get_pdf_content(db, pdf.id)
            if pdf_content:
                # Extract text from first page
                with pdfplumber.open(io.BytesIO(pdf_content)) as pdf_doc:
                    text = pdf_doc.pages[0].extract_text()
                    if text:
                        # Look for TD statement date format
                        credit_card_match = re.search(
                            r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+(\d{4})", text)
                        if credit_card_match:
                            # Get first 3 letters of month
                            month = credit_card_match.group(1)[:3]
                            year = credit_card_match.group(2)
                            new_month_year = f"{month}_{year}"

                            if new_month_year != pdf.month_year:
                                logger.info(
                                    f"Updating month/year for {pdf.original_filename} from {pdf.month_year} to {new_month_year}")
                                pdf.month_year = new_month_year
                                db.add(pdf)
                                updated += 1

        if updated > 0:
            db.commit()
            return updated
        return 0
    except Exception as e:
        logger.error(f"Error fixing TD statement dates: {str(e)}")
        db.rollback()
        return 0


def normalize_category(category, db):
    mapping = db.query(CategoryMapping).filter_by(plaid_category=category).first()
    if mapping:
        return mapping.app_category
    # If not mapped, store and return the Plaid code or user input as-is
    return category
