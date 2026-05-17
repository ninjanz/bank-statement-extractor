# Bank Statement Extractor

Extract transactions from Malaysian bank PDF statements into CSV, then optionally convert to Beancount format.

## Supported Banks

| Bank | Type | Extractor | Validated |
|------|------|-----------|-----------|
| Maybank | Savings/Current | `mbb-savings` | Debit/Credit totals |
| Maybank | Credit Card | `mbb-cc` | Debit/Credit totals |
| CIMB | Credit Card | `cimb-cc` | Statement balance per card |

## Setup

```bash
uv sync
```

## Usage

### 1. Extract PDF to CSV

```bash
# Maybank savings/current accounts
python run.py extract --bank mbb-savings -p PASSWORD input/01-jan/*.pdf

# Maybank credit card
python run.py extract --bank mbb-cc -p PASSWORD input/cc/*.pdf

# CIMB credit card (handles multiple cards per statement)
python run.py extract --bank cimb-cc -p PASSWORD input/cimb-cc/*.PDF
```

Output CSVs go to `output/<filename>/` by default. Use `-o DIR` to change.

### 2. Convert CSV to Beancount

```bash
# Print to stdout
python run.py to-beancount output/**/*.csv

# Write to files
python run.py to-beancount -o beancount_out/ output/**/*.csv
```

Account mapping is configured in `accounts_config.json`.

## Architecture

```
PDF Statements
      │
      ▼
┌─────────────┐
│  Extractors │  Parse PDF text, validate against statement totals
│             │  Output: CSV (per account/card)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ Processors  │  Convert CSV to accounting formats
│             │  Output: Beancount transactions
└─────────────┘
```

### Adding a New Bank

1. Create `extractors/your_bank.py` inheriting from `BaseExtractor`
2. Implement `extract(pdf_path)` returning `(accounts_dict, balances_dict)`
3. Register in `extractors/__init__.py` and `run.py`

The base class provides: PDF reading, validation, CSV export, batch processing.

## Validation

Every extractor validates its output against totals printed in the statement (e.g., TOTAL DEBIT, STATEMENT BALANCE). If the computed sum doesn't match, it reports FAIL.
