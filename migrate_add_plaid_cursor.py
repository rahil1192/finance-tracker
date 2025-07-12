from sqlalchemy import create_engine, text

DATABASE_URL = 'sqlite:///finance.db'
engine = create_engine(DATABASE_URL)

with engine.connect() as conn:
    # Check if the column already exists
    result = conn.execute(text("PRAGMA table_info(plaid_items);"))
    columns = [row[1] for row in result]
    if 'plaid_cursor' not in columns:
        conn.execute(text("ALTER TABLE plaid_items ADD COLUMN plaid_cursor VARCHAR;"))
        print("Added plaid_cursor column to plaid_items table.")
    else:
        print("plaid_cursor column already exists.") 