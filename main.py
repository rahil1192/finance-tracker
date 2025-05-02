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
    SessionLocal, update_transaction_details
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
            os.path.join(os.path.dirname(sys.executable), "poppler", "bin")  # Check Python installation directory
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
        logger.error(f"Poppler check error: {str(e)}\n{traceback.format_exc()}")
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

                    # Year rollover
                    txn_month = post_month
                    txn_day = post_day
                    txn_year = statement_year
                    if txn_month == "dec" and statement_month == "jan":
                        txn_year -= 1

                    date_str = f"{txn_month} {txn_day} {txn_year}"

                    # Clean amount string
                    amount_str = f"-{amount_text}" if negative_sign == "-" else amount_text
                    amount_signed = float(amount_str.replace(",", ""))
                    amount = abs(amount_signed)
                    trans_type = "Debit" if amount_signed > 0 else "Credit"

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
        txn_year = statement_year
        if txn_month == "dec" and statement_month == "jan":
            txn_year -= 1
        date_str = f"{txn_month} {txn_day} {txn_year}"
        amount_signed = float(amt_str.replace(",", ""))
        amount = abs(amount_signed)
        trans_type = "Debit" if amount_signed > 0 else "Credit"
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
                            trans_type = classify_transaction_type(details)
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
        ocr_opening_balance, ocr_closing_balance = ocr_extract_balances(pdf_content)
        logger.info(f"OCR Balances - Opening: ${ocr_opening_balance:,.2f}, Closing: ${ocr_closing_balance:,.2f}")

        # Parse transactions and get balances from regular parsing
        with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
            first_page_text = pdf.pages[0].extract_text()
            bank_name, statement_type = detect_statement_format(first_page_text)
            logger.info(f"Detected Bank: {bank_name}, Statement Type: {statement_type}")

            if bank_name == "TD" and statement_type == "Credit Card":
                transactions, reg_opening_balance, reg_closing_balance = parse_td_credit_card_statement(pdf_content)
            elif bank_name == "CIBC" and statement_type == "Chequing or Savings":
                transactions, reg_opening_balance, reg_closing_balance = parse_td_chequing_statement(pdf_content)
            else:
                # Try advanced OCR for transactions
                st.warning("Using advanced OCR for transaction extraction...")
                transactions, reg_opening_balance, reg_closing_balance = advanced_ocr_extract(pdf_content)

            logger.info(f"Regular Parsing Balances - Opening: ${reg_opening_balance:,.2f}, Closing: ${reg_closing_balance:,.2f}")

            # Compare and select the most reliable balances
            opening_balance = select_most_reliable_balance(ocr_opening_balance, reg_opening_balance)
            closing_balance = select_most_reliable_balance(ocr_closing_balance, reg_closing_balance)

            # Log the selected balances
            if opening_balance > 0:
                st.info(f"Selected Opening Balance: ${opening_balance:,.2f}")
                if abs(ocr_opening_balance - reg_opening_balance) > 0.01 and ocr_opening_balance > 0 and reg_opening_balance > 0:
                    st.warning(f"Opening balance discrepancy detected - OCR: ${ocr_opening_balance:,.2f}, Regular: ${reg_opening_balance:,.2f}")

            if closing_balance > 0:
                st.info(f"Selected Closing Balance: ${closing_balance:,.2f}")
                if abs(ocr_closing_balance - reg_closing_balance) > 0.01 and ocr_closing_balance > 0 and reg_closing_balance > 0:
                    st.warning(f"Closing balance discrepancy detected - OCR: ${ocr_closing_balance:,.2f}, Regular: ${reg_closing_balance:,.2f}")

            return transactions, opening_balance, closing_balance

    except Exception as e:
        logger.error(f"Error in parse_pdf_transactions: {str(e)}")
        st.error("Error parsing PDF file. Please check the file format.")
        return [], 0.0, 0.0


def select_most_reliable_balance(ocr_balance: float, regular_balance: float) -> float:
    """Select the most reliable balance between OCR and regular parsing results."""
    # If both values are present and equal (within a small tolerance)
    if ocr_balance > 0 and regular_balance > 0:
        if abs(ocr_balance - regular_balance) < 0.01:  # 1 cent tolerance
            return ocr_balance  # They're effectively equal, return either
        else:
            # If they differ, prefer the regular parsing method as it's usually more reliable
            # But log the discrepancy for debugging
            logger.info(f"Balance discrepancy - OCR: ${ocr_balance:,.2f}, Regular: ${regular_balance:,.2f}")
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
if "uploaded_files_key" not in st.session_state:
    st.session_state.uploaded_files_key = 0
