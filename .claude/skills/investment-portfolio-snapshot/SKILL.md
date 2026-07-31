---
name: investment-portfolio-snapshot
description: Generate a professional wealth-advisor HTML report showing a current snapshot of someone's investment portfolio, aggregated from raw brokerage CSV exports (any brokerage). Extracts holdings, classifies them by asset type and sector via yfinance, and produces a self-contained HTML report with an AI-written assessment and allocation charts. Use when the user wants a portfolio snapshot, allocation report, or wealth summary from their brokerage export files.
disable-model-invocation: true
---

# Investment Portfolio Snapshot

Turns a folder of raw brokerage CSV exports into a professional HTML portfolio
report with an advisor-style written assessment and modern allocation charts.
Works on Mac, Windows, and Linux.

## Step 0 — Check dependencies FIRST (before anything else)

This skill needs:
- Python packages `yfinance` and `matplotlib`
- A free Alpha Vantage API key (for ETF sector look-through)

The report is generated as a single self-contained HTML file (charts embedded
as base64 images) — no PDF converter or other external tool is required.

Run this check:
```
python3 -c "import yfinance" 2>/dev/null && echo "yfinance OK" || echo "yfinance MISSING"
python3 -c "import matplotlib" 2>/dev/null && echo "matplotlib OK" || echo "matplotlib MISSING"
[ -n "$ALPHAVANTAGE_API_KEY" ] && echo "ALPHAVANTAGE_API_KEY OK" || echo "ALPHAVANTAGE_API_KEY MISSING"
```

For anything reported MISSING, tell the user what's missing and ask permission to
install/set it. Only proceed after they agree:
- `yfinance` or `matplotlib` missing:
  ```
  pip install yfinance matplotlib
  ```
  On Windows, if `pip` is not recognized, try `pip3` instead (or vice versa) —
  which one works depends on how Python was installed. Same applies to every
  `python3 ...` command in this skill: on Windows, try `python` if `python3`
  isn't recognized.
- `ALPHAVANTAGE_API_KEY` missing:
  Tell the user this key is a FALLBACK for ETF sector look-through. The skill
  always tries yfinance first for every symbol (no key needed); Alpha Vantage
  is only called for an ETF when yfinance has no sector data for it. This
  keeps Alpha Vantage usage low and conserves its free-tier daily limit. It
  is free:
  1. Sign up at https://www.alphavantage.co/support/#api-key (no credit card)
  2. Easiest option: save a plain-text file named `alphavantage_key.txt` in
     this folder, containing only the key (no quotes, no extra text). The
     skill checks for this file automatically every run — no re-entry needed.
     **On a Mac, TextEdit saves Rich Text (.rtf) by default even if you name
     the file `.txt`.** Tell the user to either use a plain-text editor, or in
     TextEdit go to Format > Make Plain Text before saving. The skill detects
     and warns about an RTF file rather than silently failing.
  3. Alternative: `export ALPHAVANTAGE_API_KEY=their_key_here` in Terminal
     (session-only unless added to their shell profile). The env var takes
     priority over the key file if both are set.
  If the user prefers to skip this entirely, that's fine — the skill still
  runs; ETFs will show as "Unclassified" in the sector chart instead of being
  broken down.

The skill checks for the key in this order: environment variable, then `alphavantage_key.txt` / `.alphavantage_key` / `av_key.txt` in the working folder.

Do not proceed to Step 1 until dependencies are OK. The API key is
optional but strongly recommended — proceed without it only if the user declines.

## Step 1 — Extract & combine holdings
```
python3 ${CLAUDE_SKILL_DIR}/scripts/extract_holdings.py
```
Reads every CSV export in the folder, finds the symbol and market-value columns
in each, and writes `holdings_combined.csv` (summing duplicates across files,
so the same symbol held at two brokerages adds up correctly into one total).

This step also scans each file and reports, by filename:
- **Errors** (file excluded from the report): empty files, unreadable/wrong-format
  files, or files where no Symbol + Market Value column pair could be found.
- **Warnings** (file still processed, but flag to the user): a likely account
  number or similar identifier detected in the file, or transaction rows
  (trades, dividends, debits/credits, transfers) that were ignored because this
  report only shows current holdings, not activity history.

**Always relay every warning and error to the user by filename, in plain
language**, even if the run otherwise succeeds. For an account-number warning,
explicitly tell the user which file it's in and ask them to remove that column
before their next run — do not proceed to guess or redact it yourself. For a
file-level error, tell the user clearly that file's holdings were NOT included
and why, so they can fix and re-run if needed.

## Step 2 — Enrich with asset type & sector
```
python3 ${CLAUDE_SKILL_DIR}/scripts/enrich_holdings.py
```
Classifies each holding via yfinance and writes `holdings_enriched.csv`. Results
are cached in `classification_cache.csv`; the user may hand-edit that file to
correct any misclassification, then re-run this step. If many holdings come back
as "Others", mention that they can correct the cache and re-run.

## Step 3 — Write the advisor assessment
Read `holdings_enriched.csv` yourself and write a portfolio description of about
2–3 short paragraphs, in the voice of a professional wealth advisor. It must:
- Describe the current state first: the equity/bond/cash mix, the risk level it
  implies, and any notable concentration (sector, single holding, cash).
- Then give a LIGHT opinion — what stands out, framed as an observation, not a
  directive.
- Stay measured and professional. Do not invent data not in the file.
Save this to `assessment.txt` (plain text, blank line between paragraphs).

## Step 4 — Build the HTML report
Ask the user what title/name they want (their name, or e.g. "My Portfolio").
If `portfolio_snapshot.html` already exists in the folder from a previous run,
overwrite it directly — do not ask the user whether to proceed.
```
python3 ${CLAUDE_SKILL_DIR}/scripts/build_report.py --description-file assessment.txt --name "PORTFOLIO NAME"
```
Produces `portfolio_snapshot.html` — a single self-contained file (charts are
embedded, no external files needed) that opens directly in any browser. It has:
- Title, date, total value, holding count
- The assessment you wrote (plus a "not financial advice" disclaimer)
- Two modern charts: By Asset Type (donut, all holdings) and
  By Sector (bars, individual stocks only, with coverage %)

## Step 5 — Done
Tell the user the report is ready at `portfolio_snapshot.html` — they can open it directly in any browser.

## Rules
- Always run Step 0 first; never skip the dependency check.
- **Always overwrite existing output files without asking.** This skill is
  meant to be re-run repeatedly on the same folder. `holdings_combined.csv`,
  `holdings_enriched.csv`, `assessment.txt`, and `portfolio_snapshot.html` are
  all expected to be regenerated fresh every run. If any of these already
  exist from a prior run, overwrite them directly — do not ask the user for
  confirmation or treat this as a conflict. The one exception is
  `classification_cache.csv`, which persists intentionally across runs (do
  not delete it; the scripts update it in place).
- The report always prints a clear "not financial advice / guide only" note.
- Classification is best-effort. Offer the cache-edit + re-run path if needed.
- Never invent market values or holdings. Use only what the files contain.
- This skill assumes all values are in USD and does not convert currencies.
  If the user's files contain non-USD values, warn them that totals and the
  report's "$" labeling will be inaccurate.
- Do not modify the user's raw export files.
