import sys
import os
import logging
import traceback
from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, APIRouter, Request, Query, Form, Body
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import Optional
from models import (
    get_db, save_transaction, get_all_transactions, save_vendor_mapping,
    get_all_vendor_mappings, update_transaction_category, init_db,
    save_pdf_file, get_pdf_files, get_pdf_content, PDFFile, VendorMapping,
    clear_all_data, get_latest_statement_balance, ensure_vendor_mappings, Transaction, Account, PlaidItem,
    calculate_and_store_net_worth_snapshot, get_net_worth_history, NetWorthSnapshot,
    CategoryMapping, ensure_category_mappings, update_transaction_details, update_transaction_account, RecurringRule, SessionLocal
)
from main import get_month_year_from_pdf, check_existing_statement, parse_pdf_transactions, auto_categorize_transactions, normalize_category
from plaid.api import plaid_api
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.products import Products
from plaid.model.country_code import CountryCode
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.transactions_get_request import TransactionsGetRequest
from plaid import Configuration, ApiClient
from plaid.model.link_token_create_request_update import LinkTokenCreateRequestUpdate
from plaid.model.transactions_sync_request import TransactionsSyncRequest
import datetime
import time
import json
from sqlalchemy import func
from collections import defaultdict, Counter
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import Column, Integer, String, Boolean
from sqlalchemy.ext.declarative import declarative_base
from pydantic import BaseModel

from dotenv import load_dotenv
load_dotenv()

# Initialize database tables if needed (won't recreate if they exist)
init_db()

# Ensure category mappings are initialized
with SessionLocal() as db:
    ensure_category_mappings(db)

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

# Plaid configuration
PLAID_CLIENT_ID = os.getenv("PLAID_CLIENT_ID")
PLAID_SECRET = os.getenv("PLAID_SECRET")
PLAID_ENV = os.getenv("PLAID_ENV", "sandbox")  # 'sandbox', 'development', or 'production'

# Validate Plaid configuration
if not PLAID_CLIENT_ID or not PLAID_SECRET:
    logger.error("Missing Plaid credentials. Please set PLAID_CLIENT_ID and PLAID_SECRET environment variables.")
    raise ValueError("Missing Plaid credentials")

logger.info(f"Initializing Plaid client with environment: {PLAID_ENV}")

configuration = Configuration(
    host=f"https://{PLAID_ENV}.plaid.com",
    api_key={
        "clientId": PLAID_CLIENT_ID,
        "secret": PLAID_SECRET,
    }
)
api_client = ApiClient(configuration)
plaid_client = plaid_api.PlaidApi(api_client)

Base = getattr(__import__('models'), 'Base', None) or declarative_base()

# Add to models.py if not present, and ensure table is created

# Helper to check if a transaction matches a recurring rule
from sqlalchemy.orm import Session as OrmSession
from recurring_utils import is_recurring_by_rule

# API endpoints for recurring rules

@api.get('/api/recurring_rules')
def get_recurring_rules(db: Session = Depends(get_db)):
    rules = db.query(RecurringRule).all()
    return [
        {"id": r.id, "merchant": r.merchant, "match_type": r.match_type, "active": r.active, "recurrence_pattern": r.recurrence_pattern}
        for r in rules
    ]

@api.post('/api/recurring_rules')
def add_recurring_rule(
    merchant: str = Body(...),
    match_type: str = Body('exact'),
    recurrence_pattern: str = Body(None),
    db: Session = Depends(get_db)
):
    rule = RecurringRule(merchant=merchant, match_type=match_type, active=True, recurrence_pattern=recurrence_pattern)
    db.add(rule)
    db.commit()
    return {"status": "success", "rule": {"id": rule.id, "merchant": rule.merchant, "match_type": rule.match_type, "active": rule.active, "recurrence_pattern": rule.recurrence_pattern}}

class RecurrencePatternUpdate(BaseModel):
    recurrence_pattern: str

