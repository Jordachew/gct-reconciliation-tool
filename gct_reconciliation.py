import csv
import sys
from datetime import datetime
from collections import defaultdict

def parse_amount(amt_str):
    """Clean the amount string and convert to float."""
    if not amt_str:
        return 0.0
    try:
        # Remove commas and convert to float
        return float(amt_str.replace(',', ''))
    except ValueError:
        return 0.0

def parse_date(date_str):
    """Attempt to parse date and return a YYYY-MM key."""
    if not date_str:
        return None
    
    formats_to_try = ['%m/%d/%Y', '%Y-%m-%d', '%d/%m/%Y', '%m/%d/%y']
    for fmt in formats_to_try:
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            return dt.strftime('%Y-%m')
        except ValueError:
            continue
    return None

def process_csv(filepath):
    """Reads the CSV, categorizes transactions, and aggregates by month."""
    monthly_data = defaultdict(lambda: {
        'output_gct': 0.0,
        'input_gct': 0.0,
        'payments': 0.0,
        'journal_adj': 0.0,
        'sales_tax_adj': 0.0
    })

    try:
        with open(filepath, mode='r', encoding='utf-8-sig') as file:
            reader = csv.reader(file)
            headers = []
            
            # Find the header row (looking for 'amount' and 'transaction date' or 'date')
            header_idx = -1
            all_rows = list(reader)
            
            for i, row in enumerate(all_rows[:20]): # Check first 20 rows for headers
                row_lower = [str(c).lower().strip() for c in row]
                if ('transaction date' in row_lower or 'date' in row_lower) and 'amount' in row_lower:
                    header_idx = i
                    headers = row_lower
                    break
            
            if header_idx == -1:
                print("Error: Could not find valid headers (need 'Date' and 'Amount').")
                return None

            # Map column names to indices
            date_idx = headers.index('transaction date') if 'transaction date' in headers else headers.index('date')
            amt_idx = headers.index('amount')
            memo_idx = headers.index('memo/description') if 'memo/description' in headers else (headers.index('memo') if 'memo' in headers else -1)
            type_idx = headers.index('transaction type') if 'transaction type' in headers else (headers.index('type') if 'type' in headers else -1)

            # Process data rows
            for row in all_rows[header_idx + 1:]:
                if len(row) != len(headers):
                    continue
                
                date_str = row[date_idx]
                amt_str = row[amt_idx]
                amount = parse_amount(amt_str)
                
                if amount == 0:
                    continue
                    
                month_key = parse_date(date_str)
                if not month_key:
                    continue

                type_str = row[type_idx] if type_idx != -1 else ""
                memo_str = row[memo_idx] if memo_idx != -1 else ""
                
                type_lower = type_str.lower().strip()
                memo_lower = memo_str.lower().strip()

                # --- Categorization Logic (Matching the React App) ---
                is_sales_tax_adj = 'sales tax adjustment' in type_lower or 'sales tax adj' in type_lower or 'tax adjustment' in memo_lower
                is_journal = 'journal' in type_lower and not is_sales_tax_adj
                is_payment = ('sales tax payment' in type_lower or 'payment' in memo_lower) and not is_sales_tax_adj and not is_journal

                is_output_gct = type_lower in ['invoice', 'sales receipt', 'credit note', 'refund'] or 'sales receipt' in type_lower
                is_input_gct = type_lower in ['bill', 'check', 'credit card expense', 'expense']
                is_cc_credit = type_lower == 'credit card credit'

                if is_payment:
                    monthly_data[month_key]['payments'] += abs(amount)
                elif is_sales_tax_adj:
                    monthly_data[month_key]['sales_tax_adj'] += amount
                elif is_journal:
                    monthly_data[month_key]['journal_adj'] += amount
                elif is_input_gct or is_cc_credit:
                    input_contribution = -abs(amount) if is_cc_credit else abs(amount)
                    monthly_data[month_key]['input_gct'] += input_contribution
                elif is_output_gct:
                    output_contribution = -abs(amount) if type_lower in ['refund', 'credit note'] else abs(amount)
                    monthly_data[month_key]['output_gct'] += output_contribution
                else:
                    # Fallback based on amount sign
                    if amount > 0:
                        monthly_data[month_key]['output_gct'] += abs(amount)
                    else:
                        monthly_data[month_key]['input_gct'] += abs(amount)

        return monthly_data

    except FileNotFoundError:
        print(f"Error: File '{filepath}' not found.")
        return None

def generate_report(monthly_data):
    """Calculates cumulative totals and prints a formatted report."""
    if not monthly_data:
        return

    sorted_months = sorted(monthly_data.keys())
    cumulative_balance = 0.0

    print("="*105)
    print(f"{'Period':<10} | {'Opening Bal':>12} | {'Output GCT':>12} | {'Input GCT':>12} | {'Adjustments':>12} | {'Payments':>12} | {'Closing Bal':>12}")
    print("="*105)

    for i, month in enumerate(sorted_months):
        data = monthly_data[month]
        
        # Calculate opening balance
        opening_balance = cumulative_balance
        
        # Calculate net adjustments
        total_adjustments = data['journal_adj'] + data['sales_tax_adj']
        
        # Calculate monthly generated liability
        monthly_generated = data['output_gct'] - data['input_gct'] + total_adjustments
        
        # Find next month's payment (payments are usually applied to the previous month's balance)
        next_month_payment = 0.0
        if i + 1 < len(sorted_months):
            next_month_key = sorted_months[i + 1]
            next_month_payment = monthly_data[next_month_key]['payments']
            
        # Calculate closing balance
        cumulative_balance = opening_balance + monthly_generated - next_month_payment

        print(f"{month:<10} | ${opening_balance:>11,.2f} | ${data['output_gct']:>11,.2f} | ${data['input_gct']:>11,.2f} | ${total_adjustments:>11,.2f} | ${next_month_payment:>11,.2f} | ${cumulative_balance:>11,.2f}")
    
    print("="*105)

if __name__ == "__main__":
    # Change 'data.csv' to the name of your actual QuickBooks export file
    csv_filename = 'C:\\Users\\jwilson\\Downloads\\budgetbridge\\data.csv'
    
    print(f"Processing '{csv_filename}'...\n")
    processed_data = process_csv(csv_filename)
    
    if processed_data:
        generate_report(processed_data)
        
        # Optional: Save to a new summary CSV
        # with open('summary_report.csv', 'w', newline='') as f:
        #     # Add CSV writing logic here if you want to export the table
        #     pass