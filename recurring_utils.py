from sqlalchemy.orm import Session

def is_recurring_by_rule(transaction, db: Session):
    # Import RecurringRule here to avoid circular import
    from models import RecurringRule
    rules = db.query(RecurringRule).filter_by(active=True).all()
    details = (getattr(transaction, 'details', None) or transaction.get('details', '')).strip().lower()
    for rule in rules:
        if rule.match_type == 'exact' and details == (rule.merchant or '').strip().lower():
            return True
        if rule.match_type == 'contains' and rule.merchant.lower() in details:
            return True
        # Add regex support if needed
    return False 