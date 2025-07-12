from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, JSON, LargeBinary, inspect, ForeignKey, Text, Boolean, Date, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import json
from pathlib import Path
import yaml
import os
import logging
from sqlalchemy import text
from sqlalchemy.orm import Session
from recurring_utils import is_recurring_by_rule

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


def load_config():
    config_path = Path("config.yaml")
    if not config_path.exists():
        return {}
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


CONFIG = load_config()

# Database configuration for Render
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Fallback to SQLite for local development
if not DATABASE_URL:
    DATABASE_URL = "sqlite:///./finance_tracker.db"

logger.info(f"Using database: {DATABASE_URL}")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Database session dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class PDFFile(Base):
    __tablename__ = "pdf_files"

    id = Column(Integer, primary_key=True, index=True)
    original_filename = Column(String, nullable=False)
    month_year = Column(String)
    upload_date = Column(DateTime, default=datetime.utcnow)
    content = Column(Text)  # Store PDF content as base64
    opening_balance = Column(Float)
    closing_balance = Column(Float)
    account = Column(String)  # Account holder name
    bank = Column(String)  # Bank name
    statement_type = Column(String)  # "Credit Card", "Chequing", "Savings"

    # Relationships
    transactions = relationship("Transaction", back_populates="pdf_file")


class Account(Base):
    __tablename__ = "accounts"
    id = Column(Integer, primary_key=True)
    account_id = Column(String, unique=True, nullable=False)  # Plaid account_id
    name = Column(String)
    official_name = Column(String)
    type = Column(String)
    subtype = Column(String)
    mask = Column(String)
    available_balance = Column(Float)
    current_balance = Column(Float)
    iso_currency_code = Column(String)
    last_updated = Column(DateTime, nullable=True)
    access_token = Column(String, ForeignKey("plaid_items.access_token"))
    transactions = relationship("Transaction", back_populates="account")
    plaid_item = relationship("PlaidItem", back_populates="accounts")
    needs_update = Column(Boolean, default=False)


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    transaction_id = Column(String)  # Plaid transaction_id
    account_id = Column(String, ForeignKey("accounts.account_id"))
    date = Column(DateTime, nullable=False)
    details = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    category = Column(String, default="Uncategorized")
    app_category = Column(String, default="Other")  # Normalized category for app use
    transaction_type = Column(String, nullable=False)  # "Debit" or "Credit"
    pdf_file_id = Column(Integer, ForeignKey("pdf_files.id"))
    bank = Column(String)
    statement_type = Column(String)
    notes = Column(String, nullable=True)
    is_recurring = Column(Boolean, default=False)

    # Relationships
    pdf_file = relationship("PDFFile", back_populates="transactions")
    account = relationship("Account", back_populates="transactions")

    # Add unique constraint for duplicate detection
    __table_args__ = (
        UniqueConstraint('account_id', 'date', 'details', 'amount', 'transaction_type', 
                        name='unique_transaction'),
    )


class VendorMapping(Base):
    __tablename__ = "vendor_mappings"

    id = Column(Integer, primary_key=True, index=True)
    vendor_substring = Column(String, unique=True, nullable=False)
    category = Column(String, nullable=False)


class PlaidItem(Base):
    __tablename__ = "plaid_items"
    id = Column(Integer, primary_key=True)
    access_token = Column(String, unique=True, nullable=False)
    item_id = Column(String, unique=True, nullable=False)
    institution_id = Column(String)
    institution_name = Column(String)
    last_refresh = Column(DateTime, nullable=True, default=None)
    status = Column(String, nullable=True)  # Track update status
    accounts = relationship("Account", back_populates="plaid_item")
    needs_update = Column(Boolean, default=False)
    plaid_cursor = Column(String, nullable=True)  # For Plaid /transactions/sync


class NetWorthSnapshot(Base):
    __tablename__ = "net_worth_snapshots"
    
    id = Column(Integer, primary_key=True)
    date = Column(Date, nullable=False, index=True)
    total_assets = Column(Float, nullable=False)
    total_liabilities = Column(Float, nullable=False)
    net_worth = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('date', name='unique_date_snapshot'),
    )

