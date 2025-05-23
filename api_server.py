import sys
import os
import logging
import traceback
from fastapi import FastAPI, HTTPException, Depends, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import Optional
from models import (
    get_db, save_transaction, get_all_transactions, save_vendor_mapping,
    get_all_vendor_mappings, update_transaction_category, init_db,
    save_pdf_file, get_pdf_files, get_pdf_content, PDFFile, VendorMapping,
    clear_all_data, get_latest_statement_balance, ensure_vendor_mappings, Transaction
)
from main import get_month_year_from_pdf, check_existing_statement, parse_pdf_transactions, auto_categorize_transactions

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
        logger.info(f"Total transactions retrieved: {len(transactions)}")
        
        if month:
            # Filter transactions by month if specified
            filtered_transactions = [
                t for t in transactions
                if t.date.strftime('%Y-%m') == month
            ]
            logger.info(f"Filtered transactions for month {month}: {len(filtered_transactions)}")
            transactions = filtered_transactions
            
        # Serialize transactions to dict
        serialized_transactions = []
        for t in transactions:
            serialized_transactions.append({
                "id": t.id,
                "date": t.date.isoformat() if t.date else None,
                "details": t.details,
                "amount": float(t.amount) if t.amount else None,
                "transaction_type": t.transaction_type,
                "category": t.category,
                "pdf_file_id": t.pdf_file_id,
                "bank": t.bank,
                "statement_type": t.statement_type
            })
        
        logger.info(f"Returning {len(serialized_transactions)} serialized transactions")
        # Log first few transactions for debugging
        for t in serialized_transactions[:3]:
            logger.info(f"Sample transaction: {t}")
            
        return serialized_transactions
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
async def update_transaction_category_api(
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


@api.get("/api/transactions/summary")
async def get_transaction_summary(db: Session = Depends(get_db)):
    try:
        transactions = get_all_transactions(db)
        total_income = sum(t.amount for t in transactions if t.transaction_type == 'Credit')
        total_expenses = sum(t.amount for t in transactions if t.transaction_type == 'Debit')
        net_balance = total_income - total_expenses
        return {
            "total_income": total_income,
            "total_expenses": total_expenses,
            "net_balance": net_balance
        }
    except Exception as e:
        logger.error(f"Error getting transaction summary: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(api, host="0.0.0.0", port=8001)
