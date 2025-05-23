import streamlit as st
import pandas as pd
from datetime import datetime
        import sys
import os

# Add the parent directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from models import SessionLocal, Transaction

def main():
    st.title("Finance Categorizer")
    
    # Create a database session
    db = SessionLocal()
    
    try:
        # Fetch transactions
        transactions = db.query(Transaction).all()
        
        # Convert to DataFrame
    data = []
        for t in transactions:
                    data.append({
                'Date': t.date,
                'Description': t.details,
                'Amount': t.amount,
                'Category': t.category
            })
        
        df = pd.DataFrame(data)
        
        # Display summary statistics
        st.header("Transaction Summary")
        total_income = df[df['Amount'] > 0]['Amount'].sum()
        total_expenses = abs(df[df['Amount'] < 0]['Amount'].sum())
        net_balance = total_income - total_expenses
        
                    col1, col2, col3 = st.columns(3)
                        with col1:
            st.metric("Total Income", f"${total_income:,.2f}")
                        with col2:
            st.metric("Total Expenses", f"${total_expenses:,.2f}")
                            with col3:
            st.metric("Net Balance", f"${net_balance:,.2f}")
        
        # Display transactions
        st.header("Transactions")
        st.dataframe(df.sort_values('Date', ascending=False))
        
        # Category-wise expenses
        st.header("Category-wise Expenses")
        category_expenses = df[df['Amount'] < 0].groupby('Category')['Amount'].sum().abs()
        st.bar_chart(category_expenses)
        
                            except Exception as e:
        st.error(f"Error: {str(e)}")
    finally:
        db.close()

if __name__ == "__main__":
    main() 