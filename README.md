# Retail Analytics Platform

> End-to-end retail analytics: ETL pipeline · PostgreSQL warehouse · Power BI dashboards · AI assistant

## Architecture

```
Raw CSV Data  →  Python ETL (Extract → Transform → Validate → Load)
                     ↓
           PostgreSQL Data Warehouse
           ├── stg  (raw staging)
           ├── dw   (star schema: facts + dimensions)
           ├── rpt  (reporting views + materialized views)
           └── ops  (run logs, DQ results, rejects)
                     ↓
     ┌───────────────┴───────────────┐
   Power BI                    AI Assistant
  (5 dashboards)           (Streamlit chat UI)
```

## Quick Start

### 1. Prerequisites

```bash
# Python 3.11+
python --version

# Docker + Docker Compose
docker --version
docker compose version
```

### 2. Start PostgreSQL

```bash
cd retail-analytics-platform
docker compose up postgres -d
```

### 3. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 4. Generate synthetic data

```bash
python -m generator.generate --config pipeline/config.yaml --output-dir data/raw
```

Generates ~4.1M rows across 7 tables with ~5% injected defects.

### 5. Run the ETL pipeline

```bash
python -m pipeline.run --date 2026-10-17 --config pipeline/config.yaml
```

This runs all 4 stages: **Extract → Transform → Validate → Load**

### 6. Apply full SQL schema (optional – ETL creates tables dynamically)

```bash
# Connect to PostgreSQL and run DDL files in order:
for f in sql/01_schemas.sql sql/02_dimensions.sql sql/03_facts.sql sql/04_indexes.sql sql/05_views.sql sql/06_roles.sql; do
    psql -h localhost -U postgres -d retail_analytics -f "$f"
done
```

### 7. Run the AI assistant

```bash
# Set your OpenAI API key (optional – app works without it but answers are stubbed)
export OPENAI_API_KEY=sk-...

streamlit run assistant/app.py
# Open http://localhost:8501
```

### 8. Run all tests

```bash
pytest tests/ -v --cov=pipeline --cov=assistant
```

## Repository Structure

```
retail-analytics-platform/
├── data/
│   ├── raw/            # Source CSVs (generated)
│   ├── processed/      # Cleaned CSVs
│   └── rejects/        # Rejected rows with reason codes
├── generator/
│   └── generate.py     # Synthetic data generator (Faker + NumPy)
├── pipeline/
│   ├── cleaning/
│   │   ├── dates.py        # Date parsing + validation
│   │   ├── normalize.py    # Text normalization + canonical mappings
│   │   ├── deduplicate.py  # Dedup with survivorship rules
│   │   └── validate.py     # Business rules + outlier detection
│   ├── extract.py      # Stage 1: CSV → stg schema
│   ├── transform.py    # Stage 2: All cleaning + validation
│   ├── load.py         # Stage 3: Upsert into dw schema
│   ├── run.py          # Entry point: orchestrates all stages
│   ├── db.py           # SQLAlchemy engine + config loader
│   └── config.yaml     # Central configuration
├── sql/
│   ├── 01_schemas.sql      # Schema + ops tables
│   ├── 02_dimensions.sql   # dim_date, dim_customer (SCD2), dim_product (SCD2), etc.
│   ├── 03_facts.sql        # fact_sales (partitioned), fact_returns, fact_inventory_snapshot
│   ├── 04_indexes.sql      # Performance indexes
│   ├── 05_views.sql        # All rpt.* reporting views + materialized views
│   └── 06_roles.sql        # etl_writer, bi_reader, ai_reader
├── assistant/
│   ├── assistant.py    # Text-to-SQL engine + SQL validator + cache
│   └── app.py          # Streamlit chat UI
├── tests/
│   ├── test_cleaning.py    # Unit tests: dates, normalize, dedup, validate
│   └── test_assistant.py   # SQL validator guardrail tests
├── docs/               # PRD, data dictionary, ER diagram, performance notes
├── powerbi/            # .pbix file, theme, screenshots
├── spark/              # Stretch: PySpark job
├── docker-compose.yml
├── Dockerfile.etl
└── requirements.txt
```

