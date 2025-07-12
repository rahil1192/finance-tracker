from models import SessionLocal, CategoryMapping

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

def migrate():
    db = SessionLocal()
    inserted = 0
    for plaid_cat, app_cat in default_mappings.items():
        exists = db.query(CategoryMapping).filter_by(plaid_category=plaid_cat).first()
        if not exists:
            db.add(CategoryMapping(plaid_category=plaid_cat, app_category=app_cat))
            inserted += 1
    db.commit()
    db.close()
    print(f"Migration complete. {inserted} new mappings inserted.")

if __name__ == "__main__":
    migrate() 