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
    """Extract account number from filename patterns:
    - Maybank savings: *_YYYYMMDD_ACCT.csv → last part is account
    - Maybank CC: card_cc.csv → use parent dir *_YYYYMMDD which has no account
    - CIMB CC: card_XXXX.csv → XXXX is the card last-4
    """
    stem = os.path.splitext(os.path.basename(csv_file))[0]
    parts = stem.split('_')
    if parts[0] == 'card' and len(parts) == 2 and parts[1] != 'savings':
        return parts[1]
    parent_parts = os.path.basename(os.path.dirname(csv_file)).split('_')
    if len(parent_parts) >= 3:
        return parent_parts[-1]
    return None


def extract_statement_date(csv_file):
    """Extract YYYYMMDD from parent directory name like '749358443_20260131_6158'."""
    parent = os.path.basename(os.path.dirname(csv_file))
    m = re.search(r'_(20\d{2})(\d{2})\d{2}', parent)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None, None


def convert_date(date_str, stmt_year=None, stmt_month=None):
    """Convert date string to YYYY-MM-DD format, inferring year from statement date if needed."""
    for fmt in ('%d/%m/%Y', '%d/%m/%y'):
        try:
            return datetime.strptime(date_str, fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue
    # DD/MM without year — infer from statement date
    m = re.match(r'^(\d{2})/(\d{2})$', date_str)
    if m and stmt_year:
        day, month = int(m.group(1)), int(m.group(2))
        year = stmt_year - 1 if month > stmt_month else stmt_year
        return f'{year}-{month:02d}-{day:02d}'
    # DD MMM format (e.g. "28 DEC" — already resolved by CIMB extractor to DD/MM/YYYY)
    try:
        return datetime.strptime(date_str, '%d %b').strftime('%Y-%m-%d')
    except ValueError:
        pass
    return date_str


def csv_to_beancount(csv_file, config_file='accounts_config.json', currency='MYR'):
    """Convert a CSV file to Beancount transaction format. Returns string."""
    accounts_map = load_accounts_config(config_file)
    account_num = extract_account_number(csv_file)
    account_name = accounts_map.get(account_num, 'Assets:Bank')
    stmt_year, stmt_month = extract_statement_date(csv_file)

    transactions = []
    with open(csv_file, 'r', newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            date = convert_date(row.get('Transaction Date') or row.get('Date') or '', stmt_year, stmt_month)
            if not date or date == '':
                continue
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
