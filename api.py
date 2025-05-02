from fastapi import FastAPI, File, UploadFile, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
import io
from datetime import datetime
from typing import List, Dict
import pdfplumber
import re
from models import (
    get_db, save_transaction, get_all_transactions, save_vendor_mapping,
    get_all_vendor_mappings, update_transaction_category, save_pdf_file,
    get_pdf_files, get_pdf_content, Transaction, PDFFile,
    import_vendor_mappings_from_json, export_vendor_mappings_to_json
)
from pydantic import BaseModel
import logging

app = FastAPI(title="Finance Categorizer API")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TransactionBase(BaseModel):
    date: datetime
    details: str
    amount: float
    transaction_type: str
    category: str = "Uncategorized"


class VendorMappingBase(BaseModel):
    vendor_substring: str
    category: str


def classify_transaction_type(details: str) -> str:
    """Classify transaction type based on details."""
    text = details.lower()
    if "rewards" in text or "rebate" in text or "refund" in text:
        return "Credit"
    debit_keywords = ["retail", "debit", "purchase", "fulfill request",
                      "bill", "charge", "petro", "service", "withdrawal"]
    if any(k in text for k in debit_keywords):
        return "Debit"
    return "Credit"


def parse_pdf_transactions(pdf_content: bytes) -> List[Dict]:
    """Parse PDF transactions and return list of transaction dictionaries."""
    data = []
    try:
        current_date = None
        with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
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
                                "date": datetime.strptime(current_date + " 2025", "%b %d %Y"),
                                "details": details,
                                "amount": amount,
                                "transaction_type": trans_type,
                                "category": "Uncategorized"
                            })
                    else:
                        if data:
                            data[-1]["details"] += " " + line
    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"Error parsing PDF: {str(e)}")
    return data


def categorize_transaction(details: str, vendor_map: Dict) -> str:
    """Categorize a transaction based on vendor mapping."""
    if not details or not vendor_map:
        return "Uncategorized"

    # Normalize the transaction details
    details = details.lower().strip()

    # Try exact match first
    for vendor_substring, category in vendor_map.items():
        if vendor_substring == "__custom_categories__":
            continue
        if not isinstance(vendor_substring, str):
            continue
        if vendor_substring.lower() == details:
            return category

    # Try partial match with numbers and special characters
    for vendor_substring, category in vendor_map.items():
        if vendor_substring == "__custom_categories__":
            continue
        if not isinstance(vendor_substring, str):
            continue
        vendor_substring = vendor_substring.lower()
        if vendor_substring in details:
            return category

    # Try word-based match
    details_words = set(re.findall(r'\w+', details))
    for vendor_substring, category in vendor_map.items():
        if vendor_substring == "__custom_categories__":
            continue
        if not isinstance(vendor_substring, str):
            continue
        vendor_words = set(re.findall(r'\w+', vendor_substring.lower()))
        if vendor_words.issubset(details_words):
            return category

    return "Uncategorized"


@app.post("/vendor-mappings/import")
def import_vendor_mappings(db: Session = Depends(get_db)):
    """Import vendor mappings from vendor_map.json file."""
    try:
        # This endpoint is no longer needed since we're not using JSON files
        raise HTTPException(status_code=410, detail="This endpoint is no longer supported. Please use the database directly.")
    except Exception as e:
        logger.error(f"Error importing vendor mappings: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/upload-statement/")
