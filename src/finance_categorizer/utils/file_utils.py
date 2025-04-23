import os
import json
import pdfplumber
import re
from datetime import datetime
import pandas as pd

VENDOR_FILE = "vendor_map.json"
SAVE_DIR = "saved_statements"


def ensure_directories():
    """Ensure necessary directories exist."""
    os.makedirs(SAVE_DIR, exist_ok=True)


def load_vendor_map():
    """Load vendor mapping from JSON file."""
    if os.path.exists(VENDOR_FILE):
        with open(VENDOR_FILE, "r") as f:
            return json.load(f)
    return {}


def save_vendor_map(mapping):
    """Save vendor mapping to JSON file."""
    with open(VENDOR_FILE, "w") as f:
        json.dump(mapping, f, indent=2)


def save_uploaded_file(uploaded_file):
    """Save uploaded PDF file to appropriate directory based on date."""
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
