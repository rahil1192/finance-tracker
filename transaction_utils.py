import re
import logging

# Configure logging
logger = logging.getLogger(__name__)

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
        from models import Transaction
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
