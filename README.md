# Investment Portfolio Snapshot

Generate a professional, wealth-advisor-style HTML report of your current
investment portfolio from your brokerage export files — from any brokerage.

The report includes:
- A written assessment of your portfolio (allocation, risk posture, what stands out)
- A **By Asset Type** chart (stocks, bonds, cash, commodities, crypto, others)
- A **By Sector** chart (for your individual stock holdings, plus ETF look-through)

> This report is an informational guide only. It is **not financial advice.**

---

## What you need (one-time setup)

This skill works on **Mac, Windows, and Linux** — the instructions below note
where a step differs by platform.

1. **Claude Code** (in the Claude desktop app, the `</>` Code tab, or the CLI).
   Claude Code runs natively on Windows — no WSL required, though it's
   supported if you prefer it. Install from claude.com and open a terminal
   (PowerShell, Command Prompt, or the desktop app's Code tab) to get started.

2. **Python 3.**
   - **Mac**: usually already installed. Check with `python3 --version` in Terminal.
   - **Windows**: download from https://python.org/downloads — during install,
     **check the box "Add python.exe to PATH"** (easy to miss, and the most
     common cause of "python is not recognized" errors afterward). Verify with
     `python --version` in PowerShell or Command Prompt.
   - **Command name differs by platform:** Mac/Linux use `python3` and `pip3`;
     Windows typically uses `python` and `pip` (no "3"). The commands in this
     README use `python3`/`pip3` — on Windows, drop the "3" if that's what
     your system recognizes. Run `python3 --version` and `python --version`
     to see which one works on your machine.

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

     **Windows users:** plain **Notepad** saves `.txt` files correctly by
     default, so it's the safe choice here — just type the key, nothing else,
     and save as `alphavantage_key.txt`. Avoid WordPad or Microsoft Word for
     this file, since both can add hidden formatting the same way TextEdit
     does on Mac. From PowerShell, the equivalent one-liner is:
     ```
     "your_key_here" | Out-File -Encoding utf8 alphavantage_key.txt -NoNewline
     ```
   - **Alternative:** set it as an environment variable instead:
     - Mac/Linux (Terminal):
       ```
       export ALPHAVANTAGE_API_KEY=your_key_here
       ```
       Lasts for that Terminal session only, unless added to your shell
       profile (`~/.zshrc` on modern Macs).
     - Windows (PowerShell):
       ```
       $env:ALPHAVANTAGE_API_KEY="your_key_here"
       ```
     - Windows (Command Prompt):
       ```
       set ALPHAVANTAGE_API_KEY=your_key_here
       ```
       Both Windows versions last for that terminal session only, unless set
       permanently via System Properties → Environment Variables.

     The environment variable takes priority over the key file if you set both,
     on every platform.
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

## How to prepare your CSV files — please read before uploading

This skill only needs **two things per holding: the ticker symbol, and its
current market value.** Nothing else is required, and some things should
not be included at all.

### ✅ What to include
- **Symbol / Ticker** column (e.g. `AAPL`, `VTI`, `BTC-USD`)
- **Current value** column — any of these header names are recognized
  automatically: *Current Value*, *Current Market Value*, *Market Value*,
  *Mkt Value*, or just *Value*

That's it. Most brokerage exports have many more columns (description,
quantity, price, cost basis, gain/loss, % of account) — you don't need to
remove those; the skill simply ignores them.

### ❌ What to remove before uploading
- **Account numbers** and any other personal identifiers (name, address,
  account nickname if it contains personal info). The skill does not need
  these to generate your report, and having them in the file is an
  unnecessary exposure of personal information.
- If you're not sure whether something counts as personal info, it's safer
  to remove the column than to leave it in.

### ⚠️ What the skill ignores automatically (you don't have to remove it, but you can)
Most brokerage exports mix your **current holdings** with **transaction
history** in the same file (trades, dividends received, dividends
reinvested, debits, credits, transfers, fees). Since this report shows a
**current snapshot**, not an activity log, the skill automatically detects
and skips rows that look like transactions rather than positions. You'll
see a message telling you how many rows were skipped this way. If you'd
rather remove them yourself first, that's fine too — the result is the same.

### What happens if you don't clean up first
The skill **scans every file before processing** and tells you, by filename,
about anything worth knowing:
- If it detects what looks like an **account number**, it will tell you which
  file and ask you to remove that column before your next run (it does not
  use the number, but flags it so you can keep it out of the file entirely).
- If it detects and skips **transaction rows**, it tells you how many.
- If a file is **empty**, it tells you by filename and skips it.
- If a file **isn't a valid CSV** or its columns can't be recognized, it tells
  you by filename, explains what it was looking for, and skips that file
  rather than guessing.
- If the folder has **no CSV files at all** (or only non-CSV files like
  `.xlsx`), it tells you clearly what it needs.

