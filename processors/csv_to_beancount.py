"""Convert extracted CSV files to Beancount format."""
import csv
import json
import os
import re
from datetime import datetime


def load_accounts_config(config_file='accounts_config.json'):
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            return json.load(f).get('accounts', {})
    except FileNotFoundError:
        return {}


def extract_account_number(csv_file):
    """Extract account number from filename pattern: *_YYYYMMDD_ACCT_N.csv"""
    parts = os.path.splitext(os.path.basename(csv_file))[0].split('_')
    if len(parts) >= 3:
        return parts[-2]
    return None


def convert_date(date_str):
    for fmt in ('%d/%m/%Y', '%d/%m/%y', '%d %b'):
        try:
            return datetime.strptime(date_str, fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue
    return date_str


def csv_to_beancount(csv_file, config_file='accounts_config.json', currency='MYR'):
    """Convert a CSV file to Beancount transaction format. Returns string."""
    accounts_map = load_accounts_config(config_file)
    account_num = extract_account_number(csv_file)
    account_name = accounts_map.get(account_num, 'Assets:Bank')

    transactions = []
    with open(csv_file, 'r', newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            date = convert_date(row.get('Transaction Date') or row.get('Date') or '')
            desc = row.get('Description', '').strip()
            debit = float(row['Debit']) if row.get('Debit') else 0.0
            credit = float(row['Credit']) if row.get('Credit') else 0.0
            # CIMB CC uses Amount (positive=debit, negative=credit)
            if 'Amount' in row and 'Debit' not in row:
                amt = float(row['Amount']) if row.get('Amount') else 0.0
                debit = amt if amt > 0 else 0.0
                credit = -amt if amt < 0 else 0.0
            amount = credit - debit

            lines = [f'{date} * "{desc}"']
            lines.append(f'  {account_name}  {amount:.2f} {currency}')

            fx = re.search(r'\[FX:\s*([A-Z]{3})\s*([\d,]+\.\d{2})\]', desc)
            if fx:
                fx_cur, fx_amt = fx.group(1), float(fx.group(2).replace(',', ''))
                lines.append(f'  Expenses:Uncategorized  {fx_amt:.2f} {fx_cur} {{ {abs(amount):.2f} {currency} }}')
            else:
                lines.append(f'  Expenses:Uncategorized')

            transactions.append('\n'.join(lines))

    return '\n\n'.join(transactions)


if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print('Usage: python -m processors.csv_to_beancount <csv_file>')
        sys.exit(1)

    result = csv_to_beancount(sys.argv[1])
    output_file = os.path.splitext(sys.argv[1])[0] + '.beancount'
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(result)
    print(f'Written to {output_file}')
