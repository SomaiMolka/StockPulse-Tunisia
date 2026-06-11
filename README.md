# 📈 StockPulse Tunisia

> **"From raw data to real decisions."**

StockPulse Tunisia is a financial market intelligence platform built for the Tunisian stock exchange (**BVMT — Bourse des Valeurs Mobilières de Tunis**). It transforms 9 years of raw daily trading data into clean, structured, and interactive financial insights — covering 6 listed companies from **2016 to 2024**.

---

## 🏢 Companies Covered

| Company | Sector | Market |
|---|---|---|
| SOTUVER | Glass Manufacturing | Marché Principal |
| ONE TECH HOLDING | Technology / Cables | Marché Principal |
| POULINA GROUP HOLDING | Diversified Conglomerate | Marché Principal |
| ALKIMIA | Industrial Chemicals | Marché Alternatif |
| CARTHAGE CEMENT | Construction Materials | Marché Principal |
| AIR LIQUIDE TUNISIE | Industrial Gases | Marché Alternatif |

---

## 🛠️ Technical Stack

```
Raw BVMT CSV Files (2016–2024)
        ↓
  ETL Pipeline (Python)
        ↓
  Data Warehouse (SQL Server)
        ↓
  Power BI Dashboard  +  Predictive ML Models
        ↓
    Investment Insights
```

---

## 📁 Project Structure

```
StockPulse-Tunisia/
│
├── etl_bvmt_final_version.py       # ETL pipeline — cleans & transforms raw BVMT data
├── dwh_bvmt_final_version.py       # Loads structured data into SQL Server DWH
│
├── dashboard/                      # Power BI .pbix file
├── ml/                             # ARIMA & ML forecasting models
├── reports/                        # Financial ratio analysis report (HTML)
├── presentation/                   # Interactive HTML presentation
└── data/                           # Raw CSV input files (2016–2024)
```

---

## ⚙️ Module 1 — ETL Pipeline (`etl_bvmt_final_version.py`)

Built with **pure Python standard library** (csv, os, math, datetime, collections) — no external dependencies.

**What it does:**
- Reads 9 raw BVMT CSV files (`histo_cotation_2016` → `histo_cotation_2024`)
- Identifies companies via a lookup index handling both old numeric codes (pre-2021) and ISIN codes (post-2021)
- Parses and cleans price, volume, and date fields
- Flags suspended trading sessions (volume = 0)
- Computes financial indicators:
  - Daily return
  - 20-day moving average (MA20)
  - 50-day moving average (MA50)
  - Annualized volatility

**Output:** 12 CSV files — 6 daily clean files + 6 annual summary files per company

---

## 🗄️ Module 2 — Data Warehouse (`dwh_bvmt_final_version.py`)

Loads the cleaned data into a **SQL Server star schema** using `pyodbc`.

**Connection:**
- Server: `LAPTOP-OIQ8VLU1\SQLEXPRESS01`
- Database: `DWH_BVMT`
- Auth: Windows Authentication

**Star Schema — 4 Tables:**

| Table | Description | Rows |
|---|---|---|
| `Dim_Date` | date_key, full_date, year, month, quarter | 2,259 |
| `Dim_Security` | security_key, code, company name | 6 |
| `Dim_Market_Group` | group_key, group_id, description | 4 |
| `Fact_Daily_Trading` | open/close/high/low price, volume, turnover | 12,303 |

- Idempotent design: drops and recreates all tables on every run
- Batch inserts of 500 rows using `executemany()` (~25 trips total)
- Filters out suspended sessions before loading

---

## 📊 Module 3 — Power BI Dashboard (4 Pages)

Designed for **financial analysts and portfolio managers**, structured around 3 investor questions:

| Page | Question | Key KPIs |
|---|---|---|
| Market Overview | Which stocks are liquid enough to trade? | Avg Daily Volume: 44,730 · Most Liquid: Carthage Cement · Total Turnover: 2.53Md TND |
| Company Deep Dive | Should I invest in this specific stock? | Last Close Price · Price Growth % · Risk Level · Best Year |
| Market Analysis | Where is the market activity going? | Avg Market Growth: 78.3% · Total Volume: 444M · Market Liquidity Share |

**DAX Measures include:**
`Price Growth %` · `Annualised Volatility` · `Market Liquidity Share` · `Avg Market Growth` · `Best Year` · `Most Liquid Stock` · `Avg Daily Volume`

---

## 🤖 Module 4 — Predictive Modeling

- **ARIMA** time series model forecasting future closing prices per company
- Machine learning models trained on 9 years of historical BVMT data
- Goal: project stock price trajectory **1 to 2 years forward**

---

## 👥 Team

| Name |
|---|
| Molka Somai |
| Roua Abichou |
| Zouhour Abid |
| Mohamed Jmili |
| Eyattallah Said |
| Annoir Zorgui |

**Institution:** Esprit School of Business — Master's in Business Analytics, 2026
**Project:** FDA (Finance Data Analytics) — Bal des Projets 2026

---

## 🚀 How to Run

### 1. ETL Pipeline
```bash
python etl_bvmt_final_version.py
```
> Make sure raw CSV files are in the `data/` folder.

### 2. Load to Data Warehouse
```bash
pip install pyodbc
python dwh_bvmt_final_version.py
```
> Requires SQL Server Express installed with Windows Authentication.

---

## 📌 Key Findings

- **Carthage Cement** dominates market liquidity with **46.82% of total turnover**
- **Price-Liquidity Paradox**: higher-priced stocks are not always the most traded
- COVID-19 (2020–2021) caused a measurable shock across all 6 companies, with recovery patterns varying significantly by sector
- Average market growth across the 9-year period: **78.3%**
