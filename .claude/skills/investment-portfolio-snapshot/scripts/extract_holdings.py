#!/usr/bin/env python3
"""
extract_holdings.py
-------------------
STEP 1 + 2 of the investment-portfolio-snapshot skill.

Reads every .csv file in the working directory (raw brokerage exports),
finds the SYMBOL and MARKET VALUE columns in each (robust to different
brokerage layouts and preamble/footer junk), and produces a single
aggregated file `holdings_combined.csv` summing market value by symbol.

Also scans each file for content that should NOT be there - account
numbers, transaction rows (trades, dividends, debits/credits) - and
reports clear, actionable warnings rather than silently including or
silently failing on them.

Output columns: symbol, market_value

No network needed. Pure standard library.
"""

import csv
import glob
import os
import re
import sys

WORKDIR = os.getcwd()

# Every file this skill (or a later step in it) writes to the folder.
# These must NEVER be re-read as if they were a brokerage export.
OUTPUT_NAMES = {
    "holdings_combined.csv",
    "holdings_enriched.csv",
    "classification_cache.csv",
}

# Candidate header names for the SYMBOL column (lowercased, exact-ish)
SYMBOL_ALIASES = [
    "symbol", "ticker", "ticker symbol", "security symbol", "security id",
    "security", "investment", "holding", "fund", "cusip symbol",
]
# Candidate header names for the MARKET VALUE column.
# Per the README: current value / current market value / market value /
# mkt value / value are all accepted spellings.
VALUE_ALIASES = [
    "current market value", "market value", "mkt val (market value)",
    "mkt val", "current value", "value", "market val", "position value",
    "total value", "mkt value", "market value ($)", "current value ($)",
    "ending value", "balance",
]
# Headers we must NOT mistake for market value
VALUE_BLOCKLIST = [
    "day's value change", "days value change", "value change", "change",
    "cost basis", "cost", "unrealized", "gain", "loss", "% of account",
    "day change", "price", "last price",
]

# Row-level keywords that indicate a TRANSACTION, not a current holding.
# The report shows a current snapshot only - these rows must be ignored,
# not summed in as if they were positions.
TRANSACTION_KEYWORDS = [
    "buy", "sell", "sold", "bought", "trade", "transaction",
    "dividend received", "dividend reinvest", "dividend reinvested",
    "div reinvest", "reinvestment", "qualified dividend",
    "debit", "credit", "deposit", "withdrawal", "transfer",
    "interest earned", "interest paid", "fee", "commission",
    "journal", "adjustment", "wire", "ach",
]

# Column header keywords that suggest this whole COLUMN is a transaction
# type/description column, not a holding - if present, rows are checked
# against it for the keywords above.
TRANSACTION_COLUMN_HINTS = [
    "transaction type", "action", "activity", "description", "type",
]

# Patterns that suggest a column contains ACCOUNT NUMBERS rather than
# portfolio data. Used only to warn the user - we never print the values
# themselves, just flag that they appear present.
ACCOUNT_NUMBER_HEADER_HINTS = [
    "account number", "account #", "acct number", "acct #", "account no",
    "routing number", "routing #",
]
# A bare, long run of digits (7+) in a non-symbol, non-value cell is also
# a strong signal of an account number even without a matching header.
ACCOUNT_NUMBER_PATTERN = re.compile(r"\b\d{7,}\b")


def parse_amount(x):
    if x is None:
        return None
    s = str(x).replace("$", "").replace(",", "").replace("+", "").strip()
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    if s in ("--", "", "N/A", "#N/A", "n/a"):
        return None
    try:
        v = float(s)
        return -v if neg else v
    except ValueError:
        return None


def looks_like_symbol(s):
    """A plausible ticker: 1-6 letters, optionally with . or - (e.g. BRK.B, BTC-USD)."""
    if not s:
        return False
    s = s.strip().upper()
    return bool(re.match(r"^[A-Z]{1,6}([.\-][A-Z0-9]{1,6})?$", s))