@api.put('/api/recurring_rules/{rule_id}')
def update_recurring_rule(rule_id: int, data: RecurrencePatternUpdate, db: Session = Depends(get_db)):
    rule = db.query(RecurringRule).filter_by(id=rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    if data.recurrence_pattern:
        rule.recurrence_pattern = data.recurrence_pattern
    db.commit()
    return {"status": "success", "rule": {"id": rule.id, "merchant": rule.merchant, "match_type": rule.match_type, "active": rule.active, "recurrence_pattern": rule.recurrence_pattern}}

@api.delete('/api/recurring_rules/{rule_id}')
def delete_recurring_rule(rule_id: int, db: Session = Depends(get_db)):
    rule = db.query(RecurringRule).filter_by(id=rule_id).first()
    if rule:
        db.delete(rule)
        db.commit()
        return {"status": "deleted"}
    return {"status": "not found"}

# API endpoints for mobile app


@api.get("/api/transactions")
async def get_transactions(
    month: Optional[str] = None,
    account_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get transactions with optional month and account_id filters"""
    try:
        transactions = get_all_transactions(db)
        
        if month:
            # Filter transactions by month if specified
            filtered_transactions = [
                t for t in transactions
                if t.date.strftime('%Y-%m') == month
            ]
            transactions = filtered_transactions
        
        if account_id:
            # Filter transactions by account_id if specified
            filtered_transactions = [
                t for t in transactions
                if t.account_id == account_id
            ]
            transactions = filtered_transactions
            
        # Serialize transactions to dict
        serialized_transactions = []
        for t in transactions:
            serialized_transactions.append({
                "id": t.id,
                "transaction_id": t.transaction_id,
                "date": t.date.isoformat() if t.date else None,
                "details": t.details,
                "amount": float(t.amount) if t.amount else None,
                "transaction_type": t.transaction_type,
                "category": t.category,
                "app_category": getattr(t, "app_category", None),
                "pdf_file_id": t.pdf_file_id,
                "bank": t.bank,
                "statement_type": t.statement_type,
                "account_id": t.account_id,
                "notes": t.notes,
                "is_recurring": getattr(t, "is_recurring", False),
            })
            
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
                if 'is_recurring' not in trans:
                    trans['is_recurring'] = is_recurring_by_rule(trans, db)
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


@api.put("/api/transactions/{transaction_id}")
async def update_transaction(
    transaction_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """Update transaction details (all fields)"""
    try:
        data = await request.json()
        transaction = db.query(Transaction).filter(Transaction.id == transaction_id).first()
        if not transaction:
            raise HTTPException(status_code=404, detail="Transaction not found")

        # Update all fields if present in the request
        if "name" in data:
            transaction.details = data["name"]
        if "amount" in data:
            transaction.amount = data["amount"]
        if "category" in data:
            transaction.category = data["category"]
        # Always update app_category after category is set
        transaction.app_category = normalize_category(transaction.category, db)
        if "date" in data:
            try:
                from dateutil.parser import parse as parse_date
                transaction.date = parse_date(data["date"])
            except Exception:
                pass
        if "notes" in data:
            transaction.notes = data["notes"]
        if "account_id" in data:
            transaction.account_id = data["account_id"]
        if "type" in data:
            t = data["type"].upper()
            if t == "EXPENSE":
                transaction.transaction_type = "Debit"
            elif t == "INCOME":
                transaction.transaction_type = "Credit"
            elif t == "TRANSFER":
                transaction.transaction_type = "Transfer"
            elif t == "BILL":
                transaction.transaction_type = "Bill"
        # Handle transfer flag - if is_transfer is True, set category to "Transfers"
        if "is_transfer" in data and data["is_transfer"]:
            transaction.category = "Transfers"
            logger.info(f"Transaction {transaction_id} marked as transfer")
        # PATCH: Allow updating is_recurring
        if "is_recurring" in data:
            transaction.is_recurring = data["is_recurring"]
        
        db.commit()
        return {"message": "Transaction updated successfully"}
    except Exception as e:
        logger.error(f"Error updating transaction: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@api.put("/api/transactions/{transaction_id}/account")
async def update_transaction_account_api(
    transaction_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """Update transaction account"""
    try:
        data = await request.json()
        account_id = data.get("account_id")
        
        if not account_id:
            raise HTTPException(status_code=400, detail="account_id field is required")

        success = update_transaction_account(db, transaction_id, account_id)
        
        if success:
            return {"message": "Transaction account updated successfully"}
        else:
            # Look up transaction and account for more detailed error
            transaction_exists = db.query(Transaction).filter(Transaction.id == transaction_id).first() is not None
            account_exists = db.query(Account).filter(Account.account_id == account_id).first() is not None
            raise HTTPException(status_code=404, detail="Transaction not found or account update failed (e.g., invalid account_id or transaction_id)")
    except HTTPException as http_exc: # Re-raise HTTPExceptions to preserve status code and detail
        raise http_exc
    except Exception as e:
        logger.error(f"Error updating transaction account for transaction_id {transaction_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


def is_transfer_transaction(transaction):
    """Check if a transaction is a transfer based on category, details, or type"""
    transfer_keywords = ['transfer', 'move', 'send', 'receive', 'wire', 'ach']
    details = transaction.details.lower() if transaction.details else ''
    category = transaction.category.lower() if transaction.category else ''
    
    return (category == 'transfers' or 
            any(keyword in details for keyword in transfer_keywords) or
            transaction.transaction_type == 'Transfer')

@api.get("/api/transactions/summary")
async def get_transaction_summary(db: Session = Depends(get_db)):
    try:
        transactions = get_all_transactions(db)
        
        # Exclude transfers from expense and income calculations
        non_transfer_transactions = [t for t in transactions if not is_transfer_transaction(t)]
        
        total_income = sum(t.amount for t in non_transfer_transactions if t.transaction_type == 'Credit')
        total_expenses = sum(t.amount for t in non_transfer_transactions if t.transaction_type == 'Debit')
        net_balance = total_income - total_expenses
        
        # Calculate transfers separately
        transfer_transactions = [t for t in transactions if is_transfer_transaction(t)]
        total_transfers = sum(t.amount for t in transfer_transactions)
        
        return {
            "total_income": total_income,
            "total_expenses": total_expenses,
            "net_balance": net_balance,
            "total_transfers": total_transfers,
            "transaction_count": len(transactions),
            "non_transfer_count": len(non_transfer_transactions),
            "transfer_count": len(transfer_transactions)
        }
    except Exception as e:
        logger.error(f"Error getting transaction summary: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@api.post("/api/plaid/create_link_token")
async def create_link_token(request: Request, db: Session = Depends(get_db)):
    try:
        data = await request.json()
        update_mode = data.get("update_mode")
        item_id = data.get("item_id")

        # For update mode, we need to get the access token from the database
        access_token = None
        if update_mode and item_id:
            # Find the PlaidItem in the database
            plaid_item = db.query(PlaidItem).filter_by(item_id=item_id).first()
            if plaid_item:
                access_token = plaid_item.access_token
            else:
                raise HTTPException(status_code=400, detail="Invalid item_id")

        # Create base request
        request = LinkTokenCreateRequest(
            user=LinkTokenCreateRequestUser(client_user_id="unique_user_id"),
            client_name="Finance App",
            products=[Products("transactions")],
            country_codes=[CountryCode("US"), CountryCode("CA")],
            language="en"
        )

        # Add update mode configuration if requested
        if update_mode and access_token:
            request.access_token = access_token

        try:
            response = plaid_client.link_token_create(request)
            return {"link_token": response["link_token"]}
        except Exception as plaid_error:
            logger.error(f"Plaid API error: {str(plaid_error)}")
            raise HTTPException(
                status_code=500,
                detail=f"Error creating Plaid link token: {str(plaid_error)}"
            )
    except Exception as e:
        logger.error(f"Error in create_link_token: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Server error creating link token: {str(e)}"
        )

@api.post("/api/plaid/exchange_public_token")
async def exchange_public_token(request: Request, db: Session = Depends(get_db)):
    data = await request.json()
    public_token = data.get("public_token")
    if not public_token:
        raise HTTPException(status_code=400, detail="Missing public_token")
    try:
        # Exchange public_token for access_token
        exchange_request = ItemPublicTokenExchangeRequest(public_token=public_token)
        exchange_response = plaid_client.item_public_token_exchange(exchange_request)
        access_token = exchange_response["access_token"]
        item_id = exchange_response["item_id"]

        # Fetch transactions (last 90 days) with retry logic for PRODUCT_NOT_READY
        start_date = (datetime.datetime.now() - datetime.timedelta(days=90)).date()
        end_date = datetime.datetime.now().date()
        
        max_retries = 5
        for attempt in range(max_retries):
            try:
                transactions_request = TransactionsGetRequest(
                    access_token=access_token,
                    start_date=start_date,
                    end_date=end_date,
                    options={"count": 500, "offset": 0}
                )
                transactions_response = plaid_client.transactions_get(transactions_request)
                # Log the full Plaid response (including accounts, balances, all transactions)
                try:
                    import json
                    resp_dict = transactions_response.to_dict() if hasattr(transactions_response, 'to_dict') else dict(transactions_response)
                    logger.info(f"Full Plaid transactions_get response: {json.dumps(serialize_dates(resp_dict), indent=2)[:10000]}")
                except Exception as log_exc:
                    logger.warning(f"Could not log full Plaid response: {log_exc}")
                transactions = transactions_response["transactions"]
                break
            except Exception as e:
                if "PRODUCT_NOT_READY" in str(e):
                    if attempt < max_retries - 1:
                        time.sleep(2 ** attempt)  # Exponential backoff
                        continue
                raise

        # Process accounts and transactions
        imported = 0
        skipped = 0

        # Process accounts
        accounts = transactions_response["accounts"]
        existing_account_map = {}
        
        for acct in accounts:
            account_key = f"{acct.get('account_id')}_{acct.get('name')}"
            existing_account = db.query(Account).filter_by(account_id=acct.get("account_id")).first()
            
            if existing_account:
                # Update existing account
                existing_account.name = acct.get("name")
                existing_account.official_name = acct.get("official_name")
                # Convert Plaid account types to strings
                existing_account.type = str(acct.get("type", ""))
                existing_account.subtype = str(acct.get("subtype", ""))
                existing_account.mask = acct.get("mask")
                existing_account.available_balance = acct.get("balances", {}).get("available")
                existing_account.current_balance = acct.get("balances", {}).get("current")
                existing_account.iso_currency_code = acct.get("balances", {}).get("iso_currency_code")
                existing_account.last_updated = datetime.datetime.utcnow()
                existing_account_map[account_key] = existing_account
            else:
                # Create new account
                new_account = Account(
                    account_id=acct.get("account_id"),
                    name=acct.get("name"),
                    official_name=acct.get("official_name"),
                    # Convert Plaid account types to strings
                    type=str(acct.get("type", "")),
                    subtype=str(acct.get("subtype", "")),
                    mask=acct.get("mask"),
                    available_balance=acct.get("balances", {}).get("available"),
                    current_balance=acct.get("balances", {}).get("current"),
                    iso_currency_code=acct.get("balances", {}).get("iso_currency_code"),
                    last_updated=datetime.datetime.utcnow(),
                    access_token=access_token
                )
                db.add(new_account)
                existing_account_map[account_key] = new_account

        db.commit()

        # Process transactions
        existing_transactions = db.query(Transaction).filter(
            Transaction.date >= start_date,
            Transaction.date <= end_date
        ).all()
        
        # Defensive check for None values
        if any(t is None for t in existing_transactions):
            logger.error("Found None in existing_transactions list")
        existing_transaction_map = {t.transaction_id: t for t in existing_transactions if t is not None}
        
        logger.info(f"Plaid returned {len(transactions)} transactions")
        for txn in transactions:
            try:
                if txn is None:
                    logger.error("Encountered None transaction in Plaid response")
                    continue
                required_keys = ["transaction_id", "date", "name", "amount", "account_id"]
                if not all(k in txn for k in required_keys):
                    logger.error(f"Missing expected keys in transaction: {txn}")
                    continue
                if txn["transaction_id"] in existing_transaction_map:
                    skipped += 1
                    continue
                date_val = txn["date"]
                if isinstance(date_val, str):
                    date_val = datetime.datetime.strptime(date_val, "%Y-%m-%d").date()
                cat = txn.get("category")
                if isinstance(cat, list) and cat:
                    category_val = cat[0]
                elif isinstance(cat, str):
                    category_val = cat
                else:
                    pf_cat = txn.get("personal_finance_category", {})
                    category_val = pf_cat.get("detailed") or "Other"
                # PATCH: Always set app_category
                app_category_val = normalize_category(cat, db)
                new_transaction = Transaction(
                    transaction_id=txn["transaction_id"],
                    date=date_val,
                    details=txn["name"],
                    amount=txn["amount"],
                    transaction_type="Debit" if txn["amount"] > 0 else "Credit",
                    category=category_val,
                    app_category=app_category_val,
                    account_id=txn["account_id"]
                )
                if 'is_recurring' not in new_transaction:
                    new_transaction.is_recurring = is_recurring_by_rule(new_transaction, db)
                db.add(new_transaction)
                imported += 1
            except Exception as e:
                logger.error(f"Error processing transaction: {txn} | Exception: {e}")
                continue
            
        db.commit()

        # Clear needs_update flag for PlaidItem and all its accounts
        plaid_item = db.query(PlaidItem).filter_by(item_id=item_id).first()
        if plaid_item:
            plaid_item.needs_update = False
            plaid_item.status = "good"  # Set status to good after successful update
            for account in plaid_item.accounts:
                account.needs_update = False
                db.add(account)
            db.add(plaid_item)
            db.commit()

        return {"status": "success", "transactions_imported": imported}
    except Exception as e:
        logger.error(f"Plaid exchange error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@api.get("/api/accounts")
async def get_accounts(db: Session = Depends(get_db)):
    """Get all Plaid accounts with balances and related transactions"""
    try:
        accounts = db.query(Account).all()
        result = []
        for acct in accounts:
            acct_dict = {
                "account_id": acct.account_id,
                "name": acct.name,
                "official_name": acct.official_name,
                "type": acct.type,
                "subtype": acct.subtype,
                "mask": acct.mask,
                "available_balance": acct.available_balance,
                "current_balance": acct.current_balance,
                "iso_currency_code": acct.iso_currency_code,
                "last_updated": acct.last_updated.isoformat() if acct.last_updated else None,
                "needs_update": acct.needs_update,
                "transactions": [
                    {
                        "id": t.id,
                        "transaction_id": t.transaction_id,
                        "date": t.date.isoformat() if hasattr(t, 'date') and t.date else str(t.date) if t.date else None,
                        "details": t.details,
                        "amount": t.amount,
                        "category": t.category,
                        "transaction_type": t.transaction_type,
                        "statement_type": t.statement_type,
                        "bank": t.bank
                    }
                    for t in acct.transactions
                ]
            }
            result.append(acct_dict)
        return result
    except Exception as e:
        logger.error(f"Error getting accounts: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api.post("/api/plaid/fetch_transactions")
async def fetch_transactions(db: Session = Depends(get_db)):
    try:
        plaid_item = db.query(PlaidItem).first()  # For multi-user, filter by user
        if not plaid_item:
            raise HTTPException(status_code=404, detail="No Plaid item found")
        if plaid_item.needs_update:
            return {
                "error": "ITEM_LOGIN_REQUIRED",
                "message": "Bank credentials need to be updated. Please use the update button to refresh your connection.",
                "item_id": plaid_item.item_id
            }
        access_token = plaid_item.access_token

        # Set end date to today
        end_date = datetime.datetime.now().date()
        
        # Set start date based on last_refresh
        if plaid_item.last_refresh:
            # Use the day after last_refresh as start_date
            start_date = plaid_item.last_refresh.date() + datetime.timedelta(days=1)
        else:
            # If no last_refresh, use 30 days ago
            start_date = end_date - datetime.timedelta(days=30)

        # Ensure start_date is before end_date
        if start_date >= end_date:
            # If start_date is today or in the future, use yesterday as start_date
            start_date = end_date - datetime.timedelta(days=1)

        logger.info(f"Fetching transactions from {start_date} to {end_date}")
        
        try:
            transactions_request = TransactionsGetRequest(
                access_token=access_token,
                start_date=start_date, 
                end_date=end_date,
                options={"count": 500, "offset": 0}
            )
            transactions_response = plaid_client.transactions_get(transactions_request)
            # Log the full Plaid response (including accounts, balances, all transactions)
            try:
                import json
                resp_dict = transactions_response.to_dict() if hasattr(transactions_response, 'to_dict') else dict(transactions_response)
                logger.info(f"Full Plaid transactions_get response: {json.dumps(serialize_dates(resp_dict), indent=2)[:10000]}")
            except Exception as log_exc:
                logger.warning(f"Could not log full Plaid response: {log_exc}")
            transactions = transactions_response["transactions"]

            imported = 0
            for txn in transactions:
                transaction_data = {
                    "transaction_id": txn.get("transaction_id"),
                    "account_id": txn.get("account_id"),
                    "date": txn["date"],
                    "details": txn.get("name", "Plaid Transaction"),
                    "amount": float(txn["amount"]),
                    "category": (
                        txn.get("personal_finance_category", {}).get("detailed")
                        or (txn.get("category") or ["Uncategorized"])[-1]
                    ),
                    "app_category": normalize_category(txn.get("category"), db),
                    "transaction_type": "Debit" if txn["amount"] > 0 else "Credit",
                    "bank":  plaid_item.institution_name,
                    "statement_type": "Plaid"
                }
                if 'is_recurring' not in transaction_data:
                    transaction_data['is_recurring'] = is_recurring_by_rule(transaction_data, db)
                plaid_id = txn.get("transaction_id")
                if plaid_id:
                    existing_transaction = db.query(Transaction).filter_by(transaction_id=plaid_id).first()
                    if not existing_transaction:
                        save_transaction(db, transaction_data)
                        imported += 1
                        logger.info(f"Imported new transaction: {transaction_data['details']} - ${transaction_data['amount']}")
                    else:
                        logger.info(f"Skipped existing transaction: {transaction_data['details']} - ${transaction_data['amount']}")
                else:
                    logger.warning(f"Skipped transaction without Plaid ID: {transaction_data['details']}")

            # Update last_refresh and clear needs_update
            plaid_item.last_refresh = datetime.datetime.utcnow()
            plaid_item.needs_update = False
            db.add(plaid_item)
            # Set all related accounts to needs_update=False
            for account in plaid_item.accounts:
                account.needs_update = False
                db.add(account)
            db.commit()
            
            return {
                "status": "success", 
                "transactions_imported": imported,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat()
            }
        except Exception as e:
            error_message = str(e)
            logger.error(f"Plaid API error: {error_message}")
            
            # Check for specific Plaid error codes in the error message
            if "ITEM_LOGIN_REQUIRED" in error_message:
                logger.warning("Plaid credentials need updating")
                plaid_item.status = "ITEM_LOGIN_REQUIRED"
                plaid_item.needs_update = True
                db.add(plaid_item)
                # Set all related accounts to needs_update=True
                for account in plaid_item.accounts:
                    account.needs_update = True
                    db.add(account)
                db.commit()
                return {
                        "error": "ITEM_LOGIN_REQUIRED",
                    "message": "Bank credentials need to be updated. Please use the update button to refresh your connection.",
                    "item_id": plaid_item.item_id
                }
            elif "PRODUCT_NOT_READY" in error_message:
                return {
                    "error": "PRODUCT_NOT_READY",
                    "message": "Transactions are still being processed. Please try again in a few minutes."
                }
            else:
                return {
                    "error": "PLAID_API_ERROR",
                    "message": f"Error fetching transactions: {error_message}"
                }
    except Exception as e:
        logger.error(f"Error in fetch_transactions: {str(e)}")
        logger.error(f"Stack trace: {traceback.format_exc()}")
        return {
            "error": "SERVER_ERROR",
            "message": f"Server error: {str(e)}"
        }

@api.get("/api/plaid/last_refresh")
async def get_last_refresh(db: Session = Depends(get_db)):
    plaid_item = db.query(PlaidItem).first()
    if not plaid_item or not plaid_item.last_refresh:
        return {"last_refresh": None}
    return {"last_refresh": plaid_item.last_refresh.isoformat()}

def backfill_net_worth_history(db: Session, start_date: datetime.date, end_date: datetime.date):
    """Backfill net worth history for a date range based on transactions."""
    logger.info(f"Starting net worth history backfill from {start_date} to {end_date}")
    
    # First, let's check if we have any transactions at all
    all_transactions = db.query(Transaction).all()
    logger.info(f"Total transactions in database: {len(all_transactions)}")
    if all_transactions:
        logger.info(f"Sample transaction: date={all_transactions[0].date}, amount={all_transactions[0].amount}, type={all_transactions[0].transaction_type}")
    
    current_date = start_date
    while current_date <= end_date:
        try:
            # Check if snapshot already exists for this date
            existing_snapshot = db.query(NetWorthSnapshot).filter(NetWorthSnapshot.date == current_date).first()
            
            if existing_snapshot:
                logger.debug(f"Snapshot already exists for {current_date}, skipping")
                current_date += datetime.timedelta(days=1)
                continue
            
            # Get all transactions up to this date
            transactions = db.query(Transaction).filter(
                Transaction.date <= current_date
            ).order_by(Transaction.date).all()
            
            logger.info(f"Processing {len(transactions)} transactions for date {current_date}")
            
            if not transactions:
                logger.warning(f"No transactions found for date {current_date}")
                # Create a snapshot with zero values
                snapshot = NetWorthSnapshot(
                    date=current_date,
                    total_assets=0,
                    total_liabilities=0,
                    net_worth=0
                )
                db.add(snapshot)
                db.commit()  # Commit after each snapshot to avoid long transactions
                current_date += datetime.timedelta(days=1)
                continue
            
            # Calculate assets and liabilities
            total_assets = 0
            total_liabilities = 0
            
            # Track running balances for each account
            account_balances = {}
            
            for txn in transactions:
                # Get the account for this transaction
                account = db.query(Account).filter(Account.account_id == txn.account_id).first()
                if not account:
                    logger.warning(f"No account found for transaction {txn.id}")
                    continue
                    
                # Initialize account balance if not exists
                if account.account_id not in account_balances:
                    account_balances[account.account_id] = 0
                
                # Update account balance
                if txn.transaction_type == "Debit":
                    account_balances[account.account_id] -= txn.amount
                else:  # Credit
                    account_balances[account.account_id] += txn.amount
                
                logger.debug(f"Transaction {txn.id}: {txn.transaction_type} ${txn.amount} for account {account.name}")
            
            # Sum up all account balances into assets and liabilities
            for account_id, balance in account_balances.items():
                account = db.query(Account).filter(Account.account_id == account_id).first()
                if not account:
                    continue
                    
                # Determine if this is a liability account
                is_liability = account.type.lower() in ['credit', 'loan'] or (
                    account.subtype and account.subtype.lower() in ['credit card', 'loan']
                )
                
                # Add to appropriate total
                if is_liability:
                    total_liabilities += balance
                    logger.debug(f"Liability account {account.name}: balance ${balance}")
                else:
                    total_assets += balance
                    logger.debug(f"Asset account {account.name}: balance ${balance}")
            
            net_worth = total_assets - total_liabilities
            
            logger.info(f"Date {current_date}: Assets=${total_assets}, Liabilities=${total_liabilities}, Net Worth=${net_worth}")
            
            # Create new snapshot
            snapshot = NetWorthSnapshot(
                date=current_date,
                total_assets=total_assets,
                total_liabilities=total_liabilities,
                net_worth=net_worth
            )
            db.add(snapshot)
            db.commit()  # Commit after each snapshot to avoid long transactions
            
        except Exception as e:
            logger.error(f"Error processing date {current_date}: {str(e)}")
            db.rollback()  # Rollback on error
        finally:
            current_date += datetime.timedelta(days=1)
    
    logger.info("Completed net worth history backfill")

@api.get("/api/networth/history")
async def networth_history(
    start: str = Query(None, description="Start date YYYY-MM-DD"),
    end: str = Query(None, description="End date YYYY-MM-DD"),
    interval: str = Query('daily', description="Interval: daily, weekly, biweekly, or monthly"),
    type: str = Query('networth', description="Type: networth, cash, or credit"),
    db: Session = Depends(get_db)
):
    try:
        # Parse dates
        start_date = datetime.datetime.strptime(start, "%Y-%m-%d").date() if start else None
        end_date = datetime.datetime.strptime(end, "%Y-%m-%d").date() if end else None
        
        # Get history for the requested interval and type
        history = get_net_worth_history(db, start_date, end_date, interval, history_type=type)
        
        if not history:
            logger.warning(f"No {type} data found for date range {start_date} to {end_date}")
            
        return history
        
    except Exception as e:
        logger.error(f"Error calculating {type} history: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Initialize scheduler
scheduler = BackgroundScheduler()

def calculate_daily_net_worth():
    """Calculate and store daily net worth snapshot"""
    try:
        db = SessionLocal()
        calculate_and_store_net_worth_snapshot(db)
        db.close()
    except Exception as e:
        logger.error(f"Error in daily net worth calculation: {str(e)}")

# Schedule daily net worth calculation at midnight
scheduler.add_job(
    calculate_daily_net_worth,
    CronTrigger(hour=0, minute=0),
    id='daily_net_worth',
    name='Calculate daily net worth snapshot',
    replace_existing=True
)

# Start the scheduler
scheduler.start()

@api.post("/api/transactions/fetch_custom")
async def fetch_custom_transactions(
    start_date: str = Query(..., description="Start date in YYYY-MM-DD format"),
    end_date: str = Query(..., description="End date in YYYY-MM-DD format"),
    db: Session = Depends(get_db)
):
    """Fetch transactions for a custom date range"""
    try:
        # Parse dates
        try:
            start = datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
            end = datetime.datetime.strptime(end_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(
                status_code=400, 
                detail="Invalid date format. Use YYYY-MM-DD"
            )

        # Validate date range
        if start > end:
            # Swap dates if start is after end
            start, end = end, start
            logger.info(f"Swapped dates to ensure correct order: {start} to {end}")

        # Validate dates are not in the future
        today = datetime.date.today()
        if start > today or end > today:
            raise HTTPException(
                status_code=400,
                detail="Dates cannot be in the future"
            )

        plaid_item = db.query(PlaidItem).first()  # For multi-user, filter by user
        if not plaid_item:
            raise HTTPException(status_code=404, detail="No Plaid item found")
        access_token = plaid_item.access_token

        logger.info(f"Fetching transactions from {start} to {end}")
        
        try:
            transactions_request = TransactionsGetRequest(
                access_token=access_token,
                start_date=start, 
                end_date=end,
                options={"count": 500, "offset": 0}
            )
            
            # Add retry logic for Plaid API calls
            max_retries = 3
            retry_delay = 5  # seconds
            
            for attempt in range(max_retries):
                try:
                    transactions_response = plaid_client.transactions_get(transactions_request)
                    # Log the full Plaid response (including accounts, balances, all transactions)
                    try:
                        import json
                        resp_dict = transactions_response.to_dict() if hasattr(transactions_response, 'to_dict') else dict(transactions_response)
                        logger.info(f"Full Plaid transactions_get response: {json.dumps(serialize_dates(resp_dict), indent=2)[:10000]}")
                    except Exception as log_exc:
                        logger.warning(f"Could not log full Plaid response: {log_exc}")
                    transactions = transactions_response["transactions"]
                    accounts = transactions_response.to_dict().get("accounts", [])
                    break
                except Exception as e:
                    if attempt < max_retries - 1:
                        logger.warning(f"Plaid API call failed (attempt {attempt + 1}/{max_retries}): {str(e)}")
                        time.sleep(retry_delay)
                        continue
                    else:
                        logger.error(f"Plaid API call failed after {max_retries} attempts: {str(e)}")
                        raise HTTPException(
                            status_code=500,
                            detail=f"Failed to fetch transactions from Plaid: {str(e)}"
                        )
            
           
            imported = 0
            for txn in transactions:
                transaction_data = {
                    "transaction_id": txn.get("transaction_id"),
                    "account_id": txn.get("account_id"),
                    "date": txn["date"],
                    "details": txn.get("name", "Plaid Transaction"),
                    "amount": float(txn["amount"]),
                    "category": (
                        txn.get("personal_finance_category", {}).get("detailed")
                        or (txn.get("category") or ["Uncategorized"])[-1]
                    ),
                    "app_category": normalize_category(txn.get("category"), db),
                    "transaction_type": "Debit" if txn["amount"] > 0 else "Credit",
                    "bank":  plaid_item.institution_name,
                    "statement_type": "Plaid"
                }
                if 'is_recurring' not in transaction_data:
                    transaction_data['is_recurring'] = is_recurring_by_rule(transaction_data, db)
                plaid_id = txn.get("transaction_id")
                if plaid_id:
                    existing_transaction = db.query(Transaction).filter_by(transaction_id=plaid_id).first()
                    if not existing_transaction:
                        save_transaction(db, transaction_data)
                        imported += 1
                        logger.info(f"Imported new transaction: {transaction_data['details']} - ${transaction_data['amount']}")
                    else:
                        logger.info(f"Skipped existing transaction: {transaction_data['details']} - ${transaction_data['amount']}")
                else:
                    logger.warning(f"Skipped transaction without Plaid ID: {transaction_data['details']}")

            # Update last_refresh
            plaid_item.last_refresh = datetime.datetime.utcnow()
            db.add(plaid_item)
            db.commit()
            
            return {
                "status": "success", 
                "transactions_imported": imported,
                "start_date": start_date,
                "end_date": end_date
            }
        except Exception as e:
            error_message = str(e)
            if "ITEM_LOGIN_REQUIRED" in error_message:
                logger.warning("Plaid credentials need updating")
                plaid_item.status = "ITEM_LOGIN_REQUIRED"
                db.add(plaid_item)
                db.commit()
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "ITEM_LOGIN_REQUIRED",
                        "message": "Bank credentials need to be updated. Please use the update button to refresh your connection."
                    }
                )
            logger.error(f"Error fetching transactions: {error_message}")
            raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Error in fetch_custom_transactions: {str(e)}")
        logger.error(f"Stack trace: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))

@api.post("/api/admin/clear_db")
async def clear_db_endpoint(db: Session = Depends(get_db)):
    try:
        clear_all_data(db)
        return {"status": "success", "message": "All data cleared."}
    except Exception as e:
        logger.error(f"Error clearing database: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@api.post("/api/transactions/backfill_app_category")
async def backfill_app_category(db: Session = Depends(get_db)):
    """Backfill app_category for all transactions using the current mapping, and return unmapped categories."""
    try:
        transactions = db.query(Transaction).all()
        updated = 0
        unmapped = set()
        for t in transactions:
            if not t.app_category or t.app_category == "Other":
                mapped = normalize_category(t.category, db)
                if mapped == "Other":
                    unmapped.add(t.category)
                t.app_category = mapped
                updated += 1
        db.commit()
        return {
            "status": "success",
            "updated": updated,
            "total": len(transactions),
            "unmapped_categories": list(unmapped)
        }
    except Exception as e:
        db.rollback()
        return {"status": "error", "error": str(e)}

@api.get("/api/category_mappings")
async def get_category_mappings(db: Session = Depends(get_db)):
    mappings = db.query(CategoryMapping).all()
    return [{"plaid_category": m.plaid_category, "app_category": m.app_category} for m in mappings]

@api.post("/api/category_mappings")
async def add_or_update_category_mapping(
    plaid_category: str = Form(...),
    app_category: str = Form(...),
    db: Session = Depends(get_db)
):
    mapping = db.query(CategoryMapping).filter_by(plaid_category=plaid_category).first()
    if mapping:
        mapping.app_category = app_category
    else:
        mapping = CategoryMapping(plaid_category=plaid_category, app_category=app_category)
        db.add(mapping)
    db.commit()

    # PATCH: Apply to all past transactions
    updated_count = db.query(Transaction).filter(Transaction.category == plaid_category).update({Transaction.app_category: app_category}, synchronize_session=False)
    db.commit()

    return {"status": "success", "updated_transactions": updated_count}

@api.delete("/api/category_mappings")
async def delete_category_mapping(plaid_category: str, db: Session = Depends(get_db)):
    mapping = db.query(CategoryMapping).filter_by(plaid_category=plaid_category).first()
    if mapping:
        db.delete(mapping)
        db.commit()
        return {"status": "deleted"}
    return {"status": "not found"}

@api.delete("/api/accounts/{account_id}")
async def delete_account(account_id: str, db: Session = Depends(get_db)):
    """Delete a Plaid account and its associated data"""
    try:
        # Find the account
        account = db.query(Account).filter_by(account_id=account_id).first()
        if not account:
            raise HTTPException(status_code=404, detail="Account not found")

        # Get the Plaid item
        plaid_item = account.plaid_item
        if not plaid_item:
            raise HTTPException(status_code=404, detail="Plaid item not found")

        # Delete all transactions associated with this account
        db.query(Transaction).filter_by(account_id=account_id).delete()

        # Delete the account
        db.delete(account)

        # If this was the last account for this Plaid item, delete the item too
        remaining_accounts = db.query(Account).filter_by(access_token=plaid_item.access_token).count()
        if remaining_accounts <= 1:  # <= 1 because we haven't committed the deletion yet
            db.delete(plaid_item)

        db.commit()
        return {"status": "success", "message": "Account deleted successfully"}
    except Exception as e:
        logger.error(f"Error deleting account: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@api.get("/api/plaid/items")
async def get_plaid_items(db: Session = Depends(get_db)):
    """Get all Plaid items with their associated accounts"""
    try:
        plaid_items = db.query(PlaidItem).all()
        result = []
        for item in plaid_items:
            item_dict = {
                "item_id": item.item_id,
                "institution_id": item.institution_id,
                "institution_name": item.institution_name,
                "last_refresh": item.last_refresh.isoformat() if item.last_refresh else None,
                "status": item.status,
                "needs_update": item.needs_update,
                "accounts": [
                    {
                        "account_id": acc.account_id,
                        "name": acc.name,
                        "type": acc.type,
                        "subtype": acc.subtype,
                        "needs_update": acc.needs_update
                    }
                    for acc in item.accounts
                ]
            }
            result.append(item_dict)
        return result
    except Exception as e:
        logger.error(f"Error getting Plaid items: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api.get("/api/debug/plaid_items")
async def debug_plaid_items(db: Session = Depends(get_db)):
    """Debug endpoint to view all Plaid items and their details"""
    try:
        plaid_items = db.query(PlaidItem).all()
        result = []
        for item in plaid_items:
            item_dict = {
                "item_id": item.item_id,
                "institution_id": item.institution_id,
                "institution_name": item.institution_name,
                "access_token": item.access_token[:10] + "..." if item.access_token else None,  # Show only first 10 chars for security
                "last_refresh": item.last_refresh.isoformat() if item.last_refresh else None,
                "status": item.status,
                "accounts": [
                    {
                        "account_id": acc.account_id,
                        "name": acc.name,
                        "type": acc.type,
                        "subtype": acc.subtype,
                        "current_balance": acc.current_balance,
                        "last_updated": acc.last_updated.isoformat() if acc.last_updated else None
                    }
                    for acc in item.accounts
                ]
            }
            result.append(item_dict)
        return result
    except Exception as e:
        logger.error(f"Error getting Plaid items: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api.post("/api/admin/trigger_update")
async def trigger_update(item_id: str = None, account_id: str = None, db: Session = Depends(get_db)):
    """
    Manually set needs_update=True for a Plaid item or account.
    """
    if item_id:
        item = db.query(PlaidItem).filter_by(item_id=item_id).first()
        if not item:
            raise HTTPException(status_code=404, detail="Plaid item not found")
        item.needs_update = True
        for account in item.accounts:
            account.needs_update = True
            db.add(account)
        db.add(item)
        db.commit()
        return {"status": "success", "message": f"needs_update set for item {item_id} and all its accounts"}
    elif account_id:
        account = db.query(Account).filter_by(account_id=account_id).first()
        if not account:
            raise HTTPException(status_code=404, detail="Account not found")
        account.needs_update = True
        db.add(account)
        db.commit()
        return {"status": "success", "message": f"needs_update set for account {account_id}"}
    else:
        raise HTTPException(status_code=400, detail="Must provide item_id or account_id")

@api.delete("/api/transactions/all")
async def delete_all_transactions(db: Session = Depends(get_db)):
    """Delete all transactions from the database (does not delete accounts or Plaid items)."""
    try:
        count = db.query(Transaction).delete()
        db.commit()
        return {"status": "success", "deleted": count}
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting all transactions: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@api.delete("/api/transactions/{transaction_id}")
async def delete_transaction(
    transaction_id: int,
    db: Session = Depends(get_db)
):
    """Delete a transaction"""
    try:
        transaction = db.query(Transaction).filter(Transaction.id == transaction_id).first()
        if not transaction:
            raise HTTPException(status_code=404, detail="Transaction not found")
        
        db.delete(transaction)
        db.commit()
        return {"message": "Transaction deleted successfully"}
    except Exception as e:
        logger.error(f"Error deleting transaction: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api.post("/api/plaid/sync_transactions")
async def sync_transactions(db: Session = Depends(get_db)):
    """Sync transactions using Plaid's /transactions/sync endpoint (recommended)."""
    try:
        plaid_item = db.query(PlaidItem).first()
        if not plaid_item:
            raise HTTPException(status_code=404, detail="No Plaid item found")
        access_token = plaid_item.access_token
        cursor = plaid_item.plaid_cursor

        # Only include cursor if it is not None
        if cursor:
            request = TransactionsSyncRequest(access_token=access_token, cursor=cursor)
        else:
            request = TransactionsSyncRequest(access_token=access_token)

        response = plaid_client.transactions_sync(request)
        # Log the full Plaid sync response (truncated for safety)
        try:
            import json
            resp_dict = response.to_dict() if hasattr(response, 'to_dict') else dict(response)
            logger.info(f"Plaid sync response keys: {list(resp_dict.keys())}")
            logger.info(f"First 3 added: {json.dumps(serialize_dates([t.to_dict() if hasattr(t, 'to_dict') else dict(t) for t in resp_dict.get('added', [])[:3]]), indent=2)}")
            logger.info(f"First 3 modified: {json.dumps(serialize_dates([t.to_dict() if hasattr(t, 'to_dict') else dict(t) for t in resp_dict.get('modified', [])[:3]]), indent=2)}")
            logger.info(f"First 3 removed: {json.dumps(serialize_dates(resp_dict.get('removed', [])[:3]), indent=2)}")
        except Exception as log_exc:
            logger.warning(f"Could not log full Plaid sync response: {log_exc}")

        added = response['added']
        modified = response['modified']
        removed = response['removed']
        next_cursor = response['next_cursor']

        # Add new transactions
        imported = 0
        for txn in added:
            txn_dict = txn.to_dict() if hasattr(txn, 'to_dict') else dict(txn)
            plaid_cat = txn_dict.get("personal_finance_category", {}).get("detailed")
            if not plaid_cat:
                cat_list = txn_dict.get("category")
                if isinstance(cat_list, list) and cat_list:
                    plaid_cat = cat_list[-1]
                elif isinstance(cat_list, str):
                    plaid_cat = cat_list
                else:
                    plaid_cat = "Other"
            transaction_data = {
                "transaction_id": txn_dict.get("transaction_id"),
                "account_id": txn_dict.get("account_id"),
                "date": txn_dict["date"],
                "details": txn_dict.get("name", "Plaid Transaction"),
                "amount": float(txn_dict["amount"]),
                "category": (
                    txn_dict.get("personal_finance_category", {}).get("detailed")
                    or (txn_dict.get("category") or ["Uncategorized"])[-1]
                ),
                "app_category": normalize_category(plaid_cat, db),
                "transaction_type": "Debit" if txn_dict["amount"] > 0 else "Credit",
                "bank": plaid_item.institution_name,
                "statement_type": "Plaid"
            }
            if 'is_recurring' not in transaction_data:
                transaction_data['is_recurring'] = is_recurring_by_rule(transaction_data, db)
            plaid_id = txn_dict.get("transaction_id")
            if plaid_id:
                existing_transaction = db.query(Transaction).filter_by(transaction_id=plaid_id).first()
                if not existing_transaction:
                    save_transaction(db, transaction_data)
                    imported += 1
                # else: skip (already exists)

        # Update modified transactions
        updated = 0
        for txn in modified:
            txn_dict = txn.to_dict() if hasattr(txn, 'to_dict') else dict(txn)
            plaid_cat = txn_dict.get("personal_finance_category", {}).get("detailed")
            if not plaid_cat:
                cat_list = txn_dict.get("category")
                if isinstance(cat_list, list) and cat_list:
                    plaid_cat = cat_list[-1]
                elif isinstance(cat_list, str):
                    plaid_cat = cat_list
                else:
                    plaid_cat = "Other"
            plaid_id = txn_dict.get("transaction_id")
            if plaid_id:
                existing_transaction = db.query(Transaction).filter_by(transaction_id=plaid_id).first()
                if existing_transaction:
                    # Update fields
                    existing_transaction.amount = float(txn_dict["amount"])
                    existing_transaction.date = txn_dict["date"]
                    existing_transaction.details = txn_dict.get("name", "Plaid Transaction")
                    existing_transaction.category = (
                        txn_dict.get("personal_finance_category", {}).get("detailed")
                        or (txn_dict.get("category") or ["Uncategorized"])[-1]
                    )
                    existing_transaction.app_category = normalize_category(plaid_cat, db)
                    existing_transaction.transaction_type = "Debit" if txn_dict["amount"] > 0 else "Credit"
                    db.add(existing_transaction)
                    updated += 1
        # Remove deleted transactions
        removed_count = 0
        for removed_txn in removed:
            if hasattr(removed_txn, 'to_dict'):
                removed_txn = removed_txn.to_dict()
            txn_id = removed_txn.get("transaction_id") if isinstance(removed_txn, dict) else removed_txn
            if txn_id:
                db.query(Transaction).filter_by(transaction_id=txn_id).delete()
                removed_count += 1

        # Update last_refresh and store the new cursor
        plaid_item.last_refresh = datetime.datetime.utcnow()
        plaid_item.plaid_cursor = next_cursor
        db.add(plaid_item)
        db.commit()
        return {
            "added": imported,
            "modified": updated,
            "removed": removed_count,
            "next_cursor": next_cursor
        }
    except Exception as e:
        logger.error(f"Error in sync_transactions: {str(e)}")
        logger.error(f"Stack trace: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))

@api.post("/api/plaid/backfill_transactions")
async def backfill_transactions(db: Session = Depends(get_db)):
    """One-time backfill: fetch all available transactions for the Plaid item and update the sync cursor."""
    try:
        plaid_item = db.query(PlaidItem).first()
        if not plaid_item:
            raise HTTPException(status_code=404, detail="No Plaid item found")
        access_token = plaid_item.access_token
        # Fetch up to 2 years of transactions (with pagination)
        end_date = datetime.datetime.now().date()
        start_date = end_date - datetime.timedelta(days=730)
        all_transactions = []
        offset = 0
        while True:
            transactions_request = TransactionsGetRequest(
                access_token=access_token,
                start_date=start_date,
                end_date=end_date,
                options={"count": 500, "offset": offset}
            )
            transactions_response = plaid_client.transactions_get(transactions_request)
            transactions = transactions_response["transactions"]
            all_transactions.extend(transactions)
            total_transactions = transactions_response["total_transactions"]
            if len(all_transactions) >= total_transactions:
                break
            offset += 500
        # Log the full Plaid response (truncated for safety)
        try:
            import json
            resp_dict = transactions_response.to_dict() if hasattr(transactions_response, 'to_dict') else dict(transactions_response)
            logger.info(f"Full Plaid transactions_get response: {json.dumps(serialize_dates(resp_dict), indent=2)[:10000]}")
        except Exception as log_exc:
            logger.warning(f"Could not log full Plaid response: {log_exc}")
        imported = 0
        for txn in all_transactions:
            transaction_data = {
                "transaction_id": txn.get("transaction_id"),
                "account_id": txn.get("account_id"),
                "date": txn["date"],
                "details": txn.get("name", "Plaid Transaction"),
                "amount": float(txn["amount"]),
                "category": (
                    txn.get("personal_finance_category", {}).get("detailed")
                    or (txn.get("category") or ["Uncategorized"])[-1]
                ),
                "app_category": normalize_category(txn.get("category"), db),
                "transaction_type": "Debit" if txn["amount"] > 0 else "Credit",
                "bank": plaid_item.institution_name,
                "statement_type": "Plaid"
            }
            if 'is_recurring' not in transaction_data:
                transaction_data['is_recurring'] = is_recurring_by_rule(transaction_data, db)
            plaid_id = txn.get("transaction_id")
            if plaid_id:
                existing_transaction = db.query(Transaction).filter_by(transaction_id=plaid_id).first()
                if not existing_transaction:
                    save_transaction(db, transaction_data)
                    imported += 1
        # After backfill, get the initial sync cursor
        sync_request = TransactionsSyncRequest(access_token=access_token)
        sync_response = plaid_client.transactions_sync(sync_request)
        next_cursor = sync_response['next_cursor']
        plaid_item.plaid_cursor = next_cursor
        db.add(plaid_item)
        db.commit()
        return {"status": "success", "transactions_imported": imported, "next_cursor": next_cursor}
    except Exception as e:
        logger.error(f"Error in backfill_transactions: {str(e)}")
        logger.error(f"Stack trace: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))

@api.post("/api/plaid/clear_cursor")
async def clear_plaid_cursor(db: Session = Depends(get_db)):
    """Clear the Plaid sync cursor for the PlaidItem (for troubleshooting or re-backfill)."""
    try:
        plaid_item = db.query(PlaidItem).first()
        if not plaid_item:
            raise HTTPException(status_code=404, detail="No Plaid item found")
        plaid_item.plaid_cursor = None
        db.add(plaid_item)
        db.commit()
        return {"status": "success", "message": "Plaid sync cursor cleared."}
    except Exception as e:
        db.rollback()
        logger.error(f"Error clearing Plaid cursor: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@api.post("/api/plaid/webhook")
async def plaid_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.json()
    webhook_type = payload.get("webhook_type")
    webhook_code = payload.get("webhook_code")
    item_id = payload.get("item_id")
    logger.info(f"Received Plaid webhook: {webhook_type} {webhook_code} for item {item_id}")

    if webhook_type == "TRANSACTIONS" and webhook_code == "SYNC_UPDATES_AVAILABLE":
        logger.info(f"SYNC_UPDATES_AVAILABLE for item {item_id}.l /transactions/sync for this item.")
        # Optionally, trigger a background sync here
    return {"status": "ok"}

@api.post("/api/transactions")
async def create_transaction(request: Request, db: Session = Depends(get_db)):
    """Create a new transaction (manual add)"""
    try:
        data = await request.json()
        # Map frontend fields to backend model fields
        transaction_data = {}
        transaction_data["transaction_id"] = data.get("id") or data.get("transaction_id")
        transaction_data["account_id"] = data.get("account_id")
        transaction_data["date"] = data.get("date")
        transaction_data["details"] = data.get("name") or data.get("details")
        transaction_data["amount"] = data.get("amount")
        transaction_data["category"] = data.get("category")
        # Unified mapping logic:
        transaction_data["app_category"] = normalize_category(transaction_data["category"], db)
        transaction_data["transaction_type"] = data.get("transaction_type") or ("Credit" if data.get("type", "").upper() == "INCOME" else "Debit")
        transaction_data["pdf_file_id"] = data.get("pdf_file_id")
        transaction_data["bank"] = data.get("bank")
        transaction_data["statement_type"] = data.get("statement_type")
        transaction_data["notes"] = data.get("notes")
        # PATCH: Save is_recurring if provided
        if "is_recurring" in data:
            transaction_data["is_recurring"] = data["is_recurring"]
        # Save transaction
        transaction = save_transaction(db, transaction_data)
        return {"status": "success", "transaction_id": transaction.id}
    except Exception as e:
        logger.error(f"Error creating transaction: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def detect_recurrence_pattern(dates):
    """Given a list of datetime.date objects, return 'weekly', 'biweekly', 'monthly', or 'irregular'."""
    if len(dates) < 2:
        return 'unknown'
    # Sort dates
    dates = sorted(dates)
    # Compute deltas in days
    deltas = [(dates[i] - dates[i-1]).days for i in range(1, len(dates))]
    if not deltas:
        return 'unknown'
    # Find the most common delta
    most_common = Counter(deltas).most_common(1)[0][0]
    if 6 <= most_common <= 8:
        return 'weekly'
    elif 12 <= most_common <= 16:
        return 'biweekly'
    elif 27 <= most_common <= 32:
        return 'monthly'
    else:
        return 'irregular'

@api.get('/api/recurring/patterns')
def get_recurring_patterns(db: Session = Depends(get_db)):
    """Return recurrence pattern and amount for each recurring merchant/description."""
    txns = db.query(Transaction).filter(Transaction.is_recurring == True).all()
    rules = {r.merchant.strip().lower(): r for r in db.query(RecurringRule).all()}
    groups = {}
    for t in txns:
        key = t.details.strip() if t.details else 'Other'
        key_lc = key.lower()
        if key not in groups:
            groups[key] = []
        groups[key].append(t)
    result = []
    for merchant, txns in groups.items():
        dates = [t.date.date() if hasattr(t.date, 'date') else t.date for t in txns if t.date]
        # Use user-set pattern if present
        rule = rules.get(merchant.strip().lower())
        if rule and rule.recurrence_pattern:
            pattern = rule.recurrence_pattern
        else:
            pattern = detect_recurrence_pattern(dates)
        amounts = [abs(float(t.amount)) for t in txns if t.amount is not None]
        amount = Counter(amounts).most_common(1)[0][0] if amounts else None
        result.append({
            'merchant': merchant,
            'pattern': pattern,
            'amount': amount,
            'count': len(txns),
            'rule_id': rule.id if rule else None,
        })
    return result

if __name__ == "__main__":
    import uvicorn
    import socket
    from contextlib import closing

    def find_free_port():
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
            s.bind(('', 0))
            s.listen(1)
            port = s.getsockname()[1]
            return port

    try:
        port = 8001
        uvicorn.run(api, host="0.0.0.0", port=port)
    except OSError as e:
        if "address already in use" in str(e).lower():
            try:
                free_port = find_free_port()
                uvicorn.run(api, host="127.0.0.1", port=free_port)
            except Exception as e:
                logger.error(f"Failed to start server: {str(e)}")
                raise
        else:
            logger.error(f"Failed to start server: {str(e)}")
            raise
