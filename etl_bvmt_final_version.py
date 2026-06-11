

import csv
import os
import math
from datetime import datetime, date
from collections import defaultdict

# ─────────────────────────────────────────────
#  CONFIGURATION
# ─────────────────────────────────────────────

INPUT_DIR  = "data/raw"
OUTPUT_DIR = "data/output"

# ── Company registry ──────────────────────────
# codes: list of (groupe, code) — all variants
# across years (old numeric + new ISIN from 2021)
# ─────────────────────────────────────────────

COMPANIES = {

    "SOTUVER": {
        "label": "SOTUVER",
        "codes": [
            ("11", "656001"),          # 2016–2020
            ("11", "TN0006560015"),    # 2021–2024
        ],
        "shares": 13_084_825,
        "listing_year": 2016,
    },

    "ONE_TECH": {
        "label": "ONE TECH HOLDING",
        "codes": [
            ("11", "753001"),          # 2016–2020
            ("11", "TN0007530017"),    # 2021–2024
        ],
        "shares": 32_000_000,
        "listing_year": 2016,
    },

    "POULINA": {
        "label": "POULINA GP HOLDING",
        "codes": [
            ("11", "570001"),          # 2016–2020
            ("11", "TN0005700018"),    # 2021–2024
        ],
        "shares": 200_000_000,
        "listing_year": 2016,
    },

    "ALKIMIA": {
        "label": "ALKIMIA",
        "codes": [
            ("12", "380070"),          # 2016–2020
            ("12", "TN0003800703"),    # 2021 (groupe 12)
            ("99", "TN0003800703"),    # 2022–2024 (groupe 99)
        ],
        "shares": 4_000_000,
        "listing_year": 2016,
    },

    "CARTHAGE_CEMENT": {
        "label": "CARTHAGE CEMENT",
        "codes": [
            ("51", "740001"),          # 2016–2020 (second marché)
            ("11", "TN0007400013"),    # 2021–2024 (marché principal)
        ],
        "shares": 375_000_000,
        "listing_year": 2016,
    },

    "AIR_LIQUIDE": {
        "label": "AIR LIQUIDE TUNISIE",
        "codes": [
            ("12", "TN0002300358"),    # 2021–2024 (IPO August 2021)
        ],
        "shares": 4_800_000,
        "listing_year": 2021,
    },
}

# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────

def parse_float(s):
    """Parse float, return None on failure."""
    if s is None:
        return None
    s = s.strip().replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None

def parse_int(s):
    if s is None:
        return None
    try:
        return int(s.strip())
    except ValueError:
        return None

def parse_date(s):
    s = s.strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None

def annualised_vol(returns):
    """Annualised volatility from daily returns (252 trading days)."""
    n = len(returns)
    if n < 2:
        return None
    mean = sum(returns) / n
    variance = sum((r - mean) ** 2 for r in returns) / (n - 1)
    return math.sqrt(variance * 252)

def moving_average(prices, window):
    """Return dict {index: MA} for a list of prices."""
    result = {}
    for i in range(len(prices)):
        if i + 1 >= window:
            window_vals = [p for p in prices[i - window + 1: i + 1] if p is not None]
            result[i] = sum(window_vals) / len(window_vals) if window_vals else None
        else:
            result[i] = None
    return result

# ─────────────────────────────────────────────
#  EXTRACT — read all 9 source files
# ─────────────────────────────────────────────

def build_code_index(companies):
    """Build lookup: (groupe, code) → company_key."""
    idx = {}
    for key, cfg in companies.items():
        for (grp, cod) in cfg["codes"]:
            idx[(grp, cod)] = key
    return idx

def extract_all(input_dir, companies):
    """
    Read all histo_cotation_YYYY.csv files.
    Returns dict: company_key → list of raw row dicts (sorted by date).
    """
    code_index = build_code_index(companies)
    data = {k: [] for k in companies}

    for year in range(2016, 2025):
        filepath = os.path.join(input_dir, f"histo_cotation_{year}.csv")
        if not os.path.exists(filepath):
            print(f"  [WARN] Missing file: {filepath}")
            continue

        with open(filepath, encoding="utf-8-sig") as f:
            reader = csv.reader(f, delimiter=";")
            next(reader)  # skip header row

            for row in reader:
                if len(row) < 11:
                    continue

                groupe = row[1].strip()
                code   = row[2].strip()
                key    = code_index.get((groupe, code))
                if key is None:
                    continue

                d = parse_date(row[0])
                if d is None:
                    continue

                ouv  = parse_float(row[4])
                clo  = parse_float(row[5])
                bas  = parse_float(row[6])
                haut = parse_float(row[7])
                qty  = parse_int(row[8])
                txn  = parse_int(row[9])
                cap  = parse_float(row[10].rstrip(";"))

                suspended = (qty is not None and qty == 0)

                data[key].append({
                    "date":      d,
                    "year":      d.year,
                    "ouv":       ouv,
                    "clo":       clo,
                    "bas":       bas,
                    "haut":      haut,
                    "qty":       qty  if qty  is not None else 0,
                    "txn":       txn  if txn  is not None else 0,
                    "cap":       cap  if cap  is not None else 0.0,
                    "suspended": suspended,
                })

    # Sort each company's data by date
    for key in data:
        data[key].sort(key=lambda r: r["date"])

    return data

