#!/usr/bin/env python3
"""
build_report.py
---------------
STEP 4 of the investment-portfolio-snapshot skill.

Reads holdings_enriched.csv and produces a professional, self-contained HTML
report:
  - Title
  - AI-written portfolio description (passed in via --description-file, or a
    deterministic fallback is used if none is provided)
  - Two charts: By Asset Type, By Sector (individual stocks only + ETF look-through)

Charts are rendered with matplotlib and embedded directly in the HTML (base64),
so the output is a single file with no external dependencies - open it in any
browser, no server, no other tools needed.

Usage:
  python3 build_report.py [--description-file path] [--name "Portfolio Name"]
"""

import argparse
import csv
import os
import sys
import base64
from datetime import date

WORKDIR = os.getcwd()

# Modern palette - contemporary, vivid
PALETTE = ["#4F46E5", "#059669", "#F59E0B", "#EF4444", "#8B5CF6",
           "#06B6D4", "#EC4899", "#14B8A6", "#F97316", "#6366F1",
           "#0EA5E9", "#84CC16"]

INK = "#0F172A"
MUTED = "#64748B"
GRID = "#EEF2F7"

# Width the report content is capped at when viewed on screen (px).
# Chart figures are sized in inches at a matching aspect so they don't
# get stretched wide by CSS - see make_donut / make_bars below.
CONTENT_WIDTH_PX = 720


def load_holdings():
    path = os.path.join(WORKDIR, "holdings_enriched.csv")
    if not os.path.exists(path):
        print("ERROR: holdings_enriched.csv not found. Run enrich_holdings.py first.")
        sys.exit(1)
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            try:
                mv = float(str(r.get("market_value", "0")).replace("$", "").replace(",", ""))
            except ValueError:
                mv = 0.0
            rows.append({
                "symbol": (r.get("symbol") or "").strip(),
                "market_value": mv,
                "asset_type": (r.get("asset_type") or "Others").strip() or "Others",
                "sector": (r.get("sector") or "").strip(),
                "sector_weights": (r.get("sector_weights") or "").strip(),
            })
    return rows


def aggregate(rows, key):
    out = {}
    for r in rows:
        k = r[key] or "Unknown"
        out[k] = out.get(k, 0.0) + r["market_value"]
    return dict(sorted(out.items(), key=lambda x: -x[1]))


def fmt_money_exact(v):
    return "${:,.2f}".format(v)


def fmt_money(v):
    if v >= 1e6:
        return f"${v/1e6:.2f}M"
    if v >= 1e3:
        return f"${v/1e3:.1f}K"
    return f"${v:,.0f}"