None of these stop the whole run — files with problems are simply excluded
from the report, and everything else still processes normally.

---

## How to use it (each time)

1. **Export your holdings** from each brokerage as **CSV** and put them all in
   your working folder (e.g. `My Portfolio/`). Any brokerage works — Schwab,
   Fidelity, Vanguard, Merrill, Robinhood, etc. Most brokerages have an "Export"
   or "Download" button on the positions/holdings page.

   **Your `My Portfolio/` folder must sit inside the same folder as the skill**
   — i.e. inside the `Investment Portfolio Snapshot` folder inside `.claude/skills/`.
   The skill only reads CSV files from the folder Claude Code is pointed at
   (the working directory), so your exports need to be there directly, not in
   a separate, disconnected folder elsewhere on your computer. The layout should
   look like:
   ```
   Investment Portfolio Snapshot/        <- point Claude Code at this folder
   ├── .claude/skills/investment-portfolio-snapshot/
   ├── My Portfolio/                     <- your brokerage CSV exports go here
   │   ├── schwab_export.csv
   │   ├── fidelity_export.csv
   │   └── ...
   ├── alphavantage_key.txt              <- optional, see above
   └── README.md
   ```
   (Your CSVs can also sit directly in the top-level folder instead of a `My
   Portfolio/` subfolder if you prefer — either works, as long as they're
   somewhere Claude Code can see from the folder it's pointed at.)

   **This skill works best with USD-denominated holdings.** It assumes every
   dollar figure in your files is in US dollars and does not detect or convert
   other currencies — see "Known Limitations" below for what that means if
   your brokerage reports values in a different currency.

2. **Open Claude Code**, point it at your folder, and run:
   ```
   /investment-portfolio-snapshot
   ```

3. The skill will:
   - Scan and read every CSV, flagging anything worth your attention (see above)
   - Combine your holdings, summing anything you hold at more than one
     brokerage into a single accurate total per symbol
   - Look up each holding's asset type and sector
   - Write a portfolio assessment
   - Produce **`portfolio_snapshot.html`** in your folder

4. Open `portfolio_snapshot.html` in any browser. Done.

---

## Known Limitations

- **Classification accuracy is best-effort, not guaranteed.** Asset type and
  sector come from public data (Yahoo Finance, with Alpha Vantage as a
  fallback for ETF sectors). Individual stocks and major, well-known ETFs
  classify well. **Bonds, money-market/cash funds, and obscure or non-US
  tickers may be misclassified or land in "Others"/"Unclassified."** Always
  glance over the report's charts against what you know you actually hold.
- **You can correct misclassifications.** After the first run, a file called
  `classification_cache.csv` appears in your folder. Edit the `asset_type` or
  `sector` for any symbol, save, and re-run — your corrections persist and
  are reused on every future run.
- **Alpha Vantage's free tier has a daily request limit.** If you have many
  ETFs without yfinance sector data, you may hit that limit in one run. If
  so, some ETFs will show as "Unclassified" for that run — re-running later
  (once the daily limit resets) or adding sector data manually to the cache
  both work as a fix.
- **Sector chart coverage is partial by design.** ETFs, bonds, and cash don't
  have one single sector, so the sector chart (and its stated coverage %)
  reflect only the portion of your portfolio the skill can meaningfully
  attribute to sectors — individual stocks, plus ETFs where look-through data
  was available.
- **USD only — no currency conversion.** The skill assumes every value in
  every file is in US dollars and does not detect, convert, or label other
  currencies. If your export contains non-USD values (e.g. EUR, GBP), the
  numbers will be parsed as if they were dollars, which will make totals
  wrong and mislabel the currency shown in the report. Non-US number
  formatting (e.g. `10.000,00` using a comma as the decimal separator) can
  also be misread. If you're outside the US, review the totals carefully
  before trusting them.
- **Internet is required** the first time a new symbol is looked up. Cached
  symbols (via `classification_cache.csv`) don't need the network again.
- **What actually leaves your machine:** ticker symbols are sent to Yahoo
  Finance and, as a fallback, Alpha Vantage, purely to classify each holding
  — dollar amounts and account details are never sent to either of those
  services. Separately, because this skill runs through Claude, the contents
  of your files — including dollar values — are read by Claude in order to
  write the portfolio assessment and orchestrate the steps, the same way any
  file you share with Claude in a conversation is processed. If that's a
  concern, review Anthropic's data usage settings for your account.

---

## Files produced

| File | What it is |
|------|-----------|
| `holdings_combined.csv` | Your holdings, aggregated by symbol |
| `holdings_enriched.csv` | The above plus asset type & sector |
| `classification_cache.csv` | Editable lookup cache (correct classifications here) |
| `portfolio_snapshot.html` | **Your report** — open in any browser |
