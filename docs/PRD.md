# Retail Analytics Platform: Product Requirements Document

**Project:** End-to-end retail analytics with ETL, PostgreSQL warehouse, Power BI dashboards and an AI insight assistant **Version:** 1.0 | **Date:** October 17, 2026 | **Status:** Draft for build

## 1. Overview

### 1.1 Purpose

Build a retail analytics platform that ingests messy transactional data, cleans and validates it through an automated ETL pipeline, stores it in an optimized PostgreSQL warehouse, and serves interactive Power BI dashboards plus a GenAI assistant that explains the numbers in plain English.

### 1.2 Business scenario

A retail company sells products across multiple regions. Leadership cannot currently answer basic questions reliably because data arrives as inconsistent exports from orders, customers, products, inventory and returns systems. They want a single trusted source of truth for sales, profitability, inventory health, customer behavior and future opportunities.

### 1.3 Product vision

One pipeline, one warehouse, one set of metric definitions. A regional manager should open a dashboard, see what changed, and ask the assistant "why did West region margin drop in September?" and get a grounded answer backed by real queries.

## 2. Problem Statement and Goals

### 2.1 Problems

- Source data has missing values, duplicates, invalid records, inconsistent formats and orphaned keys.
- Metrics such as revenue, margin and return rate are computed differently by different teams.
- Inventory problems (stockouts, overstock, dead stock) are discovered late.
- Customer behavior (repeat rate, churn, segments) is not tracked systematically.
- Insights need an analyst for every question, which does not scale.

### 2.2 Goals

1. Produce a clean, validated, relational dataset with documented quality rules.
2. Automate the full ETL flow: Extract, Transform, Validate, Load, with logging and rejects.
3. Model an optimized star schema in PostgreSQL that answers core questions in under 2 seconds.
4. Deliver a Power BI dashboard covering sales, profitability, inventory, customers and returns.
5. Add an AI assistant that answers natural-language questions and generates narrative insights.
6. Show forward-looking opportunities (demand trends, reorder risk, high-value segments).

### 2.3 Non-goals

- Real-time streaming ingestion (batch only in v1).
- Writing back to source systems or running transactions.
- Full-scale ML forecasting platform (simple, explainable forecasts only).
- Multi-tenant access or enterprise SSO.

## 3. Users and Personas

| Persona | Needs | Primary surface |
| --- | --- | --- |
| Executive (CEO/COO) | Revenue, margin, regional performance at a glance | Executive dashboard page |
| Regional Sales Manager | Region and product performance, targets vs actuals, return drivers | Sales and Returns pages |
| Inventory / Supply Planner | Stockouts, overstock, days of cover, reorder suggestions | Inventory page |
| Marketing / CRM Lead | Customer segments, repeat rate, churn risk, CLV | Customer page |
| Data Analyst | Trusted tables, SQL views, data quality visibility | PostgreSQL, DQ report |
| Non-technical stakeholder | Plain-English answers | AI assistant |

## 4. Scope

### 4.1 In scope (MVP)

- Synthetic but realistically messy datasets: orders, order items, customers, products, inventory, returns, regions/stores.
- Python + Pandas cleaning and validation.
- Automated ETL with run logging, reject tables and idempotent loads.
- PostgreSQL star schema with constraints, indexes, views and materialized views.
- Power BI dashboard with 5 pages and drill-through.
- GenAI assistant (text-to-SQL over safe views plus insight narratives) via an LLM API.

### 4.2 Stretch

- PySpark job that reprocesses a large synthetic dataset (10M+ rows) to demonstrate distributed processing.
- Scheduled runs (cron or Airflow-lite).
- Simple demand forecast (moving average / seasonal naive).

### 4.3 Out of scope

Real-time ingestion, mobile app, role-based row-level security beyond a basic Power BI region filter demo.

## 5. System Architecture

```
Raw Data Sources (Orders, Customers, Products, Inventory, Returns)
        |
        v
Python Data Processing (missing values, duplicates, invalid records, normalization)
        |
        v
ETL Pipeline (Extract -> Transform -> Validate -> Load)
        |
        v
PostgreSQL Data Warehouse (fact tables, dimensions, constraints, SQL views)
        |
        +--> Power BI (dashboards and KPIs)
        +--> GenAI Assistant (questions and explanations)
```

### 5.1 Layers

