#!/usr/bin/env python3
"""
enrich_holdings.py
------------------
STEP 3 of the investment-portfolio-snapshot skill.

Reads holdings_combined.csv and appends two columns using yfinance:
  - asset_type : Stocks / Bonds / Cash / Commodities / Crypto / Others
  - sector     : GICS sector (individual stocks only; blank for funds/bonds/cash)

Writes holdings_enriched.csv.

Caching: results are cached in classification_cache.csv so re-runs don't
re-hit the network for symbols already looked up. Users may hand-edit that
cache to correct any misclassification.

Requires:  pip install yfinance
"""

import csv
import os
import sys
import time

WORKDIR = os.getcwd()
CACHE_NAME = "classification_cache.csv"

# Cash-like symbols / keywords that yfinance won't identify well
CASH_HINTS = ("cash", "money", "sweep", "fdic", "mmf", "settlement", "spaxx",
              "fdrxx", "snsxx", "snvxx", "vmfxx", "swvxx", "tmcxx", "sgov")
# Common crypto tickers people paste in
CRYPTO_HINTS = ("btc", "eth", "bitcoin", "ethereum", "sol", "ada", "doge",
                "usdc", "usdt", "-usd")


def load_cache():
    path = os.path.join(WORKDIR, CACHE_NAME)
    cache = {}
    if os.path.exists(path):
        with open(path, newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                sym = (row.get("symbol") or "").strip().upper()
                if sym:
                    cache[sym] = {
                        "asset_type": (row.get("asset_type") or "").strip(),
                        "sector": (row.get("sector") or "").strip(),
                        "sector_weights": (row.get("sector_weights") or "").strip(),
                    }
    return cache


def save_cache(cache):
    path = os.path.join(WORKDIR, CACHE_NAME)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["symbol", "asset_type", "sector", "sector_weights"])
        for sym in sorted(cache.keys()):
            r = cache[sym]
            w.writerow([sym, r["asset_type"], r["sector"], r.get("sector_weights", "")])


def heuristic_classify(symbol):
    """Classify without network for obvious cash/crypto cases. Returns dict or None."""
    low = symbol.lower()
    if any(h in low for h in CRYPTO_HINTS):
        return {"asset_type": "Crypto", "sector": ""}
    if any(h in low for h in CASH_HINTS):
        return {"asset_type": "Cash", "sector": ""}
    return None


def classify_via_yfinance(symbol):
    """
    Look up a symbol on yfinance and map to our asset_type + sector.
    Returns dict {asset_type, sector}. Falls back to 'Others' on any failure.
    """
    try:
        import yfinance as yf
    except ImportError:
        print("ERROR: yfinance is not installed. Run:  pip install yfinance")
        sys.exit(1)

    try:
        info = yf.Ticker(symbol).info
    except Exception:
        return {"asset_type": "Others", "sector": ""}

    if not info or not isinstance(info, dict):
        return {"asset_type": "Others", "sector": ""}

    qt = (info.get("quoteType") or "").upper()
    sector = info.get("sector") or ""

    if qt == "EQUITY":
        return {"asset_type": "Stocks", "sector": sector}
    if qt == "ETF":
        # Use fund category to separate bond ETFs / commodity ETFs from equity ETFs
        cat = (info.get("category") or "").lower()
        name = (info.get("longName") or info.get("shortName") or "").lower()
        blob = cat + " " + name
        if any(k in blob for k in ("bond", "treasury", "fixed income", "muni", "aggregate")):
            return {"asset_type": "Bonds", "sector": ""}
        if any(k in blob for k in ("gold", "silver", "commodity", "commodities", "oil", "metal")):
            return {"asset_type": "Commodities", "sector": ""}
        if any(k in blob for k in ("money market", "ultra short", "treasury bill")):
            return {"asset_type": "Cash", "sector": ""}
        # equity ETF -> Stocks bucket; try to pull sector weightings for look-through.
        # yfinance first (no extra API key, no rate limit) - only fall through to
        # Alpha Vantage if yfinance doesn't have the data.
        weights = _etf_sector_weights_yfinance(symbol, info)
        source = "yfinance"
        if not weights:
            weights = _etf_sector_weights_alphavantage(symbol)
            source = "alphavantage" if weights else "none"
        return {"asset_type": "Stocks", "sector": "", "sector_weights": weights,
                "sector_weights_source": source}
    if qt == "MUTUALFUND":
        cat = (info.get("category") or "").lower()
        if any(k in cat for k in ("bond", "fixed income", "muni")):
            return {"asset_type": "Bonds", "sector": ""}
        if any(k in cat for k in ("money market",)):
            return {"asset_type": "Cash", "sector": ""}
        return {"asset_type": "Stocks", "sector": ""}
    if qt == "CRYPTOCURRENCY":
        return {"asset_type": "Crypto", "sector": ""}
    if qt in ("CURRENCY", "MONEYMARKET"):
        return {"asset_type": "Cash", "sector": ""}
    if qt in ("FUTURE", "COMMODITY"):
        return {"asset_type": "Commodities", "sector": ""}

    return {"asset_type": "Others", "sector": ""}



