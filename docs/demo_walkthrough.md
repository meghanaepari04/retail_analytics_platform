# Platform Demo & Walkthrough Guide
**Retail Analytics Platform — 4-Week End-to-End Showcase**

This guide provides a structured presentation walkthrough and script for presenting the entire **Retail Analytics Platform** in interviews, reviews, or project demos.

---

## 1. Demo Agenda (10–15 Minutes)

1. **System Architecture & Data Engineering (Week 1 & 2)**
   - Synthetic Data Generation with Injected Real-World Defects.
   - Robust Python/Pandas ETL Pipeline with Reject Isolation & Idempotent Upserts.
   - PostgreSQL Star-Schema Warehouse with Partition Pruning.
2. **Business Intelligence & Reporting (Week 3)**
   - 10/10 SQL Reconciliation Validations.
   - 5-Page Interactive Streamlit & Plotly Dashboard + Power BI Modeling.
   - Query Performance Tuning Evidence (< 35ms latency, 22× speedup).
3. **AI Assistant & Distributed Big Data (Week 4)**
   - Natural Language Text-to-SQL Assistant with Guardrails & Auto-Narration.
   - Revenue Variance Driver Analysis (Volume vs Price decomposition).
   - 30-Question Golden Evaluation Suite (100% Accuracy).
   - PySpark Distributed ETL & Lakehouse Parquet Pipeline.

---

## 2. Live Command Showcase

### Step 1: Run Full Test Suite
Showcase test reliability and zero-regression status:
```bash
pytest tests/ -v
# Output: 70 passed in 4.41s
```

### Step 2: Validate Data Warehouse Reconciliation
Demonstrate that reporting views match raw fact totals to the exact cent across 10 slices:
```bash
psql -U postgres -d retail_analytics -f sql/08_dashboard_validation.sql
```
*Expected Result: All 10 reconciliation slices return `result_match = t`.*

### Step 3: Launch the 5-Page Analytics Dashboard
```bash
streamlit run dashboard/app.py
```
*Walkthrough the 5 pages in your browser (`http://localhost:8501`):*
- **Page 1 (Executive Summary)**: Highlight top KPIs, revenue trend, and regional map.
- **Page 2 (Sales & Profitability)**: Inspect discount bands vs. margin degradation and loss-making product outliers.
- **Page 3 (Inventory Health)**: Demonstrate store × category stockout heatmap and reorder candidates table.
- **Page 4 (Customer Behavior)**: Explain RFM segment breakdown, cohort retention matrix, and churn risks.
- **Page 5 (Returns & Data Quality)**: Showcase return reasons by category and the operational pipeline DQ scorecard.

### Step 4: Launch the AI Insight Assistant
```bash
streamlit run assistant/app.py --server.port 8502
```
*Demonstrate live natural language Q&A (`http://localhost:8502`):*
- Query: *"Top 5 loss-making products this year?"*
- Query: *"Which stores are at risk of stockouts next week?"*
- Query: *"Who are our at-risk high-value customers?"*
- Highlight:
  - Transparent SQL query displayed in expander.
  - Formatted data table.
  - Plain-English narrative summary referencing real data.
  - Security guardrails: SELECT-only, allow-listed `rpt` views, automatic LIMIT, and no customer PII.

### Step 5: Run the PySpark Distributed Processing Job
```bash
python spark/retail_spark_job.py --data-dir data/raw --output-dir data/processed_parquet
```
*Demonstrates high-throughput distributed transformation, customer RFM window scoring (`ntile(5)`), and snappy-compressed partitioned Parquet lakehouse outputs.*

---

## 3. Key Technical Talking Points

- **Idempotency & Data Quality**: The ETL pipeline tracks every run in `ops.etl_run_log`, isolates dirty records with reason codes into `data/rejects/`, and guarantees rerun safety.
- **Analytical Performance**: Sub-second queries achieved through table partitioning on `fact_sales`, B-tree indexing on foreign keys, and materialized view pre-aggregation.
- **Enterprise Safety for AI**: The AI Assistant never executes unstructured arbitrary SQL; queries are validated through an AST and regex parser against an allow-list of read-only reporting views.