def find_header_row(rows):
    """
    Scan the first ~15 rows for the one that contains BOTH a symbol-like column
    and a value-like column. Returns (header_index, sym_col, val_col) or None.
    Brokerage exports often have title/disclaimer rows before the real header.
    """
    limit = min(len(rows), 15)
    for i in range(limit):
        row = [(c or "").strip().lower() for c in rows[i]]
        if not any(row):
            continue

        sym_col = None
        for alias in SYMBOL_ALIASES:
            for j, h in enumerate(row):
                if h == alias:
                    sym_col = j
                    break
            if sym_col is not None:
                break
        if sym_col is None:
            for alias in SYMBOL_ALIASES:
                for j, h in enumerate(row):
                    if alias in h:
                        sym_col = j
                        break
                if sym_col is not None:
                    break

        val_col = None
        for alias in VALUE_ALIASES:
            for j, h in enumerate(row):
                if h == alias and not any(b in h for b in VALUE_BLOCKLIST):
                    val_col = j
                    break
            if val_col is not None:
                break
        if val_col is None:
            for alias in VALUE_ALIASES:
                for j, h in enumerate(row):
                    if alias in h and not any(b in h for b in VALUE_BLOCKLIST):
                        val_col = j
                        break
                if val_col is not None:
                    break

        if sym_col is not None and val_col is not None and sym_col != val_col:
            return (i, sym_col, val_col)
    return None


OWN_SCHEMA_HEADERS = {
    "symbol,market_value",
    "symbol,market_value,asset_type,sector",
    "symbol,market_value,asset_type,sector,sector_weights",
    "symbol,asset_type,sector",
    "symbol,asset_type,sector,sector_weights",
}


def is_own_output(rows):
    """True if this file's header row matches a schema this skill itself writes."""
    if not rows:
        return False
    header = ",".join((c or "").strip().lower() for c in rows[0])
    return header in OWN_SCHEMA_HEADERS


def is_transaction_row(row, header_row):
    """
    True if this row looks like a transaction (trade, dividend, debit/credit,
    transfer, fee, etc.) rather than a current holding. Checked against the
    whole row's text, since brokerages put the transaction type in different
    columns (e.g. 'Action', 'Description', 'Activity').
    """
    row_text = " ".join((c or "").strip().lower() for c in row)
    return any(kw in row_text for kw in TRANSACTION_KEYWORDS)


def scan_for_account_numbers(rows, header_row):
    """
    Look for signs of account numbers in this file: either a header that
    names an account-number column, or long digit runs in cells that are
    not the symbol or value columns. Returns True if suspected, without
    ever printing or logging the actual numbers found.
    """
    header_lower = [(c or "").strip().lower() for c in header_row]
    if any(any(hint in h for hint in ACCOUNT_NUMBER_HEADER_HINTS) for h in header_lower):
        return True

    # Sample up to 20 data rows for long digit runs, ignoring cells that
    # are plausibly a symbol or a dollar amount.
    for row in rows[1:21]:
        for cell in row:
            c = (cell or "").strip()
            if not c or looks_like_symbol(c):
                continue
            if c.replace(",", "").replace("$", "").replace(".", "").replace("-", "").isdigit() is False:
                continue
            digits_only = re.sub(r"[^\d]", "", c)
            if len(digits_only) >= 7 and ACCOUNT_NUMBER_PATTERN.search(c):
                # Skip if this cell parses as a large but plausible dollar
                # amount (e.g. "1000000.00" for a $1M position) - only flag
                # when it doesn't look like a formatted currency value.
                if parse_amount(c) is not None and ("." in c or "," in c):
                    continue
                return True
    return False


