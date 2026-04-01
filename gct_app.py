import streamlit as st
import csv
import io
from datetime import datetime
from collections import defaultdict
import pandas as pd

# --- Page Configuration (Must be first Streamlit command) ---
st.set_page_config(
    page_title="GCT Reconciliation Workspace",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Utility Functions ---
def parse_amount(amt_str):
    if not amt_str: return 0.0
    try: return float(amt_str.replace(',', ''))
    except ValueError: return 0.0

def parse_date(date_str):
    if not date_str: return None
    formats_to_try = ['%m/%d/%Y', '%Y-%m-%d', '%d/%m/%Y', '%m/%d/%y']
    for fmt in formats_to_try:
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            return dt.strftime('%Y-%m')
        except ValueError: continue
    return None

def process_csv_data(file_content):
    monthly_data = defaultdict(lambda: {
        'output_gct': 0.0, 'input_gct': 0.0, 'payments': 0.0,
        'journal_adj': 0.0, 'sales_tax_adj': 0.0
    })

    reader = csv.reader(file_content)
    all_rows = list(reader)
    headers = []
    header_idx = -1
    
    # Find headers
    for i, row in enumerate(all_rows[:20]):
        row_lower = [str(c).lower().strip() for c in row]
        if ('transaction date' in row_lower or 'date' in row_lower) and 'amount' in row_lower:
            header_idx = i
            headers = row_lower
            break
            
    if header_idx == -1: return None

    date_idx = headers.index('transaction date') if 'transaction date' in headers else headers.index('date')
    amt_idx = headers.index('amount')
    memo_idx = headers.index('memo/description') if 'memo/description' in headers else (headers.index('memo') if 'memo' in headers else -1)
    type_idx = headers.index('transaction type') if 'transaction type' in headers else (headers.index('type') if 'type' in headers else -1)

    for row in all_rows[header_idx + 1:]:
        if len(row) != len(headers): continue
        
        amount = parse_amount(row[amt_idx])
        if amount == 0: continue
            
        month_key = parse_date(row[date_idx])
        if not month_key: continue

        type_lower = row[type_idx].lower().strip() if type_idx != -1 else ""
        memo_lower = row[memo_idx].lower().strip() if memo_idx != -1 else ""

        is_sales_tax_adj = 'sales tax adjustment' in type_lower or 'sales tax adj' in type_lower or 'tax adjustment' in memo_lower
        is_journal = 'journal' in type_lower and not is_sales_tax_adj
        is_payment = ('sales tax payment' in type_lower or 'payment' in memo_lower) and not is_sales_tax_adj and not is_journal

        is_output_gct = type_lower in ['invoice', 'sales receipt', 'credit note', 'refund'] or 'sales receipt' in type_lower
        is_input_gct = type_lower in ['bill', 'check', 'credit card expense', 'expense']
        is_cc_credit = type_lower == 'credit card credit'

        if is_payment: monthly_data[month_key]['payments'] += abs(amount)
        elif is_sales_tax_adj: monthly_data[month_key]['sales_tax_adj'] += amount
        elif is_journal: monthly_data[month_key]['journal_adj'] += amount
        elif is_input_gct or is_cc_credit:
            monthly_data[month_key]['input_gct'] += (-abs(amount) if is_cc_credit else abs(amount))
        elif is_output_gct:
            monthly_data[month_key]['output_gct'] += (-abs(amount) if type_lower in ['refund', 'credit note'] else abs(amount))
        else:
            if amount > 0: monthly_data[month_key]['output_gct'] += abs(amount)
            else: monthly_data[month_key]['input_gct'] += abs(amount)

    return dict(monthly_data)

# --- UI Layout ---
st.title("📊 GCT Reconciliation Workspace")
st.markdown("Upload your QuickBooks CSV export to generate a clean, month-by-month reconciliation report.")

# File Uploader
uploaded_file = st.file_uploader("Drag and drop your CSV file here", type=['csv'])

if uploaded_file is not None:
    # Read and process file
    stringio = io.StringIO(uploaded_file.getvalue().decode("utf-8-sig"))
    monthly_data = process_csv_data(stringio)
    
    if monthly_data is None:
        st.error("Could not find valid headers ('Date' and 'Amount') in the uploaded CSV.")
    else:
        st.success("File processed successfully!")
        
        # Calculate Report Data
        sorted_months = sorted(monthly_data.keys())
        cumulative_balance = 0.0
        report_rows = []
        
        total_ytd_output = 0
        total_ytd_input = 0
        
        for i, month in enumerate(sorted_months):
            data = monthly_data[month]
            opening_balance = cumulative_balance
            total_adjustments = data['journal_adj'] + data['sales_tax_adj']
            monthly_generated = data['output_gct'] - data['input_gct'] + total_adjustments
            
            next_month_payment = 0.0
            if i + 1 < len(sorted_months):
                next_month_payment = monthly_data[sorted_months[i + 1]]['payments']
                
            cumulative_balance = opening_balance + monthly_generated - next_month_payment
            
            total_ytd_output += data['output_gct']
            total_ytd_input += data['input_gct']
            
            report_rows.append({
                "Period": month,
                "Opening Balance": opening_balance,
                "Output GCT": data['output_gct'],
                "Input GCT": data['input_gct'],
                "Adjustments": total_adjustments,
                "Applied Payments": next_month_payment,
                "Closing Balance": cumulative_balance
            })
            
        # Display Top Metrics
        st.markdown("### Year-to-Date Summary")
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Output GCT", f"${total_ytd_output:,.2f}")
        col2.metric("Total Input GCT", f"${total_ytd_input:,.2f}")
        col3.metric("Current Balance Due", f"${cumulative_balance:,.2f}", 
                    delta="In Debt" if cumulative_balance > 0 else "Credit", 
                    delta_color="inverse")
        
        # Display Data Table
        st.markdown("### Monthly Ledger")
        
        # Convert to Pandas DataFrame for a beautiful table
        df = pd.DataFrame(report_rows)
        
        # Format columns as currency for display
        format_dict = {col: "${:,.2f}" for col in df.columns if col != "Period"}
        st.dataframe(df.style.format(format_dict), use_container_width=True, hide_index=True)

        # Allow user to download the generated report
        csv_export = df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Download Summary Report (CSV)",
            data=csv_export,
            file_name='gct_summary_report.csv',
            mime='text/csv',
            type="primary"
        )
else:
    st.info("Awaiting file upload. Please select a CSV file to begin.")