import re
from .base import BaseExtractor

TRANSACTION_RE = re.compile(r'^(\d{2}/\d{2}(?:/\d{2})?)\s+(.+?)\s+([\d,]+\.\d{2})([+-])\s+([\d,]+\.\d{2})$')
BEGINNING_BAL_RE = re.compile(r'^BEGINNING BALANCE\s+([\d,]+\.\d{2})')
ENDING_BAL_RE = re.compile(r'^ENDING BALANCE\s*:\s*([\d,]+\.\d{2})')
TOTAL_DEBIT_RE = re.compile(r'^TOTAL DEBIT\s*:\s*([\d,]+\.\d{2})')
TOTAL_CREDIT_RE = re.compile(r'^TOTAL CREDIT\s*:\s*([\d,]+\.\d{2})')
HEADER_RE = re.compile(r'ENTRY DATE|TRANSACTION DESCRIPTION|STATEMENT BALANCE')
CONTINUATION_STOP = re.compile(r'^\d{2}/\d{2}|^ENDING BALANCE|^TOTAL |^BAKI LEGAR|^Perhati|^LEDGER|^\(\d\)')


class MbbSavingsExtractor(BaseExtractor):

    def extract(self, pdf_path):
        all_lines = self.read_pdf_lines(pdf_path)
        transactions = []
        totals = {'debit': 0, 'credit': 0, 'ending_balance': 0, 'beginning_balance': 0}
        in_transactions = False

        i = 0
        while i < len(all_lines):
            line = all_lines[i].strip()

            # Detect ending balance (the real stop for validation, not for parsing)
            m = ENDING_BAL_RE.match(line)
            if m:
                totals['ending_balance'] = float(m.group(1).replace(',', ''))
                i += 1
                continue

            m = TOTAL_DEBIT_RE.match(line)
            if m:
                totals['debit'] = float(m.group(1).replace(',', ''))
                i += 1
                continue

            m = TOTAL_CREDIT_RE.match(line)
            if m:
                totals['credit'] = float(m.group(1).replace(',', ''))
                i += 1
                continue

            m = BEGINNING_BAL_RE.match(line)
            if m:
                totals['beginning_balance'] = float(m.group(1).replace(',', ''))
                in_transactions = True
                i += 1
                continue

            if HEADER_RE.search(line):
                in_transactions = True
                i += 1
                continue

            if not in_transactions:
                i += 1
                continue

            m = TRANSACTION_RE.match(line)
            if m:
                date, desc, amount_str, sign, balance = m.groups()
                amount = float(amount_str.replace(',', ''))
                debit = amount if sign == '-' else None
                credit = amount if sign == '+' else None

                # Consume continuation lines
                j = i + 1
                while j < len(all_lines):
                    next_line = all_lines[j].strip()
                    if not next_line:
                        j += 1
                        continue
                    if CONTINUATION_STOP.match(next_line):
                        break
                    desc += ' ' + next_line
                    j += 1

                transactions.append({
                    'Date': date, 'Description': desc,
                    'Debit': debit, 'Credit': credit,
                })
                i = j
                continue

            i += 1

        # Use account number from filename or single "account"
        acct_id = 'savings'
        accounts = {acct_id: transactions}

        # Validate: total debits and credits should match
        computed_debit = sum(t['Debit'] for t in transactions if t['Debit'])
        computed_credit = sum(t['Credit'] for t in transactions if t['Credit'])

        # Statement balance = beginning + credits - debits
        balances = {}
        if totals['debit'] > 0 or totals['credit'] > 0:
            balances[acct_id] = totals['ending_balance']

        # Store totals for external validation
        self._totals = totals
        self._computed = {'debit': computed_debit, 'credit': computed_credit}

        return accounts, balances

    def validate(self, accounts, balances):
        """Custom validation: check debit/credit totals match statement."""
        if not self._totals.get('debit') and not self._totals.get('credit'):
            return True
        debit_ok = abs(self._computed['debit'] - self._totals['debit']) < 0.01
        credit_ok = abs(self._computed['credit'] - self._totals['credit']) < 0.01
        return debit_ok and credit_ok

    def process(self, pdf_path, output_dir=None):
        import os
        if output_dir is None:
            output_dir = os.path.splitext(os.path.basename(pdf_path))[0]

        accounts, balances = self.extract(pdf_path)

        print(f"\nFile: {os.path.basename(pdf_path)}")
        txns = list(accounts.values())[0]
        print(f"  Transactions: {len(txns)}")
        print(f"  Computed Debit: {self._computed['debit']:,.2f}  Expected: {self._totals['debit']:,.2f}")
        print(f"  Computed Credit: {self._computed['credit']:,.2f}  Expected: {self._totals['credit']:,.2f}")

        valid = self.validate(accounts, balances)
        print(f"  Validation: {'PASS' if valid else 'FAIL'}")

        self.export_csv(accounts, output_dir)
        return valid