- **Raw/Landing:** immutable CSV/JSON files stored by run date.
- **Staging schema (`stg`):** raw data loaded as text-typed tables, one row per source row, plus load metadata.
- **Core warehouse schema (`dw`):** cleaned dimensions and facts.
- **Reporting schema (`rpt`):** views and materialized views used by Power BI and the AI assistant.
- **Ops schema (`ops`):** etl\_run\_log, dq\_results, reject\_records.

## 6. Data Requirements

### 6.1 Source datasets

| Source | Key fields | Approx. volume (synthetic) |
| --- | --- | --- |
| Orders | order\_id, customer\_id, order\_date, store\_id, channel, status, payment\_method, discount | 500k |
| Order items | order\_id, product\_id, quantity, unit\_price, discount, unit\_cost | 1.5M |
| Customers | customer\_id, name, email, phone, city, region, signup\_date, segment | 80k |
| Products | product\_id, sku, name, category, subcategory, brand, cost, list\_price, supplier | 5k |
| Inventory | snapshot\_date, product\_id, store\_id, on\_hand, reserved, reorder\_level, lead\_time\_days | 2M snapshots |
| Returns | return\_id, order\_id, product\_id, return\_date, reason, refund\_amount | 60k |
| Stores/Regions | store\_id, store\_name, city, region, country | 100 |

### 6.2 Injected data problems (to make the cleaning work real)

- Missing values: null customer emails, null prices, blank regions.
- Duplicates: repeated order lines, customers with different IDs but same email.
- Invalid records: negative quantities, future order dates, zero or negative prices, return before order date.
- Inconsistent formats: dates in multiple formats, `NY`/`New York`/`new york`, currency symbols in numbers, mixed-case categories.
- Referential problems: orders pointing to unknown customers or products, returns for non-existent orders.
- Outliers: extreme quantities, unit price 100x normal.

Target: roughly 3 to 8 percent of rows carry at least one defect, documented in a data dictionary.

### 6.3 Data generation

A Python generator (Faker + NumPy) creates reproducible data with a fixed seed, seasonal sales patterns, regional differences, product lifecycle effects and the defects above. Configurable row counts via a config file.

## 7. Functional Requirements

### 7.1 Data processing and cleaning (Python + Pandas)

| ID | Requirement | Priority |
| --- | --- | --- |
| DP-1 | Profile each source: row counts, null %, distinct counts, min/max, type issues | P0 |
| DP-2 | Standardize dates to ISO 8601 and reject unparseable values | P0 |
| DP-3 | Normalize text (trim, case, canonical names for regions, categories, payment methods) via mapping tables | P0 |
| DP-4 | Handle missing values by rule: drop, default, impute (documented per column) | P0 |
| DP-5 | Deduplicate with defined keys and survivorship rules (latest record wins) | P0 |
| DP-6 | Validate business rules (qty > 0, price > 0, order\_date <= today, return\_date >= order\_date) | P0 |
| DP-7 | Flag outliers with IQR or z-score and quarantine rather than silently delete | P1 |
| DP-8 | Write every rejected row to a reject file/table with a reason code | P0 |

### 7.2 ETL pipeline

| ID | Requirement | Priority |
| --- | --- | --- |
| ETL-1 | Single entry point (`python -m pipeline.run --date YYYY-MM-DD`) running all stages | P0 |
| ETL-2 | Stages: Extract, Transform, Validate, Load, each independently re-runnable | P0 |
| ETL-3 | Idempotent loads using upserts (`INSERT ... ON CONFLICT`) so re-runs do not duplicate | P0 |
| ETL-4 | Incremental loading using watermark on order\_date / updated\_at for facts | P1 |
| ETL-5 | Slowly changing dimension Type 2 for customers (segment/region change) and products (price change) | P1 |
| ETL-6 | Run logging: run\_id, start/end, rows read/loaded/rejected per table, status | P0 |
| ETL-7 | Fail-fast on critical validation (e.g., more than 10% rejects) with a clear error | P0 |
| ETL-8 | Retry with backoff for DB connection errors | P2 |
| ETL-9 | Config-driven (YAML/env) for paths, DB credentials, thresholds | P0 |
| ETL-10 | Scheduling via cron or a lightweight scheduler; documented Airflow DAG optional | P2 |

### 7.3 Data warehouse (PostgreSQL)

See section 8 for the full model. Requirements:

- Star schema with surrogate keys, foreign keys, NOT NULL, CHECK and UNIQUE constraints.
- Indexes on join and filter columns; partitioning of the sales fact by month once above \~5M rows.
- Reporting views that encode official metric definitions.
- Role separation: `etl_writer`, `bi_reader`, `ai_reader` (read-only on `rpt` only).