## Data Model (Star Schema)

| Type | Table | Grain |
|------|-------|-------|
| Fact | `dw.fact_sales` | One row per order line |
| Fact | `dw.fact_returns` | One row per returned line |
| Fact | `dw.fact_inventory_snapshot` | Product × Store × Date |
| Dim | `dw.dim_date` | Calendar (2020–2030) |
| Dim | `dw.dim_customer` | SCD Type 2 |
| Dim | `dw.dim_product` | SCD Type 2 |
| Dim | `dw.dim_store` | Store + region |
| Dim | `dw.dim_channel` | Online / In-Store / Marketplace |
| Dim | `dw.dim_return_reason` | Reason + group |

## Metric Definitions

| Metric | Definition |
|--------|-----------|
| Gross Revenue | `SUM(quantity × unit_price)` |
| Net Revenue | Gross Revenue − discounts |
| Gross Profit | Net Revenue − `SUM(quantity × unit_cost)` |
| Margin % | Gross Profit / Net Revenue |
| AOV | Net Revenue / distinct orders |
| Return Rate | Returned units / sold units |
| Days of Cover | Available / avg daily units (30d) |
| Stockout | `available = 0` while 30d sales > 0 |
| Overstock | Days of cover > 90 |
| Dead Stock | No sales in 90d and `on_hand > 0` |

## ETL Pipeline Details

### Stages

1. **Extract** – reads raw CSVs as text into stg schema
2. **Transform** – runs per-table cleaning passes:
   - Dates: ISO 8601 normalization, reject unparseable
   - Text: canonical mapping (region, category, payment, channel)
   - Dedup: by business keys, latest-wins survivorship
   - Validate: business rules (qty > 0, price > 0, FK integrity)
   - Outliers: IQR quarantine (flagged but traceable)
3. **Validate** – fail-fast if any table exceeds 10% reject rate
4. **Load** – idempotent upserts into dw schema; reject log → ops.reject_records

### Run logging

Every run produces a record in `ops.etl_run_log` with start/end time, rows read/loaded/rejected, and status.

## AI Assistant

- **Interface**: Streamlit chat (http://localhost:8501)
- **Approach**: Text-to-SQL restricted to `rpt` schema views
- **Guardrails**: SELECT-only, allow-listed views, auto-LIMIT 500, 10s query timeout
- **Transparency**: SQL and data table shown with every answer
- **No PII**: `rpt` views exclude customer emails and phones

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DB_HOST` | PostgreSQL host | `localhost` |
| `DB_NAME` | Database name | `retail_analytics` |
| `DB_USER` | DB user | `etl_writer` |
| `DB_PASSWORD` | DB password | `changeme` |
| `OPENAI_API_KEY` | OpenAI API key (for AI assistant) | *(stubbed if unset)* |

## Testing

```bash
# All tests
pytest tests/ -v

# With coverage report
pytest tests/ -v --cov=pipeline --cov=assistant --cov-report=term-missing

# Individual modules
pytest tests/test_cleaning.py -v
pytest tests/test_assistant.py -v
```

## Power BI

Connect Power BI Desktop to PostgreSQL (localhost:5432, database: retail_analytics, user: bi_reader).
Import the following views for each dashboard page:

| Page | Views |
|------|-------|
| Executive Summary | `rpt_sales_monthly_region_category` |
| Sales & Profitability | `rpt_sales_daily`, `rpt_profitability_product` |
| Inventory Health | `rpt_inventory_health` |
| Customer Behavior | `rpt_customer_rfm`, `rpt_customer_cohorts` |
| Returns & Quality | `rpt_returns_analysis` + `ops.dq_results` |

## Milestones

| Week | Status | Deliverables |
|------|--------|--------------|
| 1 | ✅ | Repo structure, data generator, cleaning modules, SQL schema |
| 2 | 🔄 | ETL pipeline end-to-end, run logging, rejects |
| 3 | ⏳ | Reporting views, Power BI dashboard, performance tuning |
| 4 | ⏳ | AI assistant, evaluation set, PySpark stretch, README polish |
