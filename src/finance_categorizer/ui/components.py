import streamlit as st
import plotly.express as px
import pandas as pd


def display_summary_metrics(df):
    """Display summary metrics for financial data."""
    total_debits = df[df["Debit/Credit"] == "Debit"]["Amount"].sum()
    total_credits = df[df["Debit/Credit"] == "Credit"]["Amount"].sum()
    balance = total_credits - total_debits

    col1, col2, col3 = st.columns(3)
    col1.metric("💸 Total Debits", f"C${total_debits:,.2f}")
    col2.metric("💰 Total Credits", f"C${total_credits:,.2f}")
    col3.metric("🧾 Net Balance", f"C${balance:,.2f}",
                delta_color="inverse" if balance < 0 else "normal")


def plot_financial_overview(df):
    """Plot financial overview chart."""
    total_debits = df[df["Debit/Credit"] == "Debit"]["Amount"].sum()
    total_credits = df[df["Debit/Credit"] == "Credit"]["Amount"].sum()
    balance = total_credits - total_debits

    summary_df = pd.DataFrame({
        "Type": ["Credit", "Debit", "Balance"],
        "Amount": [total_credits, total_debits, balance]
    })

    chart_type = st.radio("Select chart type:", [
                          "Bar Chart", "Pie Chart"], horizontal=True)

    if chart_type == "Bar Chart":
        fig = px.bar(summary_df, x="Type", y="Amount",
                     color="Type", title="Financial Overview")
    else:
        fig = px.pie(summary_df, values="Amount", names="Type",
                     title="Financial Overview", hole=0.4)

    st.plotly_chart(fig, use_container_width=True)


def plot_category_summary(df, title, chart_type="Pie Chart"):
    """Plot category summary chart."""
    if df.empty:
        return

    if chart_type == "Pie Chart":
        fig = px.pie(df, values="Amount", names="Category",
                     title=title, hole=0.4)
    else:
        fig = px.bar(df, x="Category", y="Amount",
                     title=title, color="Category")

    st.plotly_chart(fig, use_container_width=True)


def display_monthly_report(df):
    """Display monthly expense report."""
    if df.empty:
        st.info("No transactions to show.")
        return

    df["Month"] = df["Date"].dt.to_period("M").astype(str)
    available_months = sorted(df["Month"].unique(), reverse=True)
    selected_month = st.selectbox("Select a Month", available_months)

    filtered_df = df[(df["Month"] == selected_month) &
                     (df["Debit/Credit"] == "Debit")]
    monthly_summary = filtered_df.groupby(
        "Category")["Amount"].sum().reset_index()

    st.write(f"### Expenses for {selected_month}")
    st.dataframe(monthly_summary, use_container_width=True)

    if not monthly_summary.empty:
        chart = px.bar(monthly_summary, x="Category", y="Amount",
                       title=f"Expenses by Category - {selected_month}", color="Category")
        st.plotly_chart(chart, use_container_width=True)