# ─────────────────────────────────────────────
#  TRANSFORM
# ─────────────────────────────────────────────

def transform(raw_rows):
    """
    Enrich daily rows:
      - daily_return : % price change vs previous active day
      - ma20         : 20-day moving average of close price
      - ma50         : 50-day moving average of close price
    Returns enriched list of row dicts.
    """
    rows = raw_rows[:]

    # ── Daily returns (skip suspended days) ──────────────────────
    prev_close = None
    for r in rows:
        clo = r["clo"]
        if r["suspended"] or clo is None or clo == 0:
            r["daily_return"] = None
        else:
            if prev_close is not None and prev_close != 0:
                r["daily_return"] = (clo - prev_close) / prev_close
            else:
                r["daily_return"] = None
            prev_close = clo

    # ── Moving averages on closing prices ────────────────────────
    closes = [r["clo"] if (r["clo"] and not r["suspended"]) else None for r in rows]

    # Forward-fill None with previous valid close for MA calculation
    filled = []
    last = None
    for c in closes:
        if c is not None:
            last = c
        filled.append(last)

    ma20_map = moving_average(filled, 20)
    ma50_map = moving_average(filled, 50)

    for i, r in enumerate(rows):
        r["ma20"] = round(ma20_map[i], 4) if ma20_map[i] is not None else None
        r["ma50"] = round(ma50_map[i], 4) if ma50_map[i] is not None else None

    return rows

def compute_annual(rows, shares):
    """
    Compute annual market aggregates (price stats + volume + market cap).
    No financial ratio calculations — those are handled separately in Excel.
    Returns list of annual summary dicts.
    """
    by_year = defaultdict(list)
    for r in rows:
        by_year[r["year"]].append(r)

    annual = []
    for year in sorted(by_year.keys()):
        yr_rows = by_year[year]
        active  = [r for r in yr_rows if not r["suspended"] and r["clo"] and r["clo"] > 0]
        returns = [r["daily_return"] for r in yr_rows if r["daily_return"] is not None]

        if not active:
            continue

        closes      = [r["clo"] for r in active]
        first_close = closes[0]
        last_close  = closes[-1]
        ytd_return  = (last_close - first_close) / first_close if first_close else None
        avg_price   = sum(closes) / len(closes)
        high_price  = max(r["haut"] for r in active if r["haut"])
        low_price   = min(r["bas"]  for r in active if r["bas"] and r["bas"] > 0)
        total_vol   = sum(r["qty"] for r in yr_rows)
        total_cap   = sum(r["cap"] for r in yr_rows)
        ann_vol     = annualised_vol(returns)
        n_sessions  = len(yr_rows)
        n_suspended = sum(1 for r in yr_rows if r["suspended"])
        n_active    = n_sessions - n_suspended
        mkt_cap     = last_close * shares

        annual.append({
            "year":           year,
            "first_close":    round(first_close, 3),
            "last_close":     round(last_close, 3),
            "avg_price":      round(avg_price, 3),
            "high_price":     round(high_price, 3),
            "low_price":      round(low_price, 3),
            "ytd_return_pct": round(ytd_return * 100, 2) if ytd_return is not None else None,
            "ann_volatility": round(ann_vol * 100, 2)    if ann_vol   is not None else None,
            "total_volume":   total_vol,
            "total_turnover": round(total_cap, 2),
            "n_sessions":     n_sessions,
            "n_active":       n_active,
            "n_suspended":    n_suspended,
            "market_cap":     round(mkt_cap, 0),
        })

    return annual

# ─────────────────────────────────────────────
#  LOAD — write output CSVs
# ─────────────────────────────────────────────

DAILY_COLS = [
    "date", "year", "ouv", "clo", "bas", "haut",
    "qty", "txn", "cap", "suspended", "daily_return", "ma20", "ma50",
]

