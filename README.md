# Investment Portfolio Snapshot

Generate a professional, wealth-advisor-style HTML report of your current
investment portfolio from your brokerage export files — from any brokerage.

The report includes:
- A written assessment of your portfolio (allocation, risk posture, what stands out)
- A **By Asset Type** chart (stocks, bonds, cash, commodities, crypto, others)
- A **By Sector** chart (for your individual stock holdings)

> This report is an informational guide only. It is **not financial advice.**

---

## What you need (one-time setup)

1. **Claude Code** (in the Claude desktop app, the `</>` Code tab, or the CLI).

2. **Python 3** (already on most Macs).

3. Dependencies: the skill **checks for these automatically** when you run it
   and offers to install anything missing, so you can skip this step. If you'd
   rather install them up front, in Terminal:
   ```
   pip install yfinance matplotlib
   ```
   The report is a single self-contained HTML file — no PDF converter or other
   tool needed. Just open it in any browser.

4. **Optional but recommended: a free Alpha Vantage API key.** ETF sector
   look-through (splitting an ETF's value across its underlying sectors) is
   tried first via yfinance for every ETF — no key needed for that. Alpha
   Vantage is used only as a fallback, for the ETFs where yfinance doesn't
   have sector data. Adding a key improves coverage without using up your
   Alpha Vantage quota on ETFs yfinance can already handle.
   - Sign up free at https://www.alphavantage.co/support/#api-key (no credit card)
   - **Easiest: save it as a file, once.** Create a plain-text file named
     `alphavantage_key.txt` in this folder, containing only the key — nothing
     else. The skill reads it automatically every time you run it; you never
     have to re-enter it.

     **Mac users — a common gotcha:** TextEdit saves files as Rich Text (.rtf)
     by default, even if you name the file `something.txt`. An RTF file will
     not work — the skill will detect it and warn you. To avoid this:
     - In TextEdit: **Format menu → Make Plain Text** (or Shift+Cmd+T) before
       saving, *then* save as `alphavantage_key.txt`.
     - Or use a plain-text editor like VS Code, or `nano`/`vim` in Terminal.
     - Or from Terminal, the safest one-liner:
       ```
       echo "your_key_here" > alphavantage_key.txt
       ```
   - **Alternative:** set it as an environment variable instead:
     ```
     export ALPHAVANTAGE_API_KEY=your_key_here
     ```
     This only lasts for that Terminal session unless you add it to your shell
     profile (`~/.zshrc` on modern Macs). The environment variable takes
     priority over the key file if you set both.
   - Without this key, the skill still works — ETFs just show up as
     "Unclassified" in the sector chart instead of being broken down.
   - **Keep this key private.** If you ever publish this folder (e.g. to
     GitHub), do not include your key file — add `alphavantage_key.txt` to a
     `.gitignore` file first.

5. **Install the skill.** Place the `.claude` folder from this bundle into the
   folder you'll work in. It should look like:
   ```
   My Portfolio/
   └── .claude/skills/investment-portfolio-snapshot/
       ├── SKILL.md
       └── scripts/
   ```

---

## How to use it (each time)

1. **Export your holdings** from each brokerage as **CSV** and put them all in
   your working folder (e.g. `My Portfolio/`). Any brokerage works — Schwab,
   Fidelity, Vanguard, Merrill, Robinhood, etc. Most brokerages have an "Export"
   or "Download" button on the positions/holdings page.

   The skill looks for two things in each file: a **ticker/symbol** column and a
   **market value** column. It handles the extra title, disclaimer, and total
   rows that brokerages add.

2. **Open Claude Code**, point it at your folder, and run:
   ```
   /investment-portfolio-snapshot
   ```

3. The skill will:
   - Read every CSV and combine your holdings (summing anything you hold in more
     than one account)
   - Look up each holding's asset type and sector
   - Write a portfolio assessment
   - Produce **`portfolio_snapshot.html`** in your folder

4. Open `portfolio_snapshot.html` in any browser. Done.

---

## Notes & limitations

- **Accuracy is best-effort.** Classifications come from public data (Yahoo
  Finance). Individual stocks and major ETFs classify well; some bonds, cash
  funds, or obscure/non-US tickers may land in **"Others."**
- **You can correct classifications.** After the first run, a file called
  `classification_cache.csv` appears in your folder. Edit the `asset_type` or
  `sector` for any symbol, save, and re-run — your corrections stick and are
  reused next time.
- **Sector chart covers individual stocks only.** ETFs, bonds, and cash don't
  have a single sector, so the sector chart (and its coverage %) reflect just the
  individual-stock portion of your portfolio.
- **Internet is required** the first time a new symbol is looked up (for the
  Yahoo Finance lookup). Cached symbols don't need the network again.
- Your data stays on your machine except for the ticker symbols sent to Yahoo
  Finance for classification. Market values and account details are never sent.

---

## Files produced

| File | What it is |
|------|-----------|
| `holdings_combined.csv` | Your holdings, aggregated by symbol |
| `holdings_enriched.csv` | The above plus asset type & sector |
| `classification_cache.csv` | Editable lookup cache (correct classifications here) |
| `portfolio_snapshot.html` | **Your report** — open in any browser |