class CategoryMapping(Base):
    __tablename__ = "category_mappings"
    id = Column(Integer, primary_key=True)
    plaid_category = Column(String, unique=True, nullable=False)
    app_category = Column(String, nullable=False)

class RecurringRule(Base):
    __tablename__ = 'recurring_rules'
    id = Column(Integer, primary_key=True)
    merchant = Column(String)
    match_type = Column(String, default='exact')  # 'exact', 'contains', 'regex'
    active = Column(Boolean, default=True)
    recurrence_pattern = Column(String, default=None)  # 'weekly', 'biweekly', 'monthly', etc.

def save_vendor_mapping(db, vendor_substring, category):
    """Save a vendor mapping to the database."""
    try:
        logger.info(
            f"Attempting to save vendor mapping: {vendor_substring} -> {category}")
        mapping = db.query(VendorMapping).filter(
            VendorMapping.vendor_substring == vendor_substring).first()
        if mapping:
            logger.info(
                f"Updating existing mapping: {mapping.vendor_substring} -> {category}")
            mapping.category = category
        else:
            logger.info(
                f"Creating new mapping: {vendor_substring} -> {category}")
            mapping = VendorMapping(
                vendor_substring=vendor_substring, category=category)
            db.add(mapping)
        db.commit()
        logger.info(
            f"Successfully saved vendor mapping: {vendor_substring} -> {category}")
        return mapping
    except Exception as e:
        logger.error(f"Error saving vendor mapping: {str(e)}")
        db.rollback()
        raise e

def init_db():
    """Initialize the database and handle schema updates."""
    try:
        # Check if database file exists
        if not os.path.exists('finance.db'):
            # First time initialization
            Base.metadata.create_all(bind=engine)
            logger.info("Created new database tables")

            # Add some default vendor mappings
            db = SessionLocal()
            try:
                default_mappings = {
                    "groceries": "Groceries",
                    "restaurant": "Dining",
                    "gas": "Transportation",
                    "uber": "Transportation",
                    "lyft": "Transportation",
                    "amazon": "Shopping",
                    "walmart": "Shopping",
                    "target": "Shopping",
                    "netflix": "Entertainment",
                    "spotify": "Entertainment",
                    "hulu": "Entertainment",
                    "disney": "Entertainment",
                    "rent": "Housing",
                    "mortgage": "Housing",
                    "utilities": "Utilities",
                    "electric": "Utilities",
                    "water": "Utilities",
                    "gas": "Utilities",
                    "internet": "Utilities",
                    "phone": "Utilities",
                    "salary": "Income",
                    "payroll": "Income",
                    "deposit": "Income",
                    "transfer": "Transfer",
                    "payment": "Payment"
                }

                for vendor, category in default_mappings.items():
                    save_vendor_mapping(db, vendor, category)
                logger.info("Added default vendor mappings")
            except Exception as e:
                logger.error(f"Error adding default vendor mappings: {str(e)}")
            finally:
                db.close()
        else:
            # Database exists, check for schema updates
            inspector = inspect(engine)
            existing_tables = inspector.get_table_names()

            # For each table in our models
            for table in Base.metadata.sorted_tables:
                if table.name not in existing_tables:
                    # Create missing table
                    table.create(engine)
                    logger.info(f"Created missing table: {table.name}")
                else:
                    # Check for missing columns
                    existing_columns = {col['name']
                                        for col in inspector.get_columns(table.name)}
                    model_columns = {col.name for col in table.columns}
                    missing_columns = model_columns - existing_columns

                    if missing_columns:
                        logger.info(
                            f"Adding missing columns to {table.name}: {missing_columns}")
                        with engine.begin() as connection:
                            for column_name in missing_columns:
                                column = next(
                                    col for col in table.columns if col.name == column_name)
                                # Add column with appropriate type and nullability
                                connection.execute(text(
                                    f"ALTER TABLE {table.name} ADD COLUMN {column_name} "
                                    f"{column.type.compile(engine.dialect)} "
                                    f"{'NOT NULL' if not column.nullable else ''}"
                                ))
                                logger.info(
                                    f"Added column {column_name} to {table.name}")
    except Exception as e:
        logger.error(f"Error initializing/updating database: {str(e)}")
        raise


