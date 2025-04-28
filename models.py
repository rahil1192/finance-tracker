from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, JSON, LargeBinary, inspect
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import json
from pathlib import Path
import yaml
import os
import logging
from sqlalchemy import text

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

# Create database engine
DATABASE_URL = 'sqlite:///finance_categorizer.db'
engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class PDFFile(Base):
    __tablename__ = "pdf_files"

    id = Column(Integer, primary_key=True, index=True)
    original_filename = Column(String)
    content = Column(LargeBinary)  # Store PDF content as binary data
    upload_date = Column(DateTime, default=datetime.utcnow)
    month_year = Column(String, index=True)
    opening_balance = Column(Float, nullable=True)  # Add opening balance field
    closing_balance = Column(Float, nullable=True)  # Add closing balance field
    bank = Column(String, nullable=True)  # Add bank column
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow,
                        onupdate=datetime.utcnow)


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(DateTime, index=True)
    details = Column(String)
    amount = Column(Float)
    transaction_type = Column(String)  # Debit/Credit
    category = Column(String, default="Uncategorized")
    pdf_file_id = Column(Integer, index=True)  # Reference to PDFFile


class VendorMapping(Base):
    __tablename__ = "vendor_mappings"

    id = Column(Integer, primary_key=True, index=True)
    vendor_substring = Column(String, unique=True, index=True)
    category = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow,
                        onupdate=datetime.utcnow)


def init_db():
    """Initialize the database and handle schema updates."""
    try:
        # Check if database file exists
        if not os.path.exists('finance_categorizer.db'):
            # First time initialization
            Base.metadata.create_all(bind=engine)
            logger.info("Created new database tables")

            # Import initial vendor mappings
            db = next(get_db())
            try:
                import_vendor_mappings_from_json(db)
            except Exception as e:
                logger.error(
                    f"Error importing initial vendor mappings: {str(e)}")
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

# Database session dependency


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Helper functions for database operations


def save_pdf_file(db, original_filename, content, month_year, opening_balance=None, closing_balance=None, bank=None):
    """Save a PDF file to the database.

    Args:
        db: Database session
        original_filename: Original name of the uploaded file
        content: Binary content of the PDF file
        month_year: Month and year of the statement
        opening_balance: Opening balance from the statement
        closing_balance: Closing balance from the statement
        bank: Bank from the statement

    Returns:
        PDFFile: The saved PDF file object
    """
    try:
        pdf_file = PDFFile(
            original_filename=original_filename,
            content=content,
            month_year=month_year,
            opening_balance=opening_balance,
            closing_balance=closing_balance,
            bank=bank
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


def get_pdf_content(db, pdf_file_id):
    """Get PDF content by ID."""
    pdf_file = db.query(PDFFile).filter(PDFFile.id == pdf_file_id).first()
    return pdf_file.content if pdf_file else None


def save_transaction(db, transaction_data):
    transaction = Transaction(**transaction_data)
    db.add(transaction)
    db.commit()
    return transaction


def get_all_transactions(db):
    return db.query(Transaction).order_by(Transaction.date.desc()).all()


def save_vendor_mapping(db, vendor_substring, category):
    mapping = db.query(VendorMapping).filter(
        VendorMapping.vendor_substring == vendor_substring).first()
    if mapping:
        mapping.category = category
    else:
        mapping = VendorMapping(
            vendor_substring=vendor_substring, category=category)
        db.add(mapping)
    db.commit()
    return mapping


def get_all_vendor_mappings(db):
    return {m.vendor_substring: m.category for m in db.query(VendorMapping).all()}


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
        # Delete all records from each table
        db.query(Transaction).delete()
        db.query(VendorMapping).delete()
        db.query(PDFFile).delete()
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
    """Ensure vendor mappings exist in the database, import if needed."""
    try:
        mappings = get_all_vendor_mappings(db)
        if not mappings:
            logger.info("No vendor mappings found, importing from JSON")
            import_vendor_mappings_from_json(db)
            mappings = get_all_vendor_mappings(db)
            logger.info(f"Imported {len(mappings)} vendor mappings")
        return mappings
    except Exception as e:
        logger.error(f"Error ensuring vendor mappings: {str(e)}")
        return {}