def make_donut(data, filename):
    """
    Donut chart sized to roughly match CONTENT_WIDTH_PX so it renders at a
    sensible, non-stretched size in the browser regardless of container CSS.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    labels = list(data.keys())
    values = list(data.values())
    total = sum(values) or 1
    colors = PALETTE[:len(labels)]

    # ~4.6in wide at 150 dpi -> 690px native width, close to CONTENT_WIDTH_PX
    fig, ax = plt.subplots(figsize=(4.6, 2.9), dpi=150)
    wedges, _ = ax.pie(
        values, colors=colors, startangle=90, counterclock=False,
        wedgeprops=dict(width=0.32, edgecolor="white", linewidth=2),
    )
    ax.set_aspect("equal")

    ax.text(0, 0.10, fmt_money(total), ha="center", va="center",
            fontsize=15, fontweight="bold", color=INK)
    ax.text(0, -0.14, "TOTAL", ha="center", va="center",
            fontsize=7.5, color=MUTED, fontweight="bold")

    legend_labels = [
        f"{l}    {fmt_money(v)}    {v/total*100:.1f}%"
        for l, v in zip(labels, values)
    ]
    ax.legend(
        wedges, legend_labels, loc="center left", bbox_to_anchor=(1.02, 0.5),
        frameon=False, fontsize=9, labelcolor=INK, handlelength=0.9,
        handleheight=0.9, borderpad=0.5, labelspacing=0.75,
    )

    plt.tight_layout()
    out = os.path.join(WORKDIR, filename)
    fig.savefig(out, bbox_inches="tight", transparent=True)
    plt.close(fig)
    return out


def make_bars(data, filename):
    """
    Horizontal bar chart, same target width as the donut so both charts feel
    consistently sized in the report.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    labels = list(data.keys())
    values = list(data.values())
    total = sum(values) or 1
    colors = PALETTE[:len(labels)]

    h = max(1.7, 0.34 * len(labels) + 0.7)
    fig, ax = plt.subplots(figsize=(4.6, h), dpi=150)
    y = np.arange(len(labels))[::-1]
    ax.barh(y, values, color=colors, height=0.62, zorder=3)

    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=9.5, color=INK, fontweight="bold")
    maxv = max(values) if values else 1
    for yi, v in zip(y, values):
        ax.text(v + maxv * 0.02, yi, f"{fmt_money(v)}  \u00b7  {v/total*100:.1f}%",
                va="center", ha="left", fontsize=8.5, color=MUTED, fontweight="bold")
    ax.set_xlim(0, maxv * 1.32)
    for spine in ["top", "right", "bottom", "left"]:
        ax.spines[spine].set_visible(False)
    ax.set_xticks([])
    ax.tick_params(length=0)
    ax.xaxis.grid(True, color=GRID, zorder=0)

    plt.tight_layout()
    out = os.path.join(WORKDIR, filename)
    fig.savefig(out, bbox_inches="tight", transparent=True)
    plt.close(fig)
    return out


def img_b64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


def fallback_description(rows):
    """Deterministic description if no AI text is supplied."""
    total = sum(r["market_value"] for r in rows) or 1
    by_type = aggregate(rows, "asset_type")
    def pct(name):
        return by_type.get(name, 0.0) / total * 100
    equity = pct("Stocks")
    bonds = pct("Bonds")
    cash = pct("Cash")
    risk = ("aggressive" if equity >= 75 else
            "moderately aggressive" if equity >= 60 else
            "balanced" if equity >= 40 else "conservative")
    return (
        f"This portfolio holds approximately {equity:.0f}% in equities, "
        f"{bonds:.0f}% in fixed income, and {cash:.0f}% in cash or equivalents, "
        f"reflecting a {risk} risk posture. The allocation shown is a point-in-time "
        f"snapshot aggregated across the uploaded accounts."
    )


