#!/usr/bin/env python3
"""Unified CLI for bank statement extraction and processing.

Usage:
    python run.py extract --bank mbb-savings --password PWD input/01-jan/*.pdf
    python run.py extract --bank mbb-cc --password PWD input/cc/*.pdf
    python run.py extract --bank cimb-cc --password PWD input/cimb-cc/*.PDF
    python run.py to-beancount output/**/*.csv
"""
import argparse
import glob
import os
import sys

from extractors import MbbSavingsExtractor, MbbCCExtractor, CimbCCExtractor
from processors.csv_to_beancount import csv_to_beancount

EXTRACTORS = {
    'mbb-savings': MbbSavingsExtractor,
    'mbb-cc': MbbCCExtractor,
    'cimb-cc': CimbCCExtractor,
}


def cmd_extract(args):
    cls = EXTRACTORS[args.bank]
    ext = cls(password=args.password)

    files = []
    for pattern in args.files:
        files.extend(glob.glob(pattern))
    files = sorted(set(files))

    if not files:
        print('No files found.')
        sys.exit(1)

    os.makedirs(args.output, exist_ok=True)
    all_pass = True
    for f in files:
        out_dir = os.path.join(args.output, os.path.splitext(os.path.basename(f))[0])
        if not ext.process(f, out_dir):
            all_pass = False

    print(f"\n{'='*50}")
    print(f"Overall: {'ALL PASS' if all_pass else 'SOME FAILED'}")
    sys.exit(0 if all_pass else 1)


def cmd_beancount(args):
    files = []
    for pattern in args.files:
        files.extend(glob.glob(pattern))
    files = sorted(set(files))

    if not files:
        print('No CSV files found.')
        sys.exit(1)

    for csv_file in files:
        result = csv_to_beancount(csv_file, config_file=args.config)
        if args.output:
            # Preserve parent dir structure (e.g., output/statement_name/card.csv → beancount_output/statement_name/card.beancount)
            parent = os.path.basename(os.path.dirname(csv_file))
            out_dir = os.path.join(args.output, parent)
            os.makedirs(out_dir, exist_ok=True)
            out_path = os.path.join(out_dir, os.path.splitext(os.path.basename(csv_file))[0] + '.beancount')
            with open(out_path, 'w', encoding='utf-8') as f:
                f.write(result)
            print(f'Written: {out_path}')
        else:
            print(result)
            print()


def main():
    parser = argparse.ArgumentParser(description='Bank Statement Extractor & Processor')
    sub = parser.add_subparsers(dest='command', required=True)

    # Extract command
    p_ext = sub.add_parser('extract', help='Extract transactions from PDF statements')
    p_ext.add_argument('--bank', required=True, choices=EXTRACTORS.keys(), help='Bank/statement type')
    p_ext.add_argument('--password', '-p', help='PDF password')
    p_ext.add_argument('--output', '-o', default='output', help='Output directory (default: output/)')
    p_ext.add_argument('files', nargs='+', help='PDF files or glob patterns')

    # To-beancount command
    p_bc = sub.add_parser('to-beancount', help='Convert CSVs to Beancount format')
    p_bc.add_argument('--config', '-c', default='accounts_config.json', help='Accounts config file')
    p_bc.add_argument('--output', '-o', help='Output directory (default: stdout)')
    p_bc.add_argument('files', nargs='+', help='CSV files or glob patterns')

    args = parser.parse_args()
    if args.command == 'extract':
        cmd_extract(args)
    elif args.command == 'to-beancount':
        cmd_beancount(args)


if __name__ == '__main__':
    main()
