

import csv
import os
import pyodbc
from datetime import datetime

# ─────────────────────────────────────────────
#  CONFIGURATION
# ─────────────────────────────────────────────

ETL_DIR = "data/output"

# SQL Server connection string
# Trusted_Connection=yes → uses Windows authentication (no password needed)
CONNECTION_STRING = (
    "DRIVER={SQL Server};"
    "SERVER=LAPTOP-OIQ8VLU1\\SQLEXPRESS01;"
    "DATABASE=DWH_BVMT;"
    "Trusted_Connection=yes;"
)

COMPANY_META = {
    "sotuver":         ("656001",       "SOTUVER",              11, "Marché Principal"),
    "one_tech":        ("753001",       "ONE TECH HOLDING",     11, "Marché Principal"),
    "poulina":         ("570001",       "POULINA GP HOLDING",   11, "Marché Principal"),
    "alkimia":         ("380070",       "ALKIMIA",              12, "Marché Alternatif"),
    "carthage_cement": ("740001",       "CARTHAGE CEMENT",      11, "Marché Principal"),
    "air_liquide":     ("TN0002300358", "AIR LIQUIDE TUNISIE",  12, "Marché Alternatif"),
}

MONTHS = {
    1:"January", 2:"February", 3:"March",     4:"April",
    5:"May",     6:"June",     7:"July",       8:"August",
    9:"September",10:"October",11:"November", 12:"December"
}

# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────

def parse_float(s):
    if not s or str(s).strip() in ("", "None"):
        return None
    try:
        return float(str(s).strip())
    except ValueError:
        return None

def parse_int(s):
    if not s or str(s).strip() in ("", "None"):
        return None
    try:
        return int(float(str(s).strip()))
    except ValueError:
        return None

# ─────────────────────────────────────────────
#  LOAD ETL FILES
# ─────────────────────────────────────────────

def load_etl():
    all_rows = []
    for slug in COMPANY_META:
        path = os.path.join(ETL_DIR, f"{slug}_daily_clean.csv")
        if not os.path.exists(path):
            print(f"  [WARN] Not found: {path}")
            continue
        with open(path, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f, delimiter=";"):
                row["_slug"] = slug
                all_rows.append(row)
        count = sum(1 for r in all_rows if r["_slug"] == slug)
        print(f"  Loaded {slug}_daily_clean.csv  ({count} rows)")
    return all_rows

# ─────────────────────────────────────────────
#  BUILD DIMENSION DATA
# ─────────────────────────────────────────────

def build_dim_date(all_rows):
    unique_dates = sorted(set(
        r["date"].strip() for r in all_rows
        if r.get("date", "").strip() not in ("", "None")
    ))
    dim_date = []
    date_to_key = {}
    for key, ds in enumerate(unique_dates, start=1):
        try:
            d = datetime.strptime(ds, "%Y-%m-%d").date()
        except ValueError:
            continue
        m = d.month
        dim_date.append((key, ds, d.year, MONTHS[m], f"Q{(m-1)//3+1}"))
        date_to_key[ds] = key
    return dim_date, date_to_key

def build_dim_security(all_rows):
    slugs = sorted(set(r["_slug"] for r in all_rows))
    dim_sec = []
    slug_to_key = {}
    for key, slug in enumerate(slugs, start=1):
        code, name, _, _ = COMPANY_META[slug]
        dim_sec.append((key, code, name))
        slug_to_key[slug] = key
    return dim_sec, slug_to_key

def build_dim_market_group():
    seen = {}
    for _, (_, _, gid, gdesc) in COMPANY_META.items():
        seen.setdefault(gid, gdesc)
    dim_mg = []
    group_to_key = {}
    for key, (gid, gdesc) in enumerate(sorted(seen.items()), start=1):
        dim_mg.append((key, gid, gdesc))
        group_to_key[gid] = key
    return dim_mg, group_to_key