async def upload_statement(
    file: UploadFile = File(...),
    auto_categorize: bool = True,
    db: Session = Depends(get_db)
):
    try:
        content = await file.read()
        month_year = datetime.now().strftime("%b_%Y")

        # Ensure we have a valid filename
        filename = file.filename
        if not filename:
            filename = f"statement_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"

        # Save PDF file with original filename
        pdf_file = save_pdf_file(db, filename, content, month_year)
        logger.info(f"Saved PDF file: {filename}")

        # Parse transactions from PDF
        transactions = parse_pdf_transactions(content)
        logger.info(f"Parsed {len(transactions)} transactions from PDF")

        if auto_categorize and transactions:
            # Ensure vendor mappings exist and get them
            vendor_map = ensure_vendor_mappings(db)
            logger.info(
                f"Found {len(vendor_map)} vendor mappings for categorization")

            # Categorize transactions
            categorized_count = 0
            for trans in transactions:
                original_category = trans.get("category", "Uncategorized")
                trans["category"] = categorize_transaction(
                    trans["details"], vendor_map)
                if trans["category"] != original_category:
                    categorized_count += 1
                trans["pdf_file_id"] = pdf_file.id
                save_transaction(db, trans)

            logger.info(f"Auto-categorized {categorized_count} transactions")

        return {
            "message": "Statement processed successfully",
            "pdf_id": pdf_file.id,
            "transactions_count": len(transactions),
            "categorized_count": categorized_count if auto_categorize else 0,
            "filename": pdf_file.original_filename
        }
    except Exception as e:
        logger.error(f"Error processing {filename}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/transactions/recategorize")
def recategorize_all_transactions(db: Session = Depends(get_db)):
    try:
        # Get all transactions and vendor mappings
        transactions = get_all_transactions(db)
        vendor_map = get_all_vendor_mappings(db)

        updated_count = 0
        for trans in transactions:
            new_category = categorize_transaction(trans.details, vendor_map)
            if new_category != trans.category:
                update_transaction_category(db, trans.id, new_category)
                updated_count += 1

        return {
            "message": "Recategorization complete",
            "total_transactions": len(transactions),
            "updated_count": updated_count
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/transactions/")
def get_transactions(db: Session = Depends(get_db)):
    try:
        transactions = get_all_transactions(db)
        return [
            {
                "id": t.id,
                "date": t.date,
                "details": t.details,
                "amount": t.amount,
                "transaction_type": t.transaction_type,
                "category": t.category,
                "pdf_file_id": t.pdf_file_id
            }
            for t in transactions
        ]
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/transactions/")
def create_transaction(
    transaction: TransactionBase,
    db: Session = Depends(get_db)
):
    try:
        transaction_dict = transaction.dict()
        saved_transaction = save_transaction(db, transaction_dict)
        return {"message": "Transaction saved", "id": saved_transaction.id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.put("/transactions/{transaction_id}/category")
def update_category(
    transaction_id: int,
    category: str,
    db: Session = Depends(get_db)
):
    try:
        transaction = update_transaction_category(db, transaction_id, category)
        if not transaction:
            raise HTTPException(
                status_code=404, detail="Transaction not found")
        return {"message": "Category updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/vendor-mappings/")
def get_mappings(db: Session = Depends(get_db)):
    try:
        return get_all_vendor_mappings(db)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/vendor-mappings/")
def create_mapping(
    mapping: VendorMappingBase,
    db: Session = Depends(get_db)
):
    try:
        saved_mapping = save_vendor_mapping(
            db, mapping.vendor_substring, mapping.category)
        return {"message": "Vendor mapping saved", "id": saved_mapping.id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/statements/")
def get_statements(db: Session = Depends(get_db)):
    try:
        statements = db.query(PDFFile).order_by(
            PDFFile.upload_date.desc()).all()
        return [
            {
                "id": s.id,
                "filename": s.original_filename,
                "upload_date": s.upload_date,
                "month_year": s.month_year
            }
            for s in statements
        ]
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/statements/{statement_id}/download")
def download_statement(statement_id: int, db: Session = Depends(get_db)):
    try:
        content = get_pdf_content(db, statement_id)
        if not content:
            raise HTTPException(status_code=404, detail="Statement not found")

        # Get the statement details
        statement = db.query(PDFFile).filter(
            PDFFile.id == statement_id).first()
        if not statement:
            raise HTTPException(status_code=404, detail="Statement not found")

        filename = statement.original_filename or f"statement_{statement_id}.pdf"

        return StreamingResponse(
            io.BytesIO(content),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