def _get_alphavantage_key():
    """
    Look up the Alpha Vantage API key. Checked in order:
      1. ALPHAVANTAGE_API_KEY environment variable
      2. A key file in the working directory - first of:
         alphavantage_key.txt, .alphavantage_key, av_key.txt
    Returns "" if not found anywhere.
    """
    env_key = os.environ.get("ALPHAVANTAGE_API_KEY", "").strip()
    if env_key:
        return env_key

    candidates = ["alphavantage_key.txt", ".alphavantage_key", "av_key.txt"]
    for name in candidates:
        path = os.path.join(WORKDIR, name)
        if not os.path.exists(path):
            continue
        try:
            with open(path, encoding="utf-8-sig") as f:
                key = f.read().strip()
            # Guard against accidentally reading a rich-text file: RTF starts
            # with a literal "{\rtf" header - if we see that, the file wasn't
            # saved as plain text, so treat it as unusable rather than sending
            # garbage to the API.
            if key.startswith("{\\rtf") or key.startswith("{\rtf"):
                print(f"  [!] {name} looks like Rich Text (.rtf), not plain text.")
                print(f"      Re-save it as plain text (see README) and try again.")
                return ""
            if key:
                return key
        except Exception:
            continue
    return ""


def _etf_sector_weights_yfinance(symbol, info=None):
    """
    Try to get ETF sector weightings directly from yfinance
    (funds_data.sector_weightings). This field is undocumented and not always
    present, but when it is, using it avoids an extra Alpha Vantage call.
    Returns a JSON string of {sector: weight}, or "" if unavailable.
    """
    import json
    try:
        import yfinance as yf
        t = yf.Ticker(symbol)
        fd = getattr(t, "funds_data", None)
        if fd is None:
            return ""
        sw = getattr(fd, "sector_weightings", None)
        if not sw or not isinstance(sw, dict):
            return ""
        norm = {}
        for k, v in sw.items():
            try:
                w = float(v)
            except (TypeError, ValueError):
                continue
            if w <= 0:
                continue
            label = _pretty_sector(k)
            norm[label] = norm.get(label, 0.0) + w
        if not norm:
            return ""
        return json.dumps(norm)
    except Exception:
        return ""


def _etf_sector_weights_alphavantage(symbol):
    """
    Fallback: fetch ETF sector weightings from Alpha Vantage's ETF_PROFILE
    endpoint (free tier). Used only when yfinance does not have the data,
    to conserve Alpha Vantage's daily request limit.
    Returns a JSON string of {sector: weight}, or "" if unavailable.
    """
    import json

    api_key = _get_alphavantage_key()
    if not api_key:
        return ""

    import urllib.request
    import urllib.parse

    try:
        params = urllib.parse.urlencode({
            "function": "ETF_PROFILE",
            "symbol": symbol,
            "apikey": api_key,
        })
        url = f"https://www.alphavantage.co/query?{params}"
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return ""

    if not isinstance(data, dict):
        return ""
    sectors = data.get("sectors")
    if not sectors or not isinstance(sectors, list):
        return ""

    norm = {}
    for row in sectors:
        try:
            label = _pretty_sector(row.get("sector", ""))
            w = float(row.get("weight", 0))
        except (TypeError, ValueError):
            continue
        if w <= 0 or not label:
            continue
        norm[label] = norm.get(label, 0.0) + w

    if not norm:
        return ""
    return json.dumps(norm)


def _pretty_sector(key):
    """
    Normalize sector labels from either Alpha Vantage (ALL CAPS, e.g.
    'INFORMATION TECHNOLOGY') or yfinance (snake_case) into one consistent
    display name, matching the labels used for individual-stock sectors.
    """
    m = {
        "real estate": "Real Estate", "realestate": "Real Estate",
        "consumer cyclical": "Consumer Cyclical", "consumer discretionary": "Consumer Cyclical",
        "consumer defensive": "Consumer Defensive", "consumer staples": "Consumer Defensive",
        "basic materials": "Basic Materials", "materials": "Basic Materials",
        "communication services": "Communication Services",
        "financial services": "Financial Services", "financials": "Financial Services",
        "healthcare": "Healthcare", "health care": "Healthcare",
        "industrials": "Industrials",
        "information technology": "Technology", "technology": "Technology",
        "utilities": "Utilities", "energy": "Energy",
    }
    k = str(key).strip().lower().replace("_", " ")
    if k in m:
        return m[k]
    return str(key).replace("_", " ").title()