def build_html(rows, description, portfolio_name, chart_type_path, chart_sector_path,
               sector_coverage_pct, unclassified_etfs=None):
    total = sum(r["market_value"] for r in rows)
    today = date.today().strftime("%B %d, %Y")
    type_b64 = img_b64(chart_type_path)
    has_sector = chart_sector_path is not None
    sector_b64 = img_b64(chart_sector_path) if has_sector else ""

    unclassified_etfs = unclassified_etfs or []
    note = f"Stocks &amp; ETF look-through &mdash; covers {sector_coverage_pct:.0f}% of total portfolio value"
    if unclassified_etfs:
        listed = ", ".join(unclassified_etfs)
        note += f". No reliable sector data for: {listed} (shown as \u201cUnclassified\u201d)"
    sector_block = ""
    if has_sector:
        sector_block = f"""
      <div class="chart-card">
        <div class="chart-title">By Sector</div>
        <div class="chart-note">{note}</div>
        <img class="chart-img" src="data:image/png;base64,{sector_b64}" />
      </div>"""
    else:
        sector_block = """
      <div class="chart-card">
        <div class="chart-title">By Sector</div>
        <div class="chart-note">No equity holdings with sector data were found in this portfolio.</div>
      </div>"""

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{portfolio_name} — Portfolio Snapshot</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  html, body {{ background: #F1F5F9; }}
  body {{ font-family: -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif;
          color: {INK}; line-height: 1.5; padding: 32px 16px; }}

  /* This is the actual on-screen width cap - @page/print rules alone do
     nothing when the file is just opened in a browser tab, so the real
     constraint lives here. */
  .sheet {{
    max-width: {CONTENT_WIDTH_PX}px;
    margin: 0 auto;
    background: #FFFFFF;
    border-radius: 16px;
    box-shadow: 0 1px 3px rgba(15,23,42,0.06), 0 8px 24px rgba(15,23,42,0.06);
    padding: 36px 40px 30px;
  }}

  .header {{ display: flex; justify-content: space-between; align-items: flex-end;
             border-bottom: 3px solid {INK}; padding-bottom: 16px; margin-bottom: 4px; }}
  .eyebrow {{ font-size: 9.5px; letter-spacing: 0.2em; font-weight: 700;
             text-transform: uppercase; color: #4F46E5; margin-bottom: 9px; }}
  h1 {{ font-size: 24px; font-weight: 800; letter-spacing: -0.02em; line-height: 1.15; }}
  .header-right {{ text-align: right; flex-shrink: 0; padding-left: 16px; }}
  .kpi {{ display: inline-block; margin-left: 22px; }}
  .kpi .kv {{ font-size: 17px; font-weight: 800; color: {INK}; letter-spacing: -0.01em; white-space: nowrap; }}
  .kpi .kl {{ font-size: 9px; letter-spacing: 0.1em; text-transform: uppercase;
              color: {MUTED}; font-weight: 600; margin-top: 2px; }}
  .prepared {{ font-size: 10.5px; color: {MUTED}; margin: 10px 0 2px; }}
  .section-label {{ font-size: 10px; font-weight: 700; letter-spacing: 0.15em;
                    text-transform: uppercase; color: #4F46E5; margin: 26px 0 12px; }}
  .assessment {{ font-family: Georgia, 'Times New Roman', serif;
                 font-size: 14px; line-height: 1.75; text-align: justify; color: #1E293B; }}
  .assessment p {{ margin-bottom: 11px; }}
  .charts {{ margin-top: 8px; }}
  .chart-card {{ margin-bottom: 18px; background: #FBFCFE;
                 border: 1px solid #E7ECF3; border-radius: 14px;
                 padding: 18px 20px; }}
  .chart-title {{ font-size: 15px; font-weight: 800; letter-spacing: -0.01em; margin-bottom: 3px; }}
  .chart-note {{ font-size: 10.5px; color: {MUTED}; margin-bottom: 6px; font-weight: 500; }}

  /* Real size cap on the chart image itself - this is what actually stops
     the chart from stretching edge to edge, not the figure's inch size. */
  .chart-img {{ display: block; max-width: 460px; width: 100%; height: auto; margin: 0 auto; }}

  .disclaimer {{ font-size: 9.5px; color: {MUTED};
                 background: #F8FAFC; border-radius: 10px;
                 margin-top: 22px; padding: 14px 16px; line-height: 1.55; }}
  .disclaimer b {{ color: #B23B3B; }}

  @media (max-width: 600px) {{
    .sheet {{ padding: 24px 20px; }}
    .header {{ flex-direction: column; align-items: flex-start; gap: 10px; }}
    .header-right {{ padding-left: 0; }}
    .kpi {{ margin-left: 0; margin-right: 22px; }}
  }}

  /* Optional: if the user prints this HTML (browser Print > Save as PDF),
     these rules make that reasonable too - but they are not required for
     normal on-screen viewing. */
  @media print {{
    body {{ background: #fff; padding: 0; }}
    .sheet {{ box-shadow: none; max-width: none; padding: 0.3in; }}
  }}
</style></head>
<body>
<div class="sheet">
  <div class="header">
    <div>
      <div class="eyebrow">Portfolio Snapshot &middot; Wealth Assessment</div>
      <h1>{portfolio_name}</h1>
    </div>
    <div class="header-right">
      <div class="kpi"><div class="kv">{fmt_money_exact(total)}</div><div class="kl">Total Value</div></div>
      <div class="kpi"><div class="kv">{len(rows)}</div><div class="kl">Holdings</div></div>
    </div>
  </div>
  <div class="prepared">Prepared {today}</div>

  <div class="section-label">Advisor Assessment</div>
  <div class="assessment">{description}</div>

  <div class="section-label">Allocation</div>
  <div class="charts">
    <div class="chart-card">
      <div class="chart-title">By Asset Type</div>
      <div class="chart-note">All holdings, by share of total market value</div>
      <img class="chart-img" src="data:image/png;base64,{type_b64}" />
    </div>
    {sector_block}
  </div>

  <div class="disclaimer">
    This report is generated automatically from the account data you provided and is intended
    as an informational guide only. It is <b>not financial advice</b> and should be used as a
    starting point for reflection or discussion, not as an absolute instruction. Classifications
    are best-effort and derived from public data sources, which may be incomplete or inaccurate.
    Verify all figures against your brokerage statements before making any decision.
  </div>
</div>
</body></html>"""


def friendly_import_check():
    try:
        import matplotlib  # noqa
    except ImportError:
        print("ERROR: matplotlib is not installed. Run:  pip install matplotlib")
        raise SystemExit(1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--description-file", default=None)
    ap.add_argument("--name", default="Investment Portfolio")
    args = ap.parse_args()

    friendly_import_check()
    rows = load_holdings()
    total = sum(r["market_value"] for r in rows) or 1

    # Description
    if args.description_file and os.path.exists(args.description_file):
        with open(args.description_file, encoding="utf-8") as f:
            description = f.read().strip()
        if "<p>" not in description:
            paras = [p.strip() for p in description.split("\n\n") if p.strip()]
            description = "".join(f"<p>{p}</p>" for p in paras)
    else:
        description = f"<p>{fallback_description(rows)}</p>"

    # Chart 1: By Asset Type (all holdings)
    by_type = aggregate(rows, "asset_type")
    chart_type = make_donut(by_type, "_chart_asset_type.png")

    # Chart 2: By Sector - individual stocks (direct sector) + ETF look-through
    import json
    sector_totals = {}
    classified_value = 0.0
    unclassified_etfs = []
    unclassified_value = 0.0

    for r in rows:
        at = r["asset_type"]
        mv = r["market_value"]
        if r["sector"]:
            sector_totals[r["sector"]] = sector_totals.get(r["sector"], 0.0) + mv
            classified_value += mv
            continue
        if at == "Stocks":
            weights_raw = r.get("sector_weights", "")
            weights = None
            if weights_raw:
                try:
                    weights = json.loads(weights_raw)
                except (ValueError, TypeError):
                    weights = None
            if weights:
                wsum = sum(weights.values()) or 1.0
                for sec, w in weights.items():
                    sector_totals[sec] = sector_totals.get(sec, 0.0) + mv * (w / wsum)
                classified_value += mv
            else:
                unclassified_etfs.append(r["symbol"])
                unclassified_value += mv

    chart_sector = None
    sector_coverage = 0.0
    if sector_totals or unclassified_value > 0:
        chart_data = dict(sector_totals)
        if unclassified_value > 0:
            chart_data["Unclassified"] = unclassified_value
        chart_data = dict(sorted(chart_data.items(), key=lambda x: -x[1]))
        chart_sector = make_bars(chart_data, "_chart_sector.png")
        sector_coverage = (classified_value + unclassified_value) / total * 100

    html = build_html(rows, description, args.name, chart_type, chart_sector,
                      sector_coverage, unclassified_etfs)

    out_path = os.path.join(WORKDIR, "portfolio_snapshot.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    # cleanup temp chart images (already embedded as base64 in the HTML)
    for tmp in ["_chart_asset_type.png", "_chart_sector.png"]:
        p = os.path.join(WORKDIR, tmp)
        if os.path.exists(p):
            os.remove(p)

    print(f"  Report written: {out_path}")


if __name__ == "__main__":
    main()