if "vendor_mappings_imported" not in st.session_state:
    st.session_state.vendor_mappings_imported = False

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
    2. Select months to view
    3. Categorize transactions
    4. View summaries and reports
    """)

    st.divider()
    st.subheader("🗓️ Filter by Month")

# Get all PDF files for statement filter
all_pdf_files = db.query(PDFFile).order_by(PDFFile.upload_date.desc()).all()
if all_pdf_files:
    # Create a list of statement options with file name and month/year
    statement_options = ["All Statements"] + [
        f"{pdf.original_filename} ({pdf.month_year})" for pdf in all_pdf_files
    ]
    
    # Initialize session state for statement filter if not exists
    if "selected_statements" not in st.session_state:
        st.session_state.selected_statements = ["All Statements"]
    
    # Add statement filter in sidebar after month filter
    st.sidebar.divider()
    st.sidebar.subheader("📄 Filter by Statement")
    selected_statements = st.sidebar.multiselect(
        "Select statements to view",
        options=statement_options,
        default=st.session_state.selected_statements,
        key="statement_filter"
    )
    st.session_state.selected_statements = selected_statements

# Get available months from the database
transactions = get_all_transactions(db)
if transactions:
    # Filter transactions based on selected statements if any
    if st.session_state.selected_statements and "All Statements" not in st.session_state.selected_statements:
        # Extract file names from selected statements (remove month/year part)
        selected_filenames = [s.split(" (")[0] for s in st.session_state.selected_statements]
        # Get PDF IDs for selected statements
        selected_pdf_ids = [pdf.id for pdf in all_pdf_files if pdf.original_filename in selected_filenames]
        # Filter transactions
        transactions = [t for t in transactions if getattr(t, "pdf_file_id", None) in selected_pdf_ids]

    df = pd.DataFrame([{
        'date': t.date,
        'details': t.details,
        'amount': t.amount,
        'transaction_type': t.transaction_type,
        'category': t.category,
        'transaction_id': t.id,
        'pdf_file_id': getattr(t, "pdf_file_id", None)  # Add PDF file ID to track source
    } for t in transactions])

    # Create MonthYear column for filtering
    df['MonthYear'] = df['date'].dt.strftime('%Y-%m')
    available_months = sorted(df['MonthYear'].unique(), reverse=True)
else:
    df = pd.DataFrame()
    available_months = []

# Store the selected months in session state using the callback
selected_months = st.sidebar.multiselect(
    "Select months to view",
    options=available_months,
    default=[],  # No default selection
    key="month_selector",
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

# Direct file uploader (no bank selection)
uploaded_files = st.sidebar.file_uploader(
    "Upload new statement PDFs",
    type=CONFIG['processing']['supported_file_types'],
    accept_multiple_files=True,
    help="Upload one or more PDF bank statements",
    key=f"file_uploader_{st.session_state.uploaded_files_key}"  # Use dynamic key
)

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

if uploaded_files and not st.session_state.upload_success:
    processed_files = 0
    for idx, file in enumerate(uploaded_files):
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
            if not df_display.empty:
                debits_df = df_display[df_display["transaction_type"] == "Debit"].copy()
                credits_df = df_display[df_display["transaction_type"] == "Credit"].copy()
            else:
                debits_df = pd.DataFrame()
                credits_df = pd.DataFrame()

            # Display tabs
            tab1, tab2, tab3, tab4, tab5 = st.tabs(
                ["🔄 Reconcile", "📈 Summary", "📉 Expenses", "📥 Payments", "📆 Monthly"])

            with tab1:
                st.subheader("🔄 Balance Reconciliation")
                # Add reconciliation section
                with st.expander("Statement Details", expanded=True):
                    col1, col2, col3 = st.columns(3)

                    # Get all PDF files regardless of month selection
                    pdf_files_query = db.query(PDFFile).order_by(PDFFile.upload_date.asc())
                    pdf_files_list = pdf_files_query.all()

                    # Filter PDFs based on selected statements
                    if st.session_state.selected_statements and "All Statements" not in st.session_state.selected_statements:
                        selected_filenames = [s.split(" (")[0] for s in st.session_state.selected_statements]
                        pdf_files_list = [pdf for pdf in pdf_files_list if pdf.original_filename in selected_filenames]
                        st.info(f"Showing reconciliation for selected statements: {', '.join(selected_filenames)}")

                    # Then apply month filter if selected
                    if selected_months:
                        db_month_formats = []
                        for month in selected_months:
                            year, month_num = month.split('-')
                            month_name = datetime.strptime(month_num, '%m').strftime('%b')
                            db_month_formats.append(f"{month_name}_{year}")
                        
                        pdf_files_list = [pdf for pdf in pdf_files_list if pdf.month_year in db_month_formats]
                        if st.session_state.selected_statements and "All Statements" not in st.session_state.selected_statements:
                            st.info(f"Further filtered by months: {', '.join(selected_months)}")
                        else:
                            st.info(f"Showing reconciliation for selected months: {', '.join(selected_months)}")
                    elif "All Statements" in st.session_state.selected_statements or not st.session_state.selected_statements:
                        st.info("Showing reconciliation for all statements")

                    if pdf_files_list:
                        # Add button to update bank names
                        if st.button("🔄 Update Bank Names", key="update_bank_names_btn"):
                            try:
                                updated_count = 0
                                for pdf in pdf_files_list:
                                    # Get transactions for this statement
                                    statement_transactions = [t for t in transactions if getattr(
                                        t, "pdf_file_id", None) == pdf.id]
                                    
                                    if statement_transactions:
                                        # Get the first transaction to determine bank
                                        first_trans = statement_transactions[0]
                                        if first_trans and first_trans.bank and first_trans.bank != pdf.bank:
                                            # Update the PDF file with the correct bank
                                            pdf.bank = first_trans.bank
                                            db.add(pdf)  # Ensure the PDF file is added to the session
                                            updated_count += 1
                                            logger.info(f"Updating bank for {pdf.original_filename} to {first_trans.bank}")
                                
                                if updated_count > 0:
                                    db.commit()
                                    logger.info(f"Successfully updated {updated_count} bank names")
                                    st.success(f"✅ Updated bank names for {updated_count} statements")
                                    # Force refresh of the page
                                    st.rerun()
                                else:
                                    st.info("No bank names needed updating")
                            except Exception as e:
                                logger.error(f"Error updating bank names: {str(e)}")
                                st.error("Error updating bank names. Please try again.")
                                db.rollback()

                        # Always show per-statement reconciliation table
                        statement_rows = []
                        for pdf in pdf_files_list:
                            statement_transactions = [t for t in transactions if getattr(
                                t, "pdf_file_id", None) == pdf.id]
                            
                            # Get the first transaction to determine bank and statement type
                            first_trans = statement_transactions[0] if statement_transactions else None
                            bank = pdf.bank if pdf.bank else (first_trans.bank if first_trans else "Unknown")
                            statement_type = first_trans.statement_type if first_trans else "Unknown"
                            
                            total_debits = sum(
                                t.amount for t in statement_transactions if t.transaction_type == "Debit")
                            total_credits = sum(
                                t.amount for t in statement_transactions if t.transaction_type == "Credit")
                            
                            # Calculate closing balance based on bank and statement type
                            if bank == "TD" and statement_type == "Credit Card":
                                # For TD Credit Cards: closing = opening + debits - credits
                                calculated_closing = (pdf.opening_balance or 0) + total_debits - total_credits
                            else:
                                # For other accounts: closing = opening - debits + credits
                                calculated_closing = (pdf.opening_balance or 0) - total_debits + total_credits
                            
                            difference = (pdf.closing_balance - calculated_closing) if pdf.closing_balance is not None else None

                            statement_rows.append({
                                "Statement": pdf.original_filename,
                                "Bank": bank,
                                "Statement Type": statement_type,
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
                            # Convert Month/Year to datetime for proper sorting
                            df_statements['Sort_Date'] = pd.to_datetime(df_statements['Month/Year'].apply(
                                lambda x: f"01_{x}" if '_' in x else x), format='%d_%b_%Y')
                            df_statements = df_statements.sort_values('Sort_Date')
                            df_statements = df_statements.drop('Sort_Date', axis=1)  # Remove the sorting column
                        
                        st.markdown("### Individual Statement Reconciliation")
                        st.dataframe(df_statements, use_container_width=True)
                    else:
                        st.warning("No statements found for reconciliation.")

            with tab2:
                st.subheader("📊 Total Summary")

                # Calculate totals
                total_debits = df_display[df_display["transaction_type"] == "Debit"]["amount"].sum()
                total_credits = df_display[df_display["transaction_type"] == "Credit"]["amount"].sum()
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
                st.plotly_chart(fig, use_container_width=True, key="monthly_cashflow_chart")

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
                st.plotly_chart(fig, use_container_width=True, key="financial_overview_chart")

            with tab3:
                st.subheader("✏️ Edit Debit Categories")
                st.markdown(
                    "_*ℹ️ Double Click on a transaction's Field to edit it.*_")

                # Category Management for Expenses
                with st.expander("🏷️ Manage Expense Categories"):
                    # Add new category section
                    new_category = st.text_input("New Category Name", key="expense_new_category_input")
                    if st.button("Add New Category", key="expense_add_new_category_btn"):
                        if new_category:
                            try:
                                # Create a unique vendor mapping for the category
                                temp_vendor = f"__temp_expense_{new_category.lower()}"
                                logger.info(f"Adding new expense category: {new_category}")
                                mapping = save_vendor_mapping(db, temp_vendor, new_category)
                                if mapping:
                                    # Force refresh of vendor mappings
                                    st.session_state.vendor_mappings = get_all_vendor_mappings(db)
                                    st.success(f"✅ Added new expense category: {new_category}")
                                    # Force a rerun to update all dropdowns
                                    st.rerun()
                                else:
                                    st.error("Failed to save the new category")
                            except Exception as e:
                                logger.error(f"Error adding new category: {str(e)}")
                                st.error(f"Error adding new category: {str(e)}")
                        else:
                            st.error("Please enter a category name")

                # Get existing vendor mappings
                vendor_map = st.session_state.vendor_mappings if "vendor_mappings" in st.session_state else get_all_vendor_mappings(db)
                if "vendor_mappings" not in st.session_state:
                    st.session_state.vendor_mappings = vendor_map
                    logger.info(f"Initialized vendor mappings with {len(vendor_map)} entries")

                # Get all unique categories for the dropdown
                all_categories = ["All"] + sorted(set([v for v in vendor_map.values() if v != "Uncategorized"]))

                # Display expense transactions
                if not debits_df.empty:
                    # Store previous state of the dataframe for comparison
                    if "previous_debits_df" not in st.session_state:
                        st.session_state.previous_debits_df = debits_df.copy()

                    # Add Select column for switching functionality
                    debits_df["Select"] = False

                    # Create a copy of the dataframe for display without transaction_id
                    display_df = debits_df[["Select", "date", "details", "amount", "category"]].copy()
                    # Store the transaction IDs in a separate column for internal use
                    display_df["_transaction_id"] = debits_df["transaction_id"]

                    edited_debits = st.data_editor(
                        display_df,
                        column_config={
                            "Select": st.column_config.CheckboxColumn(
                                "Select",
                                help="Select transactions to switch between debit/credit",
                                default=False,
                            ),
                            "category": st.column_config.SelectboxColumn(
                                "Category",
                                options=all_categories,
                                required=True
                            ),
                            "details": st.column_config.TextColumn(
                                "Details",
                                help="Transaction description",
                                width="large",
                                required=True
                            ),
                            "date": st.column_config.DateColumn(
                                "Date",
                                disabled=True
                            ),
                            "amount": st.column_config.NumberColumn(
                                "Amount",
                                disabled=True,
                                format="$%.2f"
                            ),
                            "_transaction_id": st.column_config.Column(
                                "ID",
                                disabled=True,
                                help="Internal transaction ID"
                            )
                        },
                        use_container_width=True,
                        hide_index=True,
                        key="debits_editor"
                    )

                    # Check for category and details changes and update automatically
                    if "previous_debits_df" in st.session_state:
                        updates = False
                        for idx, row in edited_debits.iterrows():
                            try:
                                # Find the matching previous row safely
                                prev_rows = st.session_state.previous_debits_df.loc[
                                    st.session_state.previous_debits_df['transaction_id'] == row['_transaction_id']
                                ]
                                
                                if not prev_rows.empty:
                                    prev_row = prev_rows.iloc[0]
                                    
                                    # Check for category changes
                                    if row['category'] != prev_row['category']:
                                        update_transaction_category(db, row['_transaction_id'], row['category'])
                                        # Create vendor mapping for auto-categorization
                                        vendor_substring = row['details'].lower()
                                        save_vendor_mapping(db, vendor_substring, row['category'])
                                        updates = True
                                    
                                    # Check for details changes
                                    if row['details'] != prev_row['details']:
                                        update_transaction_details(db, row['_transaction_id'], row['details'])
                                        updates = True
                            except Exception as e:
                                logger.error(f"Error processing row {idx}: {str(e)}")
                                continue
                        
                        if updates:
                            st.success("✅ Transaction updated automatically")
                            # Update the previous state
                            st.session_state.previous_debits_df = debits_df.copy()
                            st.rerun()

                    # Add switch button
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
                            selected_trans_ids = selected_rows["_transaction_id"].tolist()
                            
                            switched_count = 0
                            for trans_id in selected_trans_ids:
                                transaction = db.query(Transaction).filter(
                                    Transaction.id == trans_id).first()
                                if transaction:
                                    transaction.transaction_type = "Credit"
                                    switched_count += 1

                            if switched_count > 0:
                                db.commit()
                                st.success(f"Switched {switched_count} transaction(s) to Credit")
                                st.rerun()
                            else:
                                st.warning("No transactions were switched")

                    # Show expense summary
                    debit_summary = edited_debits.groupby("category")["amount"].sum().reset_index()
                    debit_summary = debit_summary.sort_values("amount", ascending=False)

                    st.subheader("📊 Expense Summary")
                    st.dataframe(debit_summary, use_container_width=True)

                    if not debit_summary.empty:
                        chart_type = st.radio("Choose Chart Type", [
                            "Pie Chart", "Bar Chart"], horizontal=True, key="debit_chart_type")
                        if chart_type == "Pie Chart":
                            fig = px.pie(debit_summary, values="amount",
                                         names="category", title="Expenses by Category", hole=0.4)
                        else:
                            fig = px.bar(debit_summary, x="category", y="amount",
                                         title="Expenses by Category", color="category")
                        st.plotly_chart(fig, use_container_width=True, key="debits_by_category_chart")
                    else:
                        st.info("No debit transactions found in the selected period.")

            with tab4:
                st.subheader("💳 Credit Transactions")
                st.markdown(
                    "_*ℹ️ Click on a transaction's 'Details' text below to edit it.*_")

                # Category Management for Credits (in expander)
                with st.expander("🏷️ Manage Income Categories"):
                    # Add new category section
                    new_category = st.text_input("New Category Name", key="income_new_category_input_tab4")
                    if st.button("Add New Category", key="income_add_new_category_btn_tab4"):
                        if new_category:
                            try:
                                # Create a unique vendor mapping for the category
                                temp_vendor = f"__temp_income_{new_category.lower()}"
                                logger.info(f"Adding new income category: {new_category}")
                                mapping = save_vendor_mapping(db, temp_vendor, new_category)
                                if mapping:
                                    # Force refresh of vendor mappings
                                    st.session_state.vendor_mappings = get_all_vendor_mappings(db)
                                    st.success(f"✅ Added new income category: {new_category}")
                                    # Force a rerun to update all dropdowns
                                    st.rerun()
                                else:
                                    st.error("Failed to save the new category")
                            except Exception as e:
                                logger.error(f"Error adding new category: {str(e)}")
                                st.error(f"Error adding new category: {str(e)}")
                        else:
                            st.error("Please enter a category name")

                    # Get existing vendor mappings
                    vendor_map = st.session_state.vendor_mappings if "vendor_mappings" in st.session_state else get_all_vendor_mappings(db)
                    if "vendor_mappings" not in st.session_state:
                        st.session_state.vendor_mappings = vendor_map
                        logger.info(f"Initialized vendor mappings with {len(vendor_map)} entries")

                    # Get all unique categories for the dropdown
                    all_categories = ["All"] + sorted(set([v for v in vendor_map.values() if v != "Uncategorized"]))

                # Display transactions table (outside expander)
                if not credits_df.empty:
                    # Store previous state of the dataframe for comparison
                    if "previous_credits_df" not in st.session_state:
                        st.session_state.previous_credits_df = credits_df.copy()

                    # Add Select column for switching functionality
                    credits_df["Select"] = False

                    # Create a copy of the dataframe for display without transaction_id
                    display_df = credits_df[["Select", "date", "details", "amount", "category"]].copy()
                    # Store the transaction IDs in a separate column for internal use
                    display_df["_transaction_id"] = credits_df["transaction_id"]

                    edited_credits = st.data_editor(
                        display_df,
                        column_config={
                            "Select": st.column_config.CheckboxColumn(
                                "Select",
                                help="Select transactions to switch between debit/credit",
                                default=False,
                            ),
                            "category": st.column_config.SelectboxColumn(
                                "Category",
                                options=all_categories,
                                required=True
                            ),
                            "details": st.column_config.TextColumn(
                                "Details",
                                help="Transaction description",
                                width="large",
                                required=True
                            ),
                            "date": st.column_config.DateColumn(
                                "Date",
                                disabled=True
                            ),
                            "amount": st.column_config.NumberColumn(
                                "Amount",
                                disabled=True,
                                format="$%.2f"
                            ),
                            "_transaction_id": st.column_config.Column(
                                "ID",
                                disabled=True,
                                help="Internal transaction ID"
                            )
                        },
                        use_container_width=True,
                        hide_index=True,
                        key="credits_editor_tab4"
                    )

                    # Check for category and details changes and update automatically
                    if "previous_credits_df" in st.session_state:
                        updates = False
                        for idx, row in edited_credits.iterrows():
                            try:
                                # Find the matching previous row safely
                                prev_rows = st.session_state.previous_credits_df.loc[
                                    st.session_state.previous_credits_df['transaction_id'] == row['_transaction_id']
                                ]
                                
                                if not prev_rows.empty:
                                    prev_row = prev_rows.iloc[0]
                                    
                                    # Check for category changes
                                    if row['category'] != prev_row['category']:
                                        update_transaction_category(db, row['_transaction_id'], row['category'])
                                        # Create vendor mapping for auto-categorization
                                        vendor_substring = row['details'].lower()
                                        save_vendor_mapping(db, vendor_substring, row['category'])
                                        updates = True
                                    
                                    # Check for details changes
                                    if row['details'] != prev_row['details']:
                                        update_transaction_details(db, row['_transaction_id'], row['details'])
                                        updates = True
                            except Exception as e:
                                logger.error(f"Error processing row {idx}: {str(e)}")
                                continue
                        
                        if updates:
                            st.success("✅ Transaction updated automatically")
                            # Update the previous state
                            st.session_state.previous_credits_df = credits_df.copy()
                            st.rerun()

                    # Add switch button
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
                            selected_trans_ids = selected_rows["_transaction_id"].tolist()
                            
                            switched_count = 0
                            for trans_id in selected_trans_ids:
                                transaction = db.query(Transaction).filter(
                                    Transaction.id == trans_id).first()
                                if transaction:
                                    transaction.transaction_type = "Debit"
                                    switched_count += 1

                            if switched_count > 0:
                                db.commit()
                                st.success(f"Switched {switched_count} transaction(s) to Debit")
                                st.rerun()
                            else:
                                st.warning("No transactions were switched")

                    # Show income summary
                    credit_summary = edited_credits.groupby("category")["amount"].sum().reset_index()
                    credit_summary = credit_summary.sort_values("amount", ascending=False)

                    st.subheader("📊 Income Summary")
                    st.dataframe(credit_summary, use_container_width=True)

                    if not credit_summary.empty:
                        chart_type = st.radio("Choose Chart Type", [
                            "Pie Chart", "Bar Chart"], horizontal=True, key="credit_chart_type")
                        if chart_type == "Pie Chart":
                            fig = px.pie(credit_summary, values="amount",
                                         names="category", title="Income by Category", hole=0.4)
                        else:
                            fig = px.bar(credit_summary, x="category", y="amount",
                                         title="Income by Category", color="category")
                        st.plotly_chart(fig, use_container_width=True, key="credits_by_category_chart")
                    else:
                        st.info("No credit transactions found in the selected period.")

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
                        st.plotly_chart(chart, use_container_width=True, key="monthly_expenses_chart")
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