def main():
    in_path = os.path.join(WORKDIR, "holdings_combined.csv")
    if not os.path.exists(in_path):
        print("ERROR: holdings_combined.csv not found. Run extract_holdings.py first.")
        sys.exit(1)

    holdings = []
    with open(in_path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            sym = (row.get("symbol") or "").strip().upper()
            if sym:
                holdings.append((sym, row.get("market_value") or "0"))

    cache = load_cache()
    use_mock = os.environ.get("SNAPSHOT_MOCK") == "1"

    print(f"Classifying {len(holdings)} holdings ...\n")
    results = []
    looked_up = 0
    for sym, mv in holdings:
        if sym in cache:
            cls = cache[sym]
        else:
            cls = heuristic_classify(sym)
            if cls is None:
                if use_mock:
                    cls = _mock_classify(sym)
                else:
                    cls = classify_via_yfinance(sym)
                    looked_up += 1
                    time.sleep(0.3)  # be polite to Yahoo
            src = cls.pop("sector_weights_source", None)
            if src == "yfinance":
                print(f"      (ETF sector data from yfinance)")
            elif src == "alphavantage":
                print(f"      (ETF sector data from Alpha Vantage — yfinance had none)")
            elif src == "none":
                print(f"      (no ETF sector data available from either source)")
            if "sector_weights" not in cls:
                cls["sector_weights"] = ""
            cache[sym] = cls
        results.append({
            "symbol": sym,
            "market_value": mv,
            "asset_type": cls["asset_type"],
            "sector": cls.get("sector", ""),
            "sector_weights": cls.get("sector_weights", ""),
        })
        print(f"  {sym:8}  {cls['asset_type']:12} {cls['sector']}")

    save_cache(cache)

    out_path = os.path.join(WORKDIR, "holdings_enriched.csv")
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["symbol", "market_value", "asset_type", "sector", "sector_weights"])
        for r in results:
            w.writerow([r["symbol"], r["market_value"], r["asset_type"], r["sector"], r.get("sector_weights", "")])

    print(f"\n  Looked up {looked_up} new symbol(s) via yfinance; rest from cache.")
    print(f"  Wrote: {out_path}")
    print(f"  Cache: {os.path.join(WORKDIR, CACHE_NAME)} (edit to correct any classification)")


# ---- Mock classifier: only used when SNAPSHOT_MOCK=1, for offline testing ----
_MOCK = {
    "AAPL": ("Stocks", "Technology"), "MSFT": ("Stocks", "Technology"),
    "GOOGL": ("Stocks", "Communication Services"), "AMZN": ("Stocks", "Consumer Cyclical"),
    "META": ("Stocks", "Communication Services"), "NVDA": ("Stocks", "Technology"),
    "NFLX": ("Stocks", "Communication Services"), "COST": ("Stocks", "Consumer Defensive"),
    "NDAQ": ("Stocks", "Financial Services"),
    "VTI": ("Stocks", ""), "VOO": ("Stocks", ""), "SPY": ("Stocks", ""),
    "VB": ("Stocks", ""), "VBR": ("Stocks", ""), "VO": ("Stocks", ""),
    "VTV": ("Stocks", ""), "VYM": ("Stocks", ""), "VXUS": ("Stocks", ""),
    "VSS": ("Stocks", ""), "VT": ("Stocks", ""), "EWJV": ("Stocks", ""),
    "AIQ": ("Stocks", ""), "DTCR": ("Stocks", ""), "IGV": ("Stocks", ""),
    "BND": ("Bonds", ""), "VCIT": ("Bonds", ""), "VCLT": ("Bonds", ""),
    "VTEB": ("Bonds", ""), "SGOV": ("Cash", ""),
    "SNSXX": ("Cash", ""), "TMCXX": ("Cash", ""),
    "BITCOIN": ("Crypto", ""), "BTC-USD": ("Crypto", ""),
}
# Mock ETF sector weights (only a few; others intentionally blank to test "unclassified")
import json as _json
_MOCK_WEIGHTS = {
    "VTI": _json.dumps({"Technology": 0.30, "Financial Services": 0.13, "Healthcare": 0.12,
                        "Consumer Cyclical": 0.11, "Industrials": 0.09, "Communication Services": 0.08,
                        "Consumer Defensive": 0.06, "Energy": 0.04, "Real Estate": 0.03,
                        "Utilities": 0.02, "Basic Materials": 0.02}),
    "SPY": _json.dumps({"Technology": 0.32, "Financial Services": 0.13, "Healthcare": 0.11,
                        "Consumer Cyclical": 0.10, "Communication Services": 0.09, "Industrials": 0.08}),
    "VOO": _json.dumps({"Technology": 0.31, "Financial Services": 0.13, "Healthcare": 0.11}),
}
def _mock_classify(sym):
    at, sec = _MOCK.get(sym, ("Others", ""))
    weights = _MOCK_WEIGHTS.get(sym, "") if at == "Stocks" and not sec else ""
    return {"asset_type": at, "sector": sec, "sector_weights": weights}


if __name__ == "__main__":
    main()