def extract_file(path, positions, problems, warnings):
    name = os.path.basename(path)
    try:
        with open(path, newline="", encoding="utf-8-sig") as f:
            rows = list(csv.reader(f))
    except Exception as e:
        problems.append((name, f"could not read this file — it may not be a valid CSV "
                               f"(error: {e}). Re-export it from your brokerage as CSV "
                               f"and try again."))
        return

    if not rows or all(not any((c or "").strip() for c in r) for r in rows):
        problems.append((name, "this file is empty. Check that the export actually "
                               "contains your positions and re-upload it."))
        return

    if is_own_output(rows):
        return  # this skill's own output file - not a brokerage export, skip silently

    found = find_header_row(rows)
    if not found:
        problems.append((name, "could not find a Symbol column and a Market Value column "
                               "(accepted names: Symbol/Ticker, and Current Value / "
                               "Current Market Value / Market Value / Mkt Value / Value). "
                               "This may not be a positions export, or its format isn't "
                               "recognized yet."))
        return

    hdr_i, sym_col, val_col = found
    header_row = rows[hdr_i]

    if scan_for_account_numbers(rows, header_row):
        warnings.append((name, "this file appears to contain an account number or similar "
                               "identifier. Please remove that column (and any other personal "
                               "info) before re-running, even though the skill will not use it."))

    added = 0
    skipped_transactions = 0
    for row in rows[hdr_i + 1:]:
        if not row or len(row) <= max(sym_col, val_col):
            continue
        if is_transaction_row(row, header_row):
            skipped_transactions += 1
            continue
        raw_sym = (row[sym_col] or "").strip()
        sym = raw_sym.replace("!", "").strip().upper()
        if not sym:
            continue
        low = sym.lower()
        if any(k in low for k in ("total", "subtotal", "grand", "account", "disclaimer")):
            continue
        val = parse_amount(row[val_col])
        if val is None:
            continue
        positions.setdefault(sym, 0.0)
        positions[sym] += val
        added += 1

    if skipped_transactions:
        warnings.append((name, f"ignored {skipped_transactions} row(s) that looked like "
                               f"transactions (trades, dividends, debits/credits, transfers) "
                               f"rather than current holdings — only current positions are used."))

    if added == 0:
        problems.append((name, "found a Symbol and Market Value column, but no usable "
                               "holding rows underneath. Check the file has actual position "
                               "rows below the header."))


def main():
    all_files = os.listdir(WORKDIR)
    csv_files_all = [f for f in all_files if f.lower().endswith(".csv")]
    non_csv_hint = [f for f in all_files
                     if not f.lower().endswith(".csv")
                     and f.lower().endswith((".xlsx", ".xls", ".tsv", ".txt"))]

    csv_files = sorted(glob.glob(os.path.join(WORKDIR, "*.csv")))
    csv_files = [p for p in csv_files
                 if os.path.basename(p) not in OUTPUT_NAMES
                 and not os.path.basename(p).startswith("~$")]

    if not csv_files:
        print("ERROR: no .csv files found in this folder.")
        if non_csv_hint:
            print("\nFound these non-CSV files instead, which this skill cannot read directly:")
            for f in non_csv_hint:
                print(f"   - {f}")
            print("\nRe-export your positions from your brokerage as CSV (not Excel/TSV/text)")
            print("and place the .csv file(s) in this folder, then run again.")
        else:
            print("\nPlace your brokerage's exported CSV file(s) in this folder and run again.")
        sys.exit(1)

    print(f"Reading {len(csv_files)} CSV file(s):\n")
    positions = {}
    problems = []
    warnings = []
    for path in csv_files:
        extract_file(path, positions, problems, warnings)
        print(f"  - {os.path.basename(path)}")

    if warnings:
        print("\n  [!] Please review before re-running (not blocking, but recommended):")
        for name, why in warnings:
            print(f"       - {name}: {why}")

    if not positions:
        print("\nERROR: no holdings could be extracted from any file.")
        if problems:
            print("\nFiles I could not process:")
            for name, why in problems:
                print(f"   - {name}: {why}")
        print("\nEach file needs a Symbol/Ticker column and a Current Value / Market Value column.")
        sys.exit(1)

    out_path = os.path.join(WORKDIR, "holdings_combined.csv")
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["symbol", "market_value"])
        for sym in sorted(positions.keys()):
            w.writerow([sym, format(round(positions[sym], 2), ".2f")])

    total = sum(positions.values())
    print(f"\n  Combined {len(positions)} unique holdings, total ${total:,.2f}")
    print(f"  Wrote: {out_path}")

    if problems:
        print("\n  [!] Some files could not be fully processed:")
        for name, why in problems:
            print(f"       - {name}: {why}")
        print("     Holdings from those files are NOT included. Fix and re-run if needed.")


if __name__ == "__main__":
    main()