### 7.4 Dashboards (Power BI)

See section 9.

### 7.5 AI insight assistant

See section 10.

## 8. Data Model

### 8.1 Star schema

**Dimensions**

| Table | Key columns | Notes |
| --- | --- | --- |
| `dw.dim_date` | date\_key (int yyyymmdd), date, day, week, month, quarter, year, is\_weekend, is\_holiday | Generated calendar |
| `dw.dim_customer` | customer\_key, customer\_id, name, email, city, region, segment, signup\_date, valid\_from, valid\_to, is\_current | SCD2 |
| `dw.dim_product` | product\_key, product\_id, sku, name, category, subcategory, brand, supplier, cost, list\_price, valid\_from, valid\_to, is\_current | SCD2 |
| `dw.dim_store` | store\_key, store\_id, store\_name, city, region, country |  |
| `dw.dim_channel` | channel\_key, channel\_name | Online, in-store, marketplace |
| `dw.dim_return_reason` | reason\_key, reason\_name, reason\_group |  |

**Facts**

| Table | Grain | Measures |
| --- | --- | --- |
| `dw.fact_sales` | one row per order line | quantity, gross\_amount, discount\_amount, net\_amount, cost\_amount, profit\_amount |
| `dw.fact_inventory_snapshot` | product x store x day | on\_hand, reserved, available, reorder\_level, lead\_time\_days |
| `dw.fact_returns` | one row per returned line | returned\_qty, refund\_amount |

### 8.2 Operational tables

- `ops.etl_run_log(run_id, started_at, finished_at, status, rows_read, rows_loaded, rows_rejected)`
- `ops.dq_results(run_id, table_name, rule_name, failed_count, total_count, severity)`
- `ops.reject_records(run_id, source_table, source_key, reason_code, raw_payload jsonb)`

### 8.3 Constraints and optimization

- PK on every table; FKs from facts to dimensions.
- CHECK: quantity > 0, net\_amount >= 0, on\_hand >= 0.
- Indexes: `fact_sales(date_key)`, `fact_sales(product_key)`, `fact_sales(store_key)`, `fact_sales(customer_key)`; composite `(date_key, store_key)` for regional time series.
- Materialized views for monthly sales by region/category, refreshed at end of ETL.
- Use `EXPLAIN ANALYZE` on the 10 core queries and keep the evidence in `docs/performance.md`.
- Window functions for rankings, running totals and cohort analysis.

### 8.4 Reporting views (`rpt` schema)

- `rpt_sales_daily`, `rpt_sales_monthly_region_category`
- `rpt_profitability_product` (revenue, cost, margin %, rank)
- `rpt_inventory_health` (days of cover, stockout flag, overstock flag, dead-stock flag)
- `rpt_customer_rfm` (recency, frequency, monetary, segment)
- `rpt_customer_cohorts` (signup month x months since, retention %)
- `rpt_returns_analysis` (return rate by product, reason, region)
- `rpt_opportunities` (growth products, at-risk customers, reorder candidates)

## 9. Dashboard Requirements (Power BI)

### 9.1 Global

- Slicers: date range, region, store, category, channel.
- Consistent theme, KPI cards with period-over-period delta, tooltips with definitions.
- Import mode from `rpt` views (DirectQuery optional for demo).
- Each page loads within 3 seconds on the synthetic dataset.

### 9.2 Pages

**Page 1: Executive Summary**