def build_fact(all_rows, date_to_key, slug_to_key, group_to_key):
    fact = []
    skipped = 0
    for row in all_rows:
        slug = row["_slug"]
        ds   = row.get("date", "").strip()

        date_key     = date_to_key.get(ds)
        security_key = slug_to_key.get(slug)
        meta         = COMPANY_META.get(slug)
        if not all([date_key, security_key, meta]):
            skipped += 1
            continue

        _, _, group_id, _ = meta
        group_key = group_to_key.get(group_id)
        if not group_key:
            skipped += 1
            continue

        ouv  = parse_float(row.get("ouv"))
        clo  = parse_float(row.get("clo"))
        haut = parse_float(row.get("haut"))
        bas  = parse_float(row.get("bas"))
        qty  = parse_int(row.get("qty"))
        txn  = parse_int(row.get("txn"))
        cap  = parse_float(row.get("cap"))

        # Skip suspended / zero-price rows
        suspended = str(row.get("suspended", "0")).strip() in ("1", "True", "true")
        if suspended or (clo is None or clo == 0) and (ouv is None or ouv == 0):
            skipped += 1
            continue

        fact.append((
            date_key, security_key, group_key,
            ouv, clo, haut, bas,
            qty if qty else 0,
            txn if txn else 0,
            cap if cap else 0.0
        ))

    print(f"  Fact rows: {len(fact):,}  |  skipped: {skipped:,}")
    return fact

# ─────────────────────────────────────────────
#  SQL SERVER OPERATIONS
# ─────────────────────────────────────────────

def get_connection():
    try:
        conn = pyodbc.connect(CONNECTION_STRING)
        print("  Connected to SQL Server successfully")
        return conn
    except Exception as e:
        print(f"  [ERROR] Could not connect to SQL Server: {e}")
        raise

def drop_and_create_tables(cursor):
    """Drop tables if they exist and recreate them fresh."""

    print("  Creating tables...")

    # Drop in correct order (fact first, then dimensions)
    cursor.execute("""
        IF OBJECT_ID('dbo.Fact_Daily_Trading', 'U') IS NOT NULL
            DROP TABLE dbo.Fact_Daily_Trading
    """)
    cursor.execute("""
        IF OBJECT_ID('dbo.Dim_Date', 'U') IS NOT NULL
            DROP TABLE dbo.Dim_Date
    """)
    cursor.execute("""
        IF OBJECT_ID('dbo.Dim_Security', 'U') IS NOT NULL
            DROP TABLE dbo.Dim_Security
    """)
    cursor.execute("""
        IF OBJECT_ID('dbo.Dim_Market_Group', 'U') IS NOT NULL
            DROP TABLE dbo.Dim_Market_Group
    """)

    # Create Dim_Date
    cursor.execute("""
        CREATE TABLE dbo.Dim_Date (
            date_key    INT          PRIMARY KEY,
            full_date   DATE         NOT NULL,
            year        INT          NOT NULL,
            month_name  VARCHAR(20)  NOT NULL,
            quarter     VARCHAR(5)   NOT NULL
        )
    """)

    # Create Dim_Security
    cursor.execute("""
        CREATE TABLE dbo.Dim_Security (
            security_key  INT          PRIMARY KEY,
            security_code VARCHAR(20)  NOT NULL,
            security_name VARCHAR(100) NOT NULL
        )
    """)

    # Create Dim_Market_Group
    cursor.execute("""
        CREATE TABLE dbo.Dim_Market_Group (
            group_key         INT          PRIMARY KEY,
            group_id          INT          NOT NULL,
            group_description VARCHAR(50)  NOT NULL
        )
    """)

    # Create Fact_Daily_Trading
    cursor.execute("""
        CREATE TABLE dbo.Fact_Daily_Trading (
            date_key          INT            NOT NULL,
            security_key      INT            NOT NULL,
            group_key         INT            NOT NULL,
            open_price        DECIMAL(10,4),
            close_price       DECIMAL(10,4),
            high_price        DECIMAL(10,4),
            low_price         DECIMAL(10,4),
            volume_traded     BIGINT,
            transaction_count INT,
            turnover          DECIMAL(18,2),
            FOREIGN KEY (date_key)     REFERENCES dbo.Dim_Date(date_key),
            FOREIGN KEY (security_key) REFERENCES dbo.Dim_Security(security_key),
            FOREIGN KEY (group_key)    REFERENCES dbo.Dim_Market_Group(group_key)
        )
    """)

    print("  Tables created successfully")