# Initialize or update database
init_db()

# Helper functions for database operations


def save_pdf_file(db, filename, content, month_year, opening_balance=None, closing_balance=None, account=None, bank=None, statement_type=None):
    """Save a PDF file to the database.

    Args:
        db: Database session
        filename: Original name of the uploaded file
        content: Base64 content of the PDF file
        month_year: Month and year of the statement
        opening_balance: Opening balance from the statement
        closing_balance: Closing balance from the statement
        account: Account/family member name (optional)
        bank: Bank from the statement
        statement_type: Type of statement (Credit Card, Chequing, Savings)

    Returns:
        PDFFile: The saved PDF file object
    """
    try:
        pdf_file = PDFFile(
            original_filename=filename,
            content=content,
            month_year=month_year,
            opening_balance=opening_balance,
            closing_balance=closing_balance,
            account=account,
            bank=bank,
            statement_type=statement_type
        )
        db.add(pdf_file)
        db.commit()
        db.refresh(pdf_file)
        return pdf_file
    except Exception as e:
        db.rollback()
        raise Exception(f"Error saving PDF file: {str(e)}")


def get_pdf_files(db):
    """Get all PDF files ordered by upload date."""
    return db.query(PDFFile).order_by(PDFFile.upload_date.desc()).all()


def get_pdf_content(db, pdf_id):
    """Get PDF content by ID."""
    pdf_file = db.query(PDFFile).filter(PDFFile.id == pdf_id).first()
    return pdf_file.content if pdf_file else None


def save_transaction(db, transaction_data):
    # Remove is_recurring from transaction_data to avoid double-setting
    is_recurring = transaction_data.pop('is_recurring', None)
    transaction = Transaction(**transaction_data)
    # If explicitly set, use it; otherwise, check rules
    if is_recurring is not None:
        transaction.is_recurring = is_recurring
    else:
        if is_recurring_by_rule(transaction, db):
            transaction.is_recurring = True
    db.add(transaction)
    db.commit()
    db.refresh(transaction)
    return transaction


def get_all_transactions(db):
    try:
        return db.query(Transaction).order_by(Transaction.date.desc()).all()
    except Exception as e:
        logger.error(f"Error getting transactions: {str(e)}")
        return []


def get_all_vendor_mappings(db):
    """Get all vendor mappings from the database."""
    try:
        mappings = {m.vendor_substring: m.category for m in db.query(
            VendorMapping).all()}
        logger.info(f"Retrieved {len(mappings)} vendor mappings from database")
        return mappings
    except Exception as e:
        logger.error(f"Error getting vendor mappings: {str(e)}")
        return {}


def update_transaction_category(db, transaction_id, category):
    transaction = db.query(Transaction).filter(
        Transaction.id == transaction_id).first()
    if transaction:
        transaction.category = category
        db.commit()
    return transaction


def import_vendor_mappings_from_json(db):
    """Import vendor mappings from vendor_map.json into the database."""
    try:
        # Get the absolute path to vendor_map.json
        current_dir = os.path.dirname(os.path.abspath(__file__))
        vendor_map_path = os.path.join(current_dir, 'vendor_map.json')

        if not os.path.exists(vendor_map_path):
            vendor_map_path = 'vendor_map.json'  # Try current directory
            if not os.path.exists(vendor_map_path):
                raise FileNotFoundError("vendor_map.json not found")

        with open(vendor_map_path, 'r', encoding='utf-8') as f:
            mappings = json.load(f)

        # Clear existing mappings first
        db.query(VendorMapping).delete()
        db.commit()

        # Import new mappings
        imported_count = 0
        for vendor, category in mappings.items():
            if vendor == "__custom_categories__":
                continue
            if not isinstance(vendor, str) or not isinstance(category, str):
                continue

            # Normalize the vendor string
            vendor = ' '.join(vendor.lower().split())
            save_vendor_mapping(db, vendor, category)
            imported_count += 1

        return imported_count
    except Exception as e:
        db.rollback()
        raise Exception(f"Error importing vendor mappings: {str(e)}")


def clear_all_data(db):
    """Clear all data from all tables in the database."""
    try:
        # Delete all records from each table in the correct order
        db.query(Transaction).delete()
        db.query(NetWorthSnapshot).delete()
        db.query(Account).delete()
        db.query(PlaidItem).delete()
        db.query(PDFFile).delete()
        db.query(VendorMapping).delete()
        db.commit()
        logger.info("Successfully cleared all data from the database")
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"Error clearing database: {str(e)}")
        raise Exception(f"Error clearing database: {str(e)}")


def get_latest_statement_balance(db):
    """Get the closing balance from the most recently uploaded statement."""
    try:
        latest_statement = db.query(PDFFile).order_by(
            PDFFile.upload_date.desc()).first()
        return latest_statement.closing_balance if latest_statement else None
    except Exception as e:
        logger.error(f"Error getting latest statement balance: {str(e)}")
        return None


def ensure_vendor_mappings(db):
    """Ensure vendor mappings exist in the database."""
    try:
        mappings = get_all_vendor_mappings(db)
        logger.info(f"Retrieved {len(mappings)} vendor mappings from database")

        if not mappings:
            logger.info("No vendor mappings found in database")
            # Try to import from JSON file
            try:
                import_vendor_mappings_from_json(db)
                mappings = get_all_vendor_mappings(db)
                logger.info(
                    f"After import, retrieved {len(mappings)} vendor mappings")
            except Exception as e:
                logger.warning(
                    f"Failed to import vendor mappings from JSON file: {str(e)}")

                # Add some default mappings if nothing else worked
                default_mappings = {
                    "groceries": "Groceries",
                    "restaurant": "Dining",
                    "gas": "Transportation",
                    "uber": "Transportation",
                    "lyft": "Transportation",
                    "amazon": "Shopping",
                    "walmart": "Shopping",
                    "target": "Shopping",
                    "netflix": "Entertainment",
                    "spotify": "Entertainment",
                    "hulu": "Entertainment",
                    "disney": "Entertainment",
                    "rent": "Housing",
                    "mortgage": "Housing",
                    "utilities": "Utilities",
                    "electric": "Utilities",
                    "water": "Utilities",
                    "gas": "Utilities",
                    "internet": "Utilities",
                    "phone": "Utilities",
                    "salary": "Income",
                    "payroll": "Income",
                    "deposit": "Income",
                    "transfer": "Transfer",
                    "payment": "Payment"
                }

                for vendor, category in default_mappings.items():
                    save_vendor_mapping(db, vendor, category)

                logger.info("Added default vendor mappings")
                mappings = get_all_vendor_mappings(db)

        # Debug output of mappings
        for vendor, category in list(mappings.items())[:5]:
            logger.info(f"Sample mapping: '{vendor}' -> '{category}'")

        return mappings
    except Exception as e:
        logger.error(f"Error ensuring vendor mappings: {str(e)}")
        return {}