ANNUAL_COLS = [
    "year", "first_close", "last_close", "avg_price", "high_price", "low_price",
    "ytd_return_pct", "ann_volatility",
    "total_volume", "total_turnover",
    "n_sessions", "n_active", "n_suspended",
    "market_cap",
]

def write_csv(filepath, rows, cols):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=cols, delimiter=";", extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            out = {}
            for col in cols:
                val = row.get(col)
                if val is None:
                    out[col] = ""
                elif isinstance(val, bool):
                    out[col] = "1" if val else "0"
                elif isinstance(val, float):
                    out[col] = f"{val:.6f}".rstrip("0").rstrip(".")
                else:
                    out[col] = str(val)
            writer.writerow(out)

# ─────────────────────────────────────────────
#  REPORT
# ─────────────────────────────────────────────

def generate_report(all_summaries, output_dir):
    lines = []
    lines.append("=" * 70)
    lines.append("  BVMT ETL PIPELINE — Quality & Validation Report")
    lines.append(f"  Run date : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("=" * 70)

    for key, (daily, annual) in all_summaries.items():
        label = COMPANIES[key]["label"]
        lines.append("")
        lines.append(f"  ▶ {label}")
        lines.append(f"    Daily rows    : {len(daily):,}")
        lines.append(f"    Annual rows   : {len(annual)}")

        years_covered = sorted({r["year"] for r in daily})
        if years_covered:
            lines.append(f"    Years covered : {years_covered[0]}–{years_covered[-1]}")
        else:
            lines.append("    No data found")

        total_susp = sum(1 for r in daily if r.get("suspended"))
        lines.append(f"    Suspended days: {total_susp}")

        lines.append("")
        lines.append(f"    {'Year':>6}  {'Open':>8}  {'Close':>8}  "
                     f"{'High':>8}  {'Low':>8}  {'YTD%':>7}  {'Vol%':>7}  "
                     f"{'MktCap':>14}  {'Sessions':>9}")
        lines.append("    " + "-" * 84)

        for a in annual:
            def fmt(v, d=2):
                return f"{v:.{d}f}" if v is not None else "N/A"
            lines.append(
                f"    {a['year']:>6}  {fmt(a['first_close'],3):>8}  "
                f"{fmt(a['last_close'],3):>8}  {fmt(a['high_price'],3):>8}  "
                f"{fmt(a['low_price'],3):>8}  {fmt(a['ytd_return_pct']):>7}  "
                f"{fmt(a['ann_volatility']):>7}  "
                f"{a['market_cap']:>14,.0f}  "
                f"{a['n_active']:>4}/{a['n_sessions']:>4}"
            )

    lines.append("")
    lines.append("=" * 70)
    lines.append("  ✔ ETL completed successfully.")
    lines.append("=" * 70)

    report_path = os.path.join(output_dir, "ETL_report_all.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("\n".join(lines))
    return report_path

# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"\n{'='*60}")
    print("  BVMT ETL — 6 Companies (2016–2024)")
    print(f"{'='*60}\n")

    # ── EXTRACT ──────────────────────────────────────────────────
    print("[1/3] Extracting raw data from cotation files ...")
    raw_data = extract_all(INPUT_DIR, COMPANIES)

    # ── TRANSFORM ────────────────────────────────────────────────
    print("[2/3] Transforming data ...")
    all_summaries = {}
    for key, cfg in COMPANIES.items():
        label = cfg["label"]
        rows  = raw_data[key]

        if not rows:
            print(f"  [WARN] No data found for {label}. Check codes/groups.")
            continue

        print(f"  → {label}: {len(rows)} trading sessions extracted")

        enriched = transform(rows)
        annual   = compute_annual(enriched, cfg["shares"])
        all_summaries[key] = (enriched, annual)

        # Convert date objects to string for CSV serialization
        for r in enriched:
            r["date"] = r["date"].isoformat()

    # ── LOAD ─────────────────────────────────────────────────────
    print("\n[3/3] Saving output files ...")
    for key, (daily, annual) in all_summaries.items():
        slug        = key.lower()
        daily_path  = os.path.join(OUTPUT_DIR, f"{slug}_daily_clean.csv")
        annual_path = os.path.join(OUTPUT_DIR, f"{slug}_annual_summary.csv")
        write_csv(daily_path,  daily,  DAILY_COLS)
        write_csv(annual_path, annual, ANNUAL_COLS)
        print(f"  ✔ {COMPANIES[key]['label']}")
        print(f"      {daily_path}")
        print(f"      {annual_path}")

    report_path = generate_report(all_summaries, OUTPUT_DIR)
    print(f"\n  ✔ Report saved: {report_path}")
    print(f"\n{'='*60}")
    print("  ETL complete. All files saved to data/output/")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    main()