def insert_in_batches(cursor, sql, data, batch_size=500):
    """Insert data in batches for performance."""
    total = len(data)
    for i in range(0, total, batch_size):
        batch = data[i:i+batch_size]
        cursor.executemany(sql, batch)
    return total

# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────

def main():
    print(f"\n{'='*60}")
    print("  BVMT DWH → SQL Server")
    print(f"{'='*60}\n")

    # ── Load ETL data ────────────────────────────────────────────
    print("[1/4] Loading ETL output files ...")
    all_rows = load_etl()
    print(f"  Total rows loaded: {len(all_rows):,}\n")
    if not all_rows:
        print("  [ERROR] No data found. Run etl_bvmt.py first.")
        return

    # ── Build dimension and fact data ────────────────────────────
    print("[2/4] Building star schema data ...")
    dim_date,   date_to_key  = build_dim_date(all_rows)
    dim_sec,    slug_to_key  = build_dim_security(all_rows)
    dim_market, group_to_key = build_dim_market_group()
    fact                     = build_fact(all_rows, date_to_key, slug_to_key, group_to_key)
    print(f"  Dim_Date:          {len(dim_date):,} rows")
    print(f"  Dim_Security:      {len(dim_sec):,} rows")
    print(f"  Dim_Market_Group:  {len(dim_market):,} rows")
    print(f"  Fact_Daily_Trading:{len(fact):,} rows\n")

    # ── Connect and insert into SQL Server ───────────────────────
    print("[3/4] Connecting to SQL Server ...")
    conn   = get_connection()
    cursor = conn.cursor()

    print("\n[4/4] Creating tables and inserting data ...")
    drop_and_create_tables(cursor)

    print("  Inserting Dim_Date ...")
    insert_in_batches(cursor,
        "INSERT INTO dbo.Dim_Date VALUES (?,?,?,?,?)",
        dim_date)

    print("  Inserting Dim_Security ...")
    insert_in_batches(cursor,
        "INSERT INTO dbo.Dim_Security VALUES (?,?,?)",
        dim_sec)

    print("  Inserting Dim_Market_Group ...")
    insert_in_batches(cursor,
        "INSERT INTO dbo.Dim_Market_Group VALUES (?,?,?)",
        dim_market)

    print("  Inserting Fact_Daily_Trading ...")
    insert_in_batches(cursor,
        "INSERT INTO dbo.Fact_Daily_Trading VALUES (?,?,?,?,?,?,?,?,?,?)",
        fact)

    conn.commit()
    cursor.close()
    conn.close()

    print(f"""
{'='*60}
  DWH COMPLETE ✔
{'='*60}
  Database  : BVMT_DWH
  Server    : LAPTOP-OIQ8VLU1\\SQLEXPRESS02

  Tables populated:
  → Dim_Date           {len(dim_date):>6,} rows
  → Dim_Security       {len(dim_sec):>6,} rows
  → Dim_Market_Group   {len(dim_market):>6,} rows
  → Fact_Daily_Trading {len(fact):>6,} rows

  Next step:
  → Open Power BI
  → Accueil → Obtenir les données → SQL Server
  → Server: LAPTOP-OIQ8VLU1\\SQLEXPRESS02
  → Database: BVMT_DWH
  → Select all 4 tables → Load
{'='*60}
""")

if __name__ == "__main__":
    main()