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

### 7. Run the 5-page Analytics Dashboard
```bash
streamlit run dashboard/app.py
# Open http://localhost:8501 to access all 5 pages:
# 1. Executive Summary
# 2. Sales & Profitability
# 3. Inventory Health
# 4. Customer Behavior
# 5. Returns & Data Quality Scorecard
```

### 8. Run the AI Assistant
```bash
# Set your OpenAI API key (optional – app works with fallback stubbed answers if unset)
export OPENAI_API_KEY=sk-...
streamlit run assistant/app.py --server.port 8502
# Open http://localhost:8502
```

### 9. Validate Dashboard & SQL Totals Reconciliation
```bash
psql -h localhost -U postgres -d retail_analytics -f sql/08_dashboard_validation.sql
# Verifies all 10 reconciliation slices return result_match = TRUE
```

### 10. Run All Tests
```bash
pytest tests/ -v
```

## Power BI & Dashboard Implementation

- **Interactive Web App**: Fully functional 5-page interactive dashboard with Plotly charts in `dashboard/app.py`.
- **Power BI Companion**:
  - `powerbi/powerbi_guide.md`: End-to-end setup guide for Power BI Desktop (PostgreSQL connector, star schema relationships, page visual layouts, bookmarks, and RLS).
  - `powerbi/measures.dax`: Library of all PRD-compliant DAX measures.
- **Performance Tuning Evidence**: Documented in `docs/performance.md` with EXPLAIN ANALYZE execution times (< 35ms across all core queries) and materialized view speedups (22×).

## Milestones

| Week | Status | Deliverables |
|------|--------|--------------|
| 1 | ✅ | Requirements, data generator, injected defects, data dictionary, profiling notebook, schema DDL |
| 2 | ✅ | Pandas cleaning modules, end-to-end ETL pipeline, run logging, reject tracking, constraints & indexes |
| 3 | ✅ | 13 Reporting views, Power BI DAX & guide, 5-page interactive dashboard, DQ scorecard, 10/10 reconciliation validation, performance tuning evidence |
| 4 | 🔄 | AI assistant (text-to-SQL & narratives), evaluation golden set, PySpark stretch job, documentation polish |
