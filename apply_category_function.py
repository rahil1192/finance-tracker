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
        # Extract vendor key from the transaction details
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
