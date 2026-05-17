import os
import glob
from abc import ABC, abstractmethod
import pdfplumber
import pandas as pd


class BaseExtractor(ABC):
    """Base class for bank statement extractors."""

    def __init__(self, password=None):
        self.password = password

    def read_pdf_lines(self, pdf_path):
        with pdfplumber.open(pdf_path, password=self.password) as pdf:
            lines = []
            for page in pdf.pages:
                text = page.extract_text() or ''
                lines.extend(text.splitlines())
        return lines

    @abstractmethod
    def extract(self, pdf_path):
        """Extract transactions from a PDF. Returns (accounts, balances) where:
        - accounts: dict mapping account_id -> list of transaction dicts
        - balances: dict mapping account_id -> expected statement balance
        Each transaction dict must have at minimum: Description, Amount
        """
        pass

    def validate(self, accounts, balances):
        """Validate computed sums against statement balances. Returns True if all match."""
        all_valid = True
        for acct_id, txns in accounts.items():
            df = pd.DataFrame(txns)
            computed = df['Amount'].sum()
            expected = balances.get(acct_id, 0)
            if abs(computed - expected) >= 0.01:
                all_valid = False
        return all_valid

    def export_csv(self, accounts, output_dir):
        """Export each account's transactions to a separate CSV."""
        os.makedirs(output_dir, exist_ok=True)
        paths = {}
        for acct_id, txns in accounts.items():
            df = pd.DataFrame(txns)
            csv_path = os.path.join(output_dir, f"card_{acct_id}.csv")
            df.to_csv(csv_path, index=False)
            paths[acct_id] = csv_path
        return paths

    def process(self, pdf_path, output_dir=None):
        """Full pipeline: extract, validate, export. Returns True if valid."""
        if output_dir is None:
            output_dir = os.path.splitext(os.path.basename(pdf_path))[0]

        accounts, balances = self.extract(pdf_path)

        print(f"\nFile: {os.path.basename(pdf_path)}")
        print(f"Accounts: {list(accounts.keys())}")

        all_valid = True
        for acct_id, txns in accounts.items():
            df = pd.DataFrame(txns)
            computed = df['Amount'].sum()
            expected = balances.get(acct_id, 0)
            match = abs(computed - expected) < 0.01
            if not match:
                all_valid = False

            print(f"\n  Account {acct_id}:")
            print(f"    Transactions: {len(txns)}")
            print(f"    Computed: {computed:,.2f}")
            print(f"    Expected: {expected:,.2f}")
            print(f"    {'PASS' if match else 'FAIL'}")

        self.export_csv(accounts, output_dir)
        return all_valid

    def process_batch(self, input_dir, pattern='*.PDF', output_base='output'):
        """Process all matching PDFs in a directory."""
        pdfs = sorted(glob.glob(os.path.join(input_dir, pattern)))
        if not pdfs:
            print(f"No files matching {pattern} in {input_dir}")
            return False

        all_pass = True
        for pdf_path in pdfs:
            out_dir = os.path.join(output_base, os.path.splitext(os.path.basename(pdf_path))[0])
            if not self.process(pdf_path, out_dir):
                all_pass = False

        print(f"\n{'='*50}")
        print(f"Overall: {'ALL PASS' if all_pass else 'SOME FAILED'}")
        return all_pass