def recategorize_all_transactions(db) -> int:
    """Recategorize all transactions using current vendor mappings."""
    try:
        # Import main module for categorize_transaction function
        import main

        transactions = get_all_transactions(db)
        vendor_map = get_all_vendor_mappings(db)
        logger.info(
            f"Loaded {len(vendor_map)} vendor mappings for recategorization")

        # Debug output of some vendor mappings
        for vendor, category in list(vendor_map.items())[:5]:
            logger.info(f"Sample mapping: '{vendor}' -> '{category}'")

        updated_count = 0
        total_count = len(transactions)
        logger.info(f"Processing {total_count} transactions")

        for trans in transactions:
            try:
                # Use the enhanced categorize_transaction function from main.py
                new_category = main.categorize_transaction(
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
        logger.error(f"Error recategorizing transactions: {str(e)}")
        db.rollback()
        return 0


def export_vendor_mappings_to_json(db):
    """Export vendor mappings from database to vendor_map.json file."""
    try:
        # Get all mappings from database
        mappings = get_all_vendor_mappings(db)

        # Get the absolute path to vendor_map.json
        current_dir = os.path.dirname(os.path.abspath(__file__))
        vendor_map_path = os.path.join(current_dir, 'vendor_map.json')

        if not os.path.exists(vendor_map_path):
            vendor_map_path = 'vendor_map.json'  # Try current directory

        # Add custom categories if they exist in the file
        if os.path.exists(vendor_map_path):
            with open(vendor_map_path, 'r', encoding='utf-8') as f:
                existing_mappings = json.load(f)
                if "__custom_categories__" in existing_mappings:
                    mappings["__custom_categories__"] = existing_mappings["__custom_categories__"]

        # Write mappings to file
        with open(vendor_map_path, 'w', encoding='utf-8') as f:
            json.dump(mappings, f, indent=2)

        logger.info(
            f"Exported {len(mappings)} vendor mappings to {vendor_map_path}")
        return True
    except Exception as e:
        logger.error(f"Error exporting vendor mappings: {str(e)}")
        return False


def update_transaction_details(db: Session, transaction_id: int, new_details: str) -> bool:
    """Update the details (name) of a transaction."""
    transaction = db.query(Transaction).filter(Transaction.id == transaction_id).first()
    if transaction:
        transaction.details = new_details
        db.commit()
        logger.info(f"Updated transaction ID {transaction_id} with new details: {new_details}")
        return True
    logger.warning(f"Transaction ID {transaction_id} not found for updating details.")
    return False


def update_transaction_account(db: Session, transaction_id: int, new_account_id: str) -> bool:
    """Update the account_id of a transaction."""
    logger.info(f"DB: Attempting to update account for transaction_id: {transaction_id} to new_account_id: {new_account_id}")
    transaction = db.query(Transaction).filter(Transaction.id == transaction_id).first()
    
    if not transaction:
        logger.warning(f"DB: Transaction ID {transaction_id} not found.")
        return False

    logger.info(f"DB: Found transaction {transaction_id}. Current account_id: {transaction.account_id}")
    
    account = db.query(Account).filter(Account.account_id == new_account_id).first()
    if not account:
        logger.warning(f"DB: New Account ID {new_account_id} not found in Accounts table. Transaction {transaction_id} account not updated.")
        return False
        
    logger.info(f"DB: Found new account {new_account_id} (Name: {account.name}). Proceeding with update for transaction {transaction_id}.")
    
    transaction.account_id = new_account_id
    try:
        db.commit()
        db.refresh(transaction) # Refresh to get the latest state from DB
        logger.info(f"DB: Successfully committed update for transaction ID {transaction_id}. New account_id: {transaction.account_id}")
        # Verify the change
        updated_transaction = db.query(Transaction).filter(Transaction.id == transaction_id).first()
        if updated_transaction and updated_transaction.account_id == new_account_id:
            logger.info(f"DB: Verification successful. Transaction {transaction_id} account_id is now {updated_transaction.account_id}")
            return True
        else:
            logger.error(f"DB: Verification failed after commit for transaction {transaction_id}. Expected account_id {new_account_id}, found {updated_transaction.account_id if updated_transaction else 'None'}")
            return False
    except Exception as e:
        db.rollback()
        logger.error(f"DB: Error committing update for transaction {transaction_id} to account_id {new_account_id}: {str(e)}", exc_info=True)
        return False


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
        print(f"Error getting latest balances: {str(e)}")
        return {
            "chequing": {},
            "savings": {},
            "credit": {}
        }


def get_latest_statement_balance(db, account_id):
    """Get the latest statement balance for a specific account."""
    try:
        pdf_file = db.query(PDFFile).filter(PDFFile.id == account_id).first()
        return pdf_file.closing_balance if pdf_file else None
    except Exception as e:
        print(f"Error getting statement balance: {str(e)}")
        return None


def calculate_and_store_net_worth_snapshot(db: Session, date: datetime.date = None):
    """
    Calculate net worth for a given date and store it in the snapshots table.
    If no date is provided, uses today's date.
    """
    if date is None:
        date = datetime.date.today()
    
    # Get all accounts
    accounts = db.query(Account).all()
    
    # Calculate total assets and liabilities
    total_assets = 0
    total_liabilities = 0
    
    for account in accounts:
        balance = account.current_balance or 0
        if account.type.lower() in ['credit', 'loan'] or (account.subtype and account.subtype.lower() in ['credit card', 'loan']):
            total_liabilities += balance
        else:
            total_assets += balance
    
    net_worth = total_assets - total_liabilities
    
    # Check if snapshot already exists for this date
    existing_snapshot = db.query(NetWorthSnapshot).filter(NetWorthSnapshot.date == date).first()
    
    if existing_snapshot:
        # Update existing snapshot
        existing_snapshot.total_assets = total_assets
        existing_snapshot.total_liabilities = total_liabilities
        existing_snapshot.net_worth = net_worth
    else:
        # Create new snapshot
        snapshot = NetWorthSnapshot(
            date=date,
            total_assets=total_assets,
            total_liabilities=total_liabilities,
            net_worth=net_worth
        )
        db.add(snapshot)
    
    db.commit()
    return net_worth


def get_net_worth_history(db: Session, start_date: datetime.date = None, end_date: datetime.date = None, interval: str = 'daily', history_type: str = 'networth'):
    """
    Get net worth, cash, or credit card history for a given date range and interval.
    history_type: 'networth' (default), 'cash', or 'credit'
    Interval can be 'daily', 'weekly', 'biweekly', or 'monthly'.
    """
    if end_date is None:
        end_date = datetime.date.today()
    if start_date is None:
        start_date = end_date - datetime.timedelta(days=365)
    
    # Base query
    query = db.query(NetWorthSnapshot).filter(
        NetWorthSnapshot.date >= start_date,
        NetWorthSnapshot.date <= end_date
    )
    
    if interval == 'daily':
        snapshots = query.order_by(NetWorthSnapshot.date).all()
        if history_type == 'networth':
            return [{"date": s.date.isoformat(), "value": s.net_worth} for s in snapshots]
        elif history_type == 'cash':
            return [{"date": s.date.isoformat(), "value": s.total_assets} for s in snapshots]
        elif history_type == 'credit':
            return [{"date": s.date.isoformat(), "value": s.total_liabilities} for s in snapshots]
        else:
            raise ValueError(f"Invalid history_type: {history_type}")
    
    elif interval == 'weekly':
        snapshots = query.order_by(NetWorthSnapshot.date).all()
        weekly_data = {}
        for s in snapshots:
            week_start = s.date - datetime.timedelta(days=s.date.weekday())
            if week_start not in weekly_data:
                weekly_data[week_start] = []
            if history_type == 'networth':
                weekly_data[week_start].append(s.net_worth)
            elif history_type == 'cash':
                weekly_data[week_start].append(s.total_assets)
            elif history_type == 'credit':
                weekly_data[week_start].append(s.total_liabilities)
            else:
                raise ValueError(f"Invalid history_type: {history_type}")
        return [{"date": week_start.isoformat(), "value": sum(values)/len(values)} 
                for week_start, values in weekly_data.items()]
    
    elif interval == 'biweekly':
        snapshots = query.order_by(NetWorthSnapshot.date).all()
        biweekly_data = {}
        for s in snapshots:
            days_since_start = (s.date - start_date).days
            period_start = start_date + datetime.timedelta(days=(days_since_start // 14) * 14)
            if period_start not in biweekly_data:
                biweekly_data[period_start] = []
            if history_type == 'networth':
                biweekly_data[period_start].append(s.net_worth)
            elif history_type == 'cash':
                biweekly_data[period_start].append(s.total_assets)
            elif history_type == 'credit':
                biweekly_data[period_start].append(s.total_liabilities)
            else:
                raise ValueError(f"Invalid history_type: {history_type}")
        return [{"date": period_start.isoformat(), "value": sum(values)/len(values)} 
                for period_start, values in biweekly_data.items()]
    
    elif interval == 'monthly':
        snapshots = query.order_by(NetWorthSnapshot.date).all()
        monthly_data = {}
        for s in snapshots:
            month_start = s.date.replace(day=1)
            if month_start not in monthly_data:
                monthly_data[month_start] = []
            if history_type == 'networth':
                monthly_data[month_start].append(s.net_worth)
            elif history_type == 'cash':
                monthly_data[month_start].append(s.total_assets)
            elif history_type == 'credit':
                monthly_data[month_start].append(s.total_liabilities)
            else:
                raise ValueError(f"Invalid history_type: {history_type}")
        return [{"date": month_start.isoformat(), "value": sum(values)/len(values)} 
                for month_start, values in monthly_data.items()]
    else:
        raise ValueError(f"Invalid interval: {interval}")

def ensure_category_mappings(db):
    default_mappings = {
        "FOOD_AND_DRINK_FAST_FOOD": "Restaurants & Bars",
        "GENERAL_SERVICES_INSURANCE": "Insurance",
        "TRANSPORTATION_GAS": "Gas",
        "GENERAL_MERCHANDISE_CONVENIENCE_STORES": "Groceries",
        "FOOD_AND_DRINK_OTHER_FOOD_AND_DRINK": "Food & Dining",
        "MEDICAL_PHARMACIES_AND_SUPPLEMENTS": "Medical",
        "HOME_IMPROVEMENT_FURNITURE": "Furniture & Housewares",
        "TRANSPORTATION_PARKING": "Parking & Tolls",
        "GENERAL_MERCHANDISE_SUPERSTORES": "Groceries",
        "RENT_AND_UTILITIES_TELEPHONE": "Phone",
        "TRANSFER_IN_ACCOUNT_TRANSFER": "Transfer",
        "TRANSPORTATION_TAXIS_AND_RIDE_SHARES": "Taxi & Ride Shares",
        "ENTERTAINMENT_SPORTING_EVENTS_AMUSEMENT_PARKS_AND_MUSEUMS": "Entertainment & Recreation",
        "INCOME_INTEREST_EARNED": "Interest",
        "GENERAL_MERCHANDISE_DISCOUNT_STORES": "Shopping",
        "GENERAL_MERCHANDISE_CLOTHING_AND_ACCESSORIES": "Clothing",
        "FOOD_AND_DRINK_GROCERIES": "Groceries",
        "FOOD_AND_DRINK_RESTAURANT": "Restaurants & Bars",
        "GENERAL_SERVICES_AUTOMOTIVE": "Auto Maintenance",
        "LOAN_PAYMENTS_CREDIT_CARD_PAYMENT": "Credit Card Payment",
        "TRANSFER_OUT_ACCOUNT_TRANSFER": "Transfer",
        "RENT_AND_UTILITIES_INTERNET_AND_CABLE": "Internet & Cable",
        "TRANSPORTATION_PUBLIC_TRANSIT": "Public Transit",
        "HOME_IMPROVEMENT_OTHER_HOME_IMPROVEMENT": "Home Improvement",
        # ...add more as needed...
    }
    for plaid_cat, app_cat in default_mappings.items():
        exists = db.query(CategoryMapping).filter_by(plaid_category=plaid_cat).first()
        if not exists:
            db.add(CategoryMapping(plaid_category=plaid_cat, app_category=app_cat))
    db.commit()