- KPIs: Revenue, Gross Profit, Margin %, Orders, Average Order Value, Return Rate, Active Customers.
- Revenue and profit trend (monthly), region map, top 5 / bottom 5 categories.
- AI insight card (text from the assistant's weekly summary).

**Page 2: Sales and Profitability**

- Revenue by region, category, channel; margin by product (scatter: revenue vs margin %).
- Discount impact analysis (discount band vs margin).
- Top 20 products and loss-making products table.

**Page 3: Inventory Health**

- KPIs: stockout rate, overstock value, days of cover, dead stock value.
- Heatmap of stockouts by store and category.
- Reorder candidates table (available < reorder level, with lead time).
- Inventory turnover by category.

**Page 4: Customer Behavior**

- New vs returning customers, repeat purchase rate, RFM segment distribution.
- Cohort retention matrix, customer lifetime value by segment.
- Churn-risk list (high value, no purchase in 90+ days).

**Page 5: Returns and Quality**

- Return rate by product, category, region; reasons breakdown.
- Products with abnormal return rate.
- Data quality scorecard from `ops.dq_results` (last run status, reject counts).

### 9.3 Interactivity

Drill-through from category to product to order lines, bookmarks for "Executive" and "Analyst" views, and a region-based row-level security demo.

## 10. AI Insight Assistant

### 10.1 Capabilities

1. **Ask questions in natural language:** "Which products had the highest margin in the South last quarter?"
2. **Explain changes:** "Why did revenue drop in March?" using driver analysis (volume vs price vs mix vs region).
3. **Generate narrative summaries:** weekly or monthly executive summary written from computed metrics.
4. **Suggest opportunities:** grounded in `rpt_opportunities` (e.g., reorder risks, rising categories, churn-risk high-value customers).

### 10.2 Design

- **Interface:** simple Streamlit or FastAPI + web chat page (Power BI embeds a link or summary text).
- **Approach:** text-to-SQL restricted to the `rpt` views. The LLM receives a schema description, metric glossary and few-shot examples; it returns a SQL query; the backend validates and runs it; the result rows go back to the LLM for a plain-English answer.
- **Guardrails:**
  - Read-only DB role limited to `rpt` schema.
  - SQL validator: only `SELECT`, single statement, allow-listed views, enforced `LIMIT`, statement timeout of 10 seconds.
  - The assistant must show the SQL and the data table used with every answer.
  - If the question cannot be answered from available data, it says so instead of guessing.
  - No customer PII (emails, phones) exposed in any `rpt` view used by the assistant.
- **Narrative insights:** a scheduled job computes the key metrics and deltas in Python/SQL first; the LLM only writes the explanation from those numbers, never calculates them.
- **Evaluation:** a set of 30 golden questions with expected SQL results; target of at least 85% correct answers; log failures for prompt iteration.
- **Cost and latency:** cache repeated questions; target under 8 seconds per answer.

### 10.3 Example interactions

| Question | Expected behavior |
| --- | --- |
| "Top 5 loss-making products this year?" | Query `rpt_profitability_product`, return table plus a one-line comment |
| "Which stores are at risk of stockouts next week?" | Query `rpt_inventory_health`, list items with days of cover below lead time |
| "Why is the return rate up in the West?" | Break down by category and reason, highlight top contributor |
| "What should we focus on next quarter?" | Summarize items from `rpt_opportunities` with supporting numbers |

## 11. Metric Definitions (single source of truth)

| Metric | Definition |
| --- | --- |
| Gross Revenue | SUM(quantity x unit\_price) |
| Net Revenue | Gross Revenue minus discounts |
| Gross Profit | Net Revenue minus SUM(quantity x unit\_cost) |
| Margin % | Gross Profit / Net Revenue |
| AOV | Net Revenue / distinct orders |
| Return Rate | Returned units / sold units (same period, same product) |
| Days of Cover | Available stock / average daily units sold over last 30 days |
| Stockout | Available = 0 while 30-day sales > 0 |
| Overstock | Days of cover > 90 |
| Dead Stock | No sales in 90 days and on\_hand > 0 |
| Repeat Rate | Customers with 2+ orders / customers with 1+ orders |
| RFM Segment | Quintile scores on recency, frequency, monetary mapped to Champions, Loyal, At Risk, Lost, etc. |
| CLV (simple) | Average order value x purchase frequency x expected lifespan |

## 12. Technology Stack

| Layer | Technology | Role |
| --- | --- | --- |
| Data processing | Python + Pandas | Cleaning, normalization, validation |
| ETL | Python (modular package, SQLAlchemy / psycopg) | Extract, transform, validate, load |
| Warehouse | PostgreSQL | Relational modeling, SQL, optimization |
| BI | Power BI | Interactive dashboards and KPIs |
| Distributed (stretch) | PySpark | Large-scale processing exposure |
| GenAI | LLM API | Natural-language insights and Q&A |
| Supporting | pytest, Great Expectations or custom DQ checks, Docker Compose, Git, YAML config | Testing, quality, packaging |

**Sequencing rule:** keep PostgreSQL, Python and Power BI as the core. Add PySpark and GenAI only after the main pipeline works end to end.

## 13. Non-Functional Requirements

- **Performance:** core queries under 2 seconds on 1.5M fact rows; full ETL for the base dataset under 10 minutes on a laptop.
- **Reliability:** idempotent, restartable runs; no partial loads (transaction per table load).
- **Data quality:** at least 99% of loaded rows pass all P0 rules; all rejects traceable.
- **Security:** secrets in environment variables, least-privilege DB roles, no PII in AI-facing views.
- **Maintainability:** modular code, type hints, README, data dictionary, ER diagram.
- **Reproducibility:** `docker compose up` brings up PostgreSQL; one command generates data and runs ETL.
- **Observability:** structured logs, run history table, DQ scorecard in dashboard.

## 14. Testing and Validation

- **Unit tests:** each cleaning function (dates, normalization, dedup) with edge cases.
- **Pipeline tests:** run ETL on a small fixture dataset and assert row counts, reject counts and totals.
- **Reconciliation:** source revenue minus rejected revenue must equal warehouse revenue.
- **Idempotency test:** run twice, assert identical row counts.
- **SQL tests:** FK integrity, no negative quantities, one current row per SCD2 business key.
- **Dashboard validation:** Power BI totals match SQL totals for 10 sample slices.
- **AI evaluation:** golden question set as described in section 10.

## 15. Milestones and Timeline (suggested 4 weeks)

| Week | Deliverables |
| --- | --- |
| 1 | Requirements finalized, data generator with injected defects, data dictionary, profiling notebook, ER diagram |
| 2 | Pandas cleaning modules, ETL pipeline with logging and rejects, PostgreSQL schema, constraints, indexes, loads working end to end |
| 3 | Reporting views, metric definitions, Power BI 5-page dashboard, DQ scorecard, performance tuning evidence |
| 4 | AI assistant (text-to-SQL plus narratives), evaluation set, PySpark stretch job, documentation, demo video, README polish |

## 16. Success Metrics

| Metric | Target |
| --- | --- |
| Pipeline success on clean re-run | 100%, idempotent |
| Rows loaded passing validation | 99%+ |
| Defects caught vs injected | 95%+ |
| Core query latency | Under 2 seconds |
| Dashboard load time | Under 3 seconds per page |
| AI golden-set accuracy | 85%+ |
| Business questions answerable without an analyst | 80%+ of a 20-question list |

## 17. Risks and Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Scope creep into PySpark / GenAI before the core works | Unfinished project | Strict sequencing: core first, stretch later |
| LLM generates wrong or unsafe SQL | Wrong answers, data risk | Read-only role, allow-listed views, validator, show SQL, golden-set tests |
| LLM hallucinated numbers | Loss of trust | LLM never computes; it only narrates query results |
| Synthetic data too clean or unrealistic | Weak demo | Documented defect injection, seasonality and regional skew |
| Power BI licensing / platform limits | Cannot demo | Use Power BI Desktop with import mode; export PDF and screenshots as backup |
| Slow queries at scale | Poor UX | Indexes, materialized views, partitioning, EXPLAIN evidence |
| SCD2 complexity | Delays | Ship SCD1 first, upgrade to SCD2 in week 3 if time allows |

## 18. Repository Structure

```
retail-analytics-platform/
  data/raw/  data/processed/  data/rejects/
  generator/            # synthetic messy data
  pipeline/
    extract.py  transform.py  validate.py  load.py  run.py
    cleaning/           # pandas modules
    config.yaml
  sql/
    01_schemas.sql  02_dimensions.sql  03_facts.sql
    04_indexes.sql  05_views.sql  06_roles.sql
  powerbi/              # .pbix, theme, screenshots
  assistant/            # text-to-SQL, validator, prompts, eval set
  spark/                # stretch job
  tests/
  docs/                 # PRD, data dictionary, ER diagram, performance
  docker-compose.yml
  README.md
```

## 19. Deliverables Checklist

- [ ] PRD (this document)
- [ ] Data generator and data dictionary
- [ ] Cleaning and ETL code with tests
- [ ] PostgreSQL DDL, indexes, views, roles
- [ ] ER diagram and architecture diagram
- [ ] Power BI dashboard (.pbix) and screenshots
- [ ] AI assistant with guardrails and evaluation results
- [ ] Performance evidence (EXPLAIN ANALYZE before and after)
- [ ] README with setup, architecture, results and demo video

## 20. Future Opportunities

- Streaming ingestion (Kafka) and near-real-time inventory alerts.
- ML demand forecasting and dynamic reorder points.
- Price elasticity and promotion effectiveness modeling.
- Customer churn prediction and next-best-offer recommendations.
- Proactive AI alerts (Slack or email) when KPIs breach thresholds.
