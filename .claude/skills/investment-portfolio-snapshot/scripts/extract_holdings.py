#!/usr/bin/env python3
"""
extract_holdings.py
-------------------
STEP 1 + 2 of the investment-portfolio-snapshot skill.

Reads every .csv file in the working directory (raw brokerage exports),
finds the SYMBOL and MARKET VALUE columns in each (robust to different
brokerage layouts and preamble/footer junk), and produces a single
aggregated file `holdings_combined.csv` summing market value by symbol.

Output columns: symbol, market_value

No network needed. Pure standard library.
"""

import csv
import glob
import os
import re
import sys

WORKDIR = os.getcwd()

# Files we generate ourselves - never treat as input
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
# Candidate header names for the MARKET VALUE column
VALUE_ALIASES = [
    "market value", "mkt val (market value)", "mkt val", "current value",
    "value", "market val", "position value", "total value", "mkt value",
    "market value ($)", "current value ($)", "ending value", "balance",
]
# Headers we must NOT mistake for market value
VALUE_BLOCKLIST = [
    "day's value change", "days value change", "value change", "change",
    "cost basis", "cost", "unrealized", "gain", "loss", "% of account",
    "day change", "price", "last price",
]


def parse_amount(x):
    if x is None:
        return None
    s = str(x).replace("$", "").replace(",", "").replace("+", "").strip()
    # handle parentheses for negatives
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
        # fallback: contains match
        if sym_col is None:
            for alias in SYMBOL_ALIASES:
                for j, h in enumerate(row):
                    if alias in h:
                        sym_col = j
                        break
                if sym_col is not None:
                    break

        val_col = None
        # exact match first, skipping blocklisted headers
        for alias in VALUE_ALIASES:
            for j, h in enumerate(row):
                if h == alias and not any(b in h for b in VALUE_BLOCKLIST):
                    val_col = j
                    break
            if val_col is not None:
                break
        # contains match, still respecting blocklist
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


def extract_file(path, positions, problems):
    try:
        with open(path, newline="", encoding="utf-8-sig") as f:
            rows = list(csv.reader(f))
    except Exception as e:
        problems.append((os.path.basename(path), f"could not read file ({e})"))
        return

    if not rows:
        problems.append((os.path.basename(path), "file is empty"))
        return

    if is_own_output(rows):
        # Skip silently - this is a file the skill generated itself
        # (e.g. a renamed or copied holdings_combined.csv), not a brokerage export.
        return

    found = find_header_row(rows)
    if not found:
        problems.append((os.path.basename(path),
                         "could not find Symbol and Market Value columns"))
        return

    hdr_i, sym_col, val_col = found
    added = 0
    for row in rows[hdr_i + 1:]:
        if not row or len(row) <= max(sym_col, val_col):
            continue
        raw_sym = (row[sym_col] or "").strip()
        # strip trailing flags some brokerages add (e.g. "VTI !")
        sym = raw_sym.replace("!", "").strip().upper()
        if not sym:
            continue
        # skip obvious total/summary/footer lines
        low = sym.lower()
        if any(k in low for k in ("total", "subtotal", "grand", "account", "disclaimer")):
            continue
        val = parse_amount(row[val_col])
        if val is None:
            continue
        # keep cash-like rows even if symbol isn't a clean ticker
        if not looks_like_symbol(sym) and not any(
            k in low for k in ("cash", "money", "sweep", "fdic", "mmf", "settlement")
        ):
            # still keep it, but it will likely classify as "others"
            pass
        positions.setdefault(sym, 0.0)
        positions[sym] += val
        added += 1

    if added == 0:
        problems.append((os.path.basename(path),
                         "found headers but no usable holding rows"))


def main():
    csv_files = sorted(glob.glob(os.path.join(WORKDIR, "*.csv")))
    csv_files = [p for p in csv_files
                 if os.path.basename(p) not in OUTPUT_NAMES
                 and not os.path.basename(p).startswith("~$")]

    if not csv_files:
        print("ERROR: no .csv brokerage export files found in this folder.")
        sys.exit(1)

    print(f"Reading {len(csv_files)} CSV file(s):\n")
    positions = {}
    problems = []
    for path in csv_files:
        before = sum(1 for _ in positions)
        extract_file(path, positions, problems)
        print(f"  - {os.path.basename(path)}")

    if not positions:
        print("\nERROR: no holdings could be extracted from any file.")
        if problems:
            print("\nFiles I could not parse:")
            for name, why in problems:
                print(f"   - {name}: {why}")
        print("\nEach file needs a column for the ticker/symbol and one for market value.")
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
        print("\n  [!] Some files could not be fully parsed:")
        for name, why in problems:
            print(f"       - {name}: {why}")
        print("     Holdings from those files are NOT included. Check their format.")


if __name__ == "__main__":
    main()
