import re
import pandas as pd
import pdfplumber


def classify_transaction_type(details):
    """Classify transaction as Debit or Credit based on details."""
    text = details.lower()
    if "rewards" in text or "rebate" in text or "refund" in text:
        return "Credit"
    debit_keywords = ["retail", "debit", "purchase",
                      "bill", "charge", "petro", "service", "withdrawal"]
    if any(k in text for k in debit_keywords):
        return "Debit"
    return "Credit"


def parse_pdf_transactions(file):
    """Parse transactions from PDF file."""
    data = []
    current_date = None
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            lines = page.extract_text().split("\n")
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                date_match = re.match(
                    r"^((Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2})(.*)", line)
                if date_match:
                    current_date = date_match.group(1).strip()
                    line = date_match.group(3).strip()

                matches = re.findall(r"([\d,]+\.\d{2}) ([\d,]+\.\d{2})", line)
                if matches:
                    parts = re.split(r"[\d,]+\.\d{2} [\d,]+\.\d{2}", line)
                    for i, (amount_str, _) in enumerate(matches):
                        desc = parts[i].strip() if i < len(parts) else ""
                        amount = float(amount_str.replace(",", ""))
                        details = desc
                        trans_type = classify_transaction_type(details)
                        data.append({
                            "Date": pd.to_datetime(current_date + " 2025", errors='coerce'),
                            "Details": details,
                            "Amount": amount,
                            "Debit/Credit": trans_type
                        })
                else:
                    if data:
                        data[-1]["Details"] += " " + line
    return pd.DataFrame(data)


def categorize(df, vendor_map):
    """Categorize transactions based on vendor mapping."""
    df["Category"] = "Uncategorized"
    for idx, row in df.iterrows():
        details = row["Details"].lower()
        for vendor_substring, cat in vendor_map.items():
            if vendor_substring == "__custom_categories__":
                continue
            if vendor_substring in details:
                df.at[idx, "Category"] = cat
                break
    return df


def auto_apply_category(df, original_df):
    """Automatically apply categories to similar transactions."""
    categorized_rows = df[df["Category"] != "Uncategorized"]
    for _, row in categorized_rows.iterrows():
        snippet = row["Details"].lower()[:25]
        category = row["Category"]
        mask = original_df["Details"].str.lower().str.contains(
            re.escape(snippet)) & (original_df["Category"] == "Uncategorized")
        original_df.loc[mask, "Category"] = category
    return original_df
