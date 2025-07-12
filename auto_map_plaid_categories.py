import requests

API_BASE = "http://localhost:8001/api"

# Predefined mapping: Plaid category → built-in category
PLAID_TO_APP_CATEGORY = {
    "Food and Drink": "Food & Dining",
    "Restaurants": "Restaurants & Bars",
    "Coffee Shop": "Coffee Shops",
    "Transfer": "Transfer",
    "Credit Card": "Credit Card Payment",
    "Travel": "Travel & Vacation",
    "Gas": "Gas",
    "Groceries": "Groceries",
    "Shopping": "Shopping",
    "Clothing": "Clothing",
    "Rent": "Rent",
    "Mortgage": "Mortgage",
    "Home Improvement": "Home Improvement",
    "Bills and Utilities": "Bills & Utilities",
    "Water": "Water",
    "Electric": "Gas & Electric",
    "Internet": "Internet & Cable",
    "Phone": "Phone",
    "Charity": "Charity",
    "Gifts": "Gifts",
    "Medical": "Medical",
    "Dentist": "Dentist",
    "Fitness": "Fitness",
    "Insurance": "Insurance",
    "Loan": "Loan Repayment",
    "Financial": "Financial & Legal Services",
    "Cash Advance": "Cash & ATM",
    "Entertainment": "Entertainment & Recreation",
    "Pets": "Pets",
    "Childcare": "Child Care",
    "Education": "Education",
    "Student Loan": "Student Loans",
    "Business": "Business Income",
    "Salary": "Paycheck",
    "Interest": "Interest",
    "Other": "Other",
    # Add more as needed!
}

def get_unmapped_categories():
    print("Running backfill to get unmapped categories...")
    resp = requests.post(f"{API_BASE}/transactions/backfill_app_category")
    data = resp.json()
    return data.get("unmapped_categories", [])

def add_mapping(plaid_category, app_category):
    resp = requests.post(
        f"{API_BASE}/category_mappings",
        data={"plaid_category": plaid_category, "app_category": app_category}
    )
    print(f"Mapped '{plaid_category}' → '{app_category}': {resp.json()}")

def main():
    unmapped = get_unmapped_categories()
    if not unmapped:
        print("No unmapped categories found. All Plaid categories are mapped!")
        return

    mapped_to_other = []

    for plaid_cat in unmapped:
        app_cat = PLAID_TO_APP_CATEGORY.get(plaid_cat, "Other")
        add_mapping(plaid_cat, app_cat)
        if app_cat == "Other":
            mapped_to_other.append(plaid_cat)

    print("\nRe-running backfill to update all transactions...")
    requests.post(f"{API_BASE}/transactions/backfill_app_category")
    print("Done! All Plaid categories are now mapped.")

    if mapped_to_other:
        print("\nThe following Plaid categories were mapped to 'Other':")
        for cat in mapped_to_other:
            print(f"  - {cat}")
        print("\nConsider adding these to your mapping dictionary for better categorization.")

if __name__ == "__main__":
    main() 