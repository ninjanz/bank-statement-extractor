import re
from .base import BaseExtractor

TRANSACTION_RE = re.compile(r'^(\d{2}/\d{2})\s+(\d{2}/\d{2})\s+(.+?)\s+([\d,]+\.\d{2})(CR)?\s*$')
FX_RE = re.compile(r'^TRANSACTED AMOUNT\s+([A-Z]{3})\s+([\d,]+\.\d{2})')
TOTAL_CREDIT_RE = re.compile(r'TOTAL CREDIT THIS MONTH\s*([\d,]+\.\d{2})?')
TOTAL_DEBIT_RE = re.compile(r'TOTAL DEBIT THIS MONTH\s*([\d,]+\.\d{2})?')
SUB_TOTAL_RE = re.compile(r'SUB TOTAL/JUMLAH\s*([\d,]+\.\d{2})?')
AMOUNT_RE = re.compile(r'([\d,]+\.\d{2})')
INTEREST_RATE_RE = re.compile(r'RETAIL INTEREST RATE|CASH ADVANCE INTEREST')
PREV_BALANCE_RE = re.compile(r'YOUR PREVIOUS STATEMENT BALANCE\s*([\d,]+\.\d{2})?')

NOISE_STRS = [
    'WARNING ON PAYING', 'AMARAN KE ATAS', 'If you make only',
    'take you longer', 'Alternatively, you may', 'Jika anda hanya',
    'faedah dan tempoh', 'lanjut sila rujuk', 'bankinginfo',
    'www.maybank', 'MAYBANK CARD -', 'YOUR COMBINED CREDIT',
    'KOMBINASI HAD KREDIT', 'Page/Halaman', 'STATEMENT OF CREDIT',
    'PENYATA AKAUN', 'Malayan Banking', 'Posting Date',
    'Tarikh Pos', 'Menara Maybank', '100 Jalan Tun',
    '50050 Kuala Lumpur', 'Wilayah Persekutuan', 'ENCIK ',
    'NO 3 JLN', 'TMN ANJUNG', '68100 BATU',
    'Statement Date', 'Tarikh Penyata', 'Account Number',
    'Current Balance', 'Minimum Payment', 'Amount To Be',
    'TreatsPoints', 'Mata Ganjaran', 'TREATS',
    'Current Payment Scheme', 'Minimum Payment Warning',
    'New Balance', 'Payment Due Date', 'Card No/Nombor',
    'Total Multiple', 'Jumlah Mata', 'VISA SIGNATURE',
    'Multiple TreatsPoints',
]


def _is_noise(line):
    if not line:
        return True
    for p in NOISE_STRS:
        if p in line:
            return True
    return False


class MbbCCExtractor(BaseExtractor):

    def extract(self, pdf_path):
        all_lines = self.read_pdf_lines(pdf_path)
        transactions = []
        totals = {'credit': None, 'debit': None, 'sub_total': None}
        in_transactions = False
        prev_balance = None

        i = 0
        while i < len(all_lines):
            line = all_lines[i].strip()

            # Detect totals (these end the transaction section)
            if 'TOTAL CREDIT THIS MONTH' in line:
                m = AMOUNT_RE.search(line)
                if not m and i + 1 < len(all_lines):
                    m = AMOUNT_RE.search(all_lines[i + 1])
                if m:
                    totals['credit'] = float(m.group(1).replace(',', ''))
                in_transactions = False
                i += 1
                continue

            if 'TOTAL DEBIT THIS MONTH' in line:
                m = AMOUNT_RE.search(line)
                if not m and i + 1 < len(all_lines):
                    m = AMOUNT_RE.search(all_lines[i + 1])
                if m:
                    totals['debit'] = float(m.group(1).replace(',', ''))
                i += 1
                continue

            if 'SUB TOTAL' in line:
                m = AMOUNT_RE.search(line)
                if m:
                    totals['sub_total'] = float(m.group(1).replace(',', ''))
                i += 1
                continue

            # Previous balance
            if 'YOUR PREVIOUS STATEMENT BALANCE' in line:
                m = AMOUNT_RE.search(line)
                if m:
                    prev_balance = float(m.group(1).replace(',', ''))
                in_transactions = True
                i += 1
                continue

            # Skip interest rate info lines
            if INTEREST_RATE_RE.search(line):
                i += 1
                continue

            if _is_noise(line):
                i += 1
                continue

            # Transaction line
            tx_m = TRANSACTION_RE.match(line)
            if tx_m:
                in_transactions = True
                post_date, tx_date, desc, amount_str, cr = tx_m.groups()
                amt = float(amount_str.replace(',', ''))
                debit = None if cr else amt
                credit = amt if cr else None

                # Check next line for FX info
                j = i + 1
                if j < len(all_lines):
                    fx_m = FX_RE.match(all_lines[j].strip())
                    if fx_m:
                        cur, fx_amt = fx_m.groups()
                        desc += f' [FX: {cur} {fx_amt}]'
                        j += 1

                transactions.append({
                    'Posting Date': post_date, 'Transaction Date': tx_date,
                    'Description': desc, 'Debit': debit, 'Credit': credit,
                })
                i = j
                continue

            i += 1

        accounts = {'cc': transactions}

        # Validate sub_total = prev_balance + debit - credit (net owed)
        # Or simpler: credit and debit totals match
        balances = {}
        if totals['credit'] is not None:
            balances['cc'] = totals['credit']

        self._totals = totals
        self._prev_balance = prev_balance
        computed_debit = sum(t['Debit'] for t in transactions if t['Debit'])
        computed_credit = sum(t['Credit'] for t in transactions if t['Credit'])
        self._computed = {'debit': computed_debit, 'credit': computed_credit}

        return accounts, balances

    def validate(self, accounts, balances):
        t = self._totals
        c = self._computed
        debit_ok = t['debit'] is None or abs(c['debit'] - t['debit']) < 0.01
        credit_ok = t['credit'] is None or abs(c['credit'] - t['credit']) < 0.01
        return debit_ok and credit_ok

    def process(self, pdf_path, output_dir=None):
        import os
        if output_dir is None:
            output_dir = os.path.splitext(os.path.basename(pdf_path))[0]

        accounts, balances = self.extract(pdf_path)

        print(f"\nFile: {os.path.basename(pdf_path)}")
        txns = list(accounts.values())[0]
        print(f"  Transactions: {len(txns)}")
        print(f"  Computed Debit: {self._computed['debit']:,.2f}  Expected: {self._totals.get('debit', 0) or 0:,.2f}")
        print(f"  Computed Credit: {self._computed['credit']:,.2f}  Expected: {self._totals.get('credit', 0) or 0:,.2f}")

        valid = self.validate(accounts, balances)
        print(f"  Validation: {'PASS' if valid else 'FAIL'}")

        self.export_csv(accounts, output_dir)
        return valid
