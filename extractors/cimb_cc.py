import re
from datetime import datetime
from .base import BaseExtractor

CARD_HEADER_RE = re.compile(r'^(\d{4}-\d{4}-\d{4}-\d{4}|[X\d]{4}-[X\d]{4}-[X\d]{4}-\d{4})\s+')
STMT_DATE_RE = re.compile(r'(\d{1,2})\s+(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\s+(\d{4})')
MONTHS = {'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
           'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12}
TRANSACTION_RE = re.compile(
    r'^(\d{2}\s+[A-Z]{3})\s+(\d{2}\s+[A-Z]{3})\s+(.+?[MY])\s+([\d,]+\.\d{2})(CR)?$'
)
FOREIGN_TRANSACTION_RE = re.compile(
    r'^(\d{2}\s+[A-Z]{3})\s+(\d{2}\s+[A-Z]{3})\s+(.+?[^MY])\s+([\d,]+\.\d{2})(CR)?$'
)
PREV_BALANCE_RE = re.compile(r'^PREVIOUS BALANCE\s+([\d,]+\.\d{2})')
STMT_BALANCE_RE = re.compile(r'^STATEMENT BALANCE\s+([\d,]+\.\d{2})')
FOREIGN_CURRENCY_NEXT_LINE_RE = re.compile(r'^\d+([A-Z\s]*)([\d,]+\.\d{2})$')
PROMO_RE = re.compile(r'^(Travel to|RM\d+|back on flights|Deals MY|Easy Pay|Now till|0% Easy)')
CONTINUATION_RE = re.compile(r'^(FROM\s|CREDIT CARD$|[A-Z]{3}$)')

NOISE_STRS = [
    'CONTINUED ON NEXT PAGE', 'ON-GOING PROMOTION', 'For Lost / Stolen',
    'UntukLaporan', 'Pertanyaan atau', 'Persekutuan; Tel:',
    'Transaction Details', 'Posting Date', 'Tarikh Pos',
    'Page / Mukasurat', 'CIMB Group has issued', 'Please call',
    'WARNING ON PAYING', 'If you make only', 'it will take you',
    'available on our website', 'Jika anda hanya', 'faedah kena bayar',
    'jelas anda akan', 'lanjut. Selain itu', 'www.cimb.com.my',
    'www.bankinginfo.com.my', 'Credit Card Bonus Points',
    'Credit Card No.', 'No. Kad Kredit', 'Summary of Your Total',
    '*includes Bonus Points', 'Points Brought Forward', 'Mata Dibawa',
    'Points Expiring By', 'Mata Yang Akan', 'CREDIT CARD STATEMENT',
    'Statement Date', 'Tarikh Penyata', 'Combined Credit Limit',
    'Gabungan Had Kredit', 'No more waiting', 'ATM, recurring',
    'Cards Summary', 'Card Type', 'Jenis Kad', 'TRAVEL WORLD', 'MASTERCARD',
]


def _is_noise(line):
    if not line:
        return True
    for p in NOISE_STRS:
        if p in line:
            return True
    if PROMO_RE.match(line):
        return True
    return False


def _card_from_header(line):
    m = CARD_HEADER_RE.match(line)
    if m and ('PRINCIPAL' in line or 'N ZAINAL' in line or 'SUPPLEMENTARY' in line):
        return m.group(1)[-4:]
    return None


def _resolve_date(date_str, stmt_year, stmt_month):
    """Convert '28 DEC' to '28/12/2025' using statement date for year inference."""
    parts = date_str.strip().split()
    if len(parts) != 2:
        return date_str
    day, mon = parts
    mon_num = MONTHS.get(mon)
    if not mon_num:
        return date_str
    year = stmt_year - 1 if mon_num > stmt_month else stmt_year
    return f'{int(day):02d}/{mon_num:02d}/{year}'


class CimbCCExtractor(BaseExtractor):

    def _find_statement_date(self, all_lines):
        for line in all_lines[:30]:
            m = STMT_DATE_RE.search(line)
            if m:
                day, mon, year = m.groups()
                return int(year), MONTHS[mon]
        return None, None

    def extract(self, pdf_path):
        all_lines = self.read_pdf_lines(pdf_path)
        stmt_year, stmt_month = self._find_statement_date(all_lines)
        cards = {}
        current_card = None
        transactions = []
        statement_balances = {}

        i = 0
        while i < len(all_lines):
            line = all_lines[i].strip()

            card = _card_from_header(line)
            if card:
                if current_card and transactions:
                    cards.setdefault(current_card, []).extend(transactions)
                    transactions = []
                current_card = card
                i += 1
                continue

            stmt_m = STMT_BALANCE_RE.match(line)
            if stmt_m:
                statement_balances[current_card] = float(stmt_m.group(1).replace(',', ''))
                if current_card and transactions:
                    cards.setdefault(current_card, []).extend(transactions)
                    transactions = []
                i += 1
                continue

            prev_m = PREV_BALANCE_RE.match(line)
            if prev_m:
                transactions.append({
                    'Posting Date': '', 'Transaction Date': '',
                    'Description': 'PREVIOUS BALANCE',
                    'Amount': float(prev_m.group(1).replace(',', '')),
                })
                i += 1
                continue

            if _is_noise(line):
                i += 1
                continue

            if not current_card:
                i += 1
                continue

            tx_m = FOREIGN_TRANSACTION_RE.match(line)
            if tx_m:
                post_date, tx_date, desc, amount, cr = tx_m.groups()
                amt = float(amount.replace(',', ''))
                if cr == 'CR':
                    amt = -amt

                j = i + 1
                while j < len(all_lines):
                    next_line = all_lines[j].strip()
                    if not next_line:
                        j += 1
                        continue
                    if FOREIGN_CURRENCY_NEXT_LINE_RE.match(next_line):
                        fx, fx_amt = FOREIGN_CURRENCY_NEXT_LINE_RE.match(next_line).groups()
                        desc += ' [' + fx + ' ' + fx_amt + ']'
                        j += 1
                        continue
                    break

                transactions.append({
                    'Posting Date': _resolve_date(post_date, stmt_year, stmt_month),
                    'Transaction Date': _resolve_date(tx_date, stmt_year, stmt_month),
                    'Description': desc, 'Amount': amt,
                })
                i = j
                continue
            
            tx_m = TRANSACTION_RE.match(line)
            if tx_m:
                post_date, tx_date, desc, amount, cr = tx_m.groups()
                amt = float(amount.replace(',', ''))
                if cr == 'CR':
                    amt = -amt

                j = i + 1
                while j < len(all_lines):
                    next_line = all_lines[j].strip()
                    if not next_line:
                        j += 1
                        continue
                    if CONTINUATION_RE.match(next_line):
                        desc += ' ' + next_line
                        j += 1
                        continue
                    break

                transactions.append({
                    'Posting Date': _resolve_date(post_date, stmt_year, stmt_month),
                    'Transaction Date': _resolve_date(tx_date, stmt_year, stmt_month),
                    'Description': desc, 'Amount': amt,
                })
                i = j
                continue

            i += 1

        if current_card and transactions:
            cards.setdefault(current_card, []).extend(transactions)

        return cards, statement_balances
