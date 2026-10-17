# Power BI Implementation Guide
**Retail Analytics Platform — 5-Page Enterprise Dashboard**

This guide provides end-to-end instructions for connecting **Power BI Desktop** to the PostgreSQL data warehouse and building the 5-page enterprise analytics dashboard specified in **PRD §9**.

---

## 1. Connecting Power BI to PostgreSQL

### Prerequisites
- Power BI Desktop installed (Windows or via VM/Parallels on Mac).
- Npgsql connector or PostgreSQL ODBC Driver installed.
- PostgreSQL database running (`localhost:5432/retail_analytics`).

### Connection Steps
1. In Power BI Desktop, click **Get Data** → **Database** → **PostgreSQL database**.
2. **Server**: `localhost:5432`
3. **Database**: `retail_analytics`
4. **Data Connectivity mode**: **Import** (recommended for sub-second UI interactions per PRD §9.1) or **DirectQuery**.
5. **Credentials**:
   - User name: `bi_reader` (or `postgres`)
   - Password: password configured in `sql/06_roles.sql`
6. In the **Navigator** window, select the following schemas and tables/views:
   - **`rpt` Reporting Views**:
     - `rpt_executive_summary`
     - `rpt_sales_daily`
     - `rpt_sales_monthly_region_category`
     - `rpt_profitability_product`
     - `rpt_inventory_health`
     - `rpt_inventory_turnover`
     - `rpt_customer_rfm`
     - `rpt_customer_cohorts`
     - `rpt_returns_analysis`
     - `rpt_opportunities`
     - `rpt_discount_impact`
     - `rpt_new_vs_returning`
     - `rpt_dq_scorecard`
   - **`dw` Star Schema (for custom drill-downs)**:
     - `fact_sales`
     - `fact_inventory_snapshot`
     - `fact_returns`
     - `dim_date`
     - `dim_product` (filter `is_current = TRUE` or use `dim_product_current`)
     - `dim_customer` (filter `is_current = TRUE` or use `dim_customer_current`)
     - `dim_store`
     - `dim_channel`
     - `dim_return_reason`

---

## 2. Data Model Relationships (Star Schema)

When modeling the core `dw` tables:

```
          ┌────────────────┐
          │  dim_channel   │
          └───────┬────────┘
                  │ 1:N (channel_key)
┌──────────────┐  │  ┌──────────────┐
│  dim_store   ├──┼──┤  fact_sales  ├───┬──────────────┐
└──────────────┘1:N  └──────┬───────┘   │1:N           │1:N
                            │1:N        │              │
                   ┌────────┴───────┐   │       ┌──────┴───────┐
                   │  dim_product   ├───┤       │ dim_customer │
                   └────────┬───────┘   │       └──────────────┘
                            │1:N        │
              ┌─────────────┴─────┐     │
              │fact_inventory_snap│     │
              └───────────────────┘     │
                                        │
┌──────────────────┐  ┌─────────────┐   │
│dim_return_reason ├──┤fact_returns ├───┘ (order_id)
└──────────────────┘  └─────────────┘
```

- `dw_dim_date[date_key]` **1 : N** `dw_fact_sales[date_key]`
- `dw_dim_product[product_key]` **1 : N** `dw_fact_sales[product_key]`
- `dw_dim_store[store_key]` **1 : N** `dw_fact_sales[store_key]`
- `dw_dim_customer[customer_key]` **1 : N** `dw_fact_sales[customer_key]`
- `dw_dim_channel[channel_key]` **1 : N** `dw_fact_sales[channel_key]`
- `dw_dim_product[product_key]` **1 : N** `dw_fact_inventory_snapshot[product_key]`
- `dw_dim_store[store_key]` **1 : N** `dw_fact_inventory_snapshot[store_key]`
- `dw_dim_return_reason[reason_key]` **1 : N** `dw_fact_returns[reason_key]`

---

## 3. Global Filters & Slicers (PRD §9.1)

Place a top filter banner or collapsible left sidebar containing:
1. **Date Range**: Slider on `dim_date[date]`
2. **Region**: Dropdown slicer on `dim_store[region]`
3. **Store**: Dropdown slicer on `dim_store[store_name]`
4. **Category**: Buttons/Dropdown on `dim_product[category]`
5. **Channel**: Segmented control on `dim_channel[channel_name]`

---

## 4. 5 Dashboard Pages Specification

### Page 1: Executive Summary
- **KPI Cards**:
  - Net Revenue with MoM Delta (`[Net Revenue]`, `[Net Revenue MoM Growth %]`)
  - Gross Profit & Margin % (`[Gross Profit]`, `[Margin %]`)
  - Total Orders (`[Total Orders]`)
  - Average Order Value (`[Average Order Value (AOV)]`)
  - Active Customers (`[Active Customers]`)
  - Return Rate % (`[Return Rate %]`)
- **Visuals**:
  - Monthly Revenue & Profit Trend: Combo Chart (Line for Margin %, Bar for Net Revenue)
  - Sales by Region: Map / Clustered Bar chart (`dim_store[region]` × `[Net Revenue]`)
  - Top 5 & Bottom 5 Product Categories: Stacked Bar Chart
  - **AI Weekly Insight Card**: Dynamic narrative card sourced from `assistant` executive summary.

### Page 2: Sales and Profitability
- **Visuals**:
  - Revenue breakdown by Channel and Region: Matrix table with data bars
  - Product Margin Scatter Plot: X-axis = `[Net Revenue]`, Y-axis = `[Margin %]`, Bubble Size = `[Units Sold]`, Tooltip = `Product Name`
  - Discount Impact Analysis: Column chart grouping by `rpt_discount_impact[discount_band]` showing `[Margin %]` degradation
  - Top 20 Most Profitable Products vs Loss-Making Products: Table with Conditional Formatting (green for high margin, red for negative margin).

### Page 3: Inventory Health
- **KPI Cards**:
  - Stockout Rate % (`[Stockout Rate %]`)
  - Overstock Value (`[Overstock Value]`)
  - Average Days of Cover (`[Days of Cover]`)
  - Dead Stock Value (`[Dead Stock Value]`)
- **Visuals**:
  - Store × Category Stockout Heatmap: Matrix visual with conditional color scales (red = high stockout risk)
  - Reorder Candidates Table: Filtered to `available < reorder_level`, showing `lead_time_days`, `available`, `reorder_level`
  - Category Inventory Turnover: Bar chart of `[Inventory Turnover Ratio]` by Category.

### Page 4: Customer Behavior
- **KPI Cards**:
  - Total Customers & Repeat Purchase Rate % (`[Repeat Purchase Rate %]`)
  - Customer Lifetime Value (`[Customer Lifetime Value (CLV)]`)
- **Visuals**:
  - New vs Returning Customers: 100% Stacked Area Chart over time
  - RFM Customer Segments: Treemap / Donut chart showing customer counts by `rfm_segment` (Champions, Loyal, At Risk, Hibernating, etc.)
  - Cohort Retention Matrix: Cohort signup month vs Months Since First Order (Heatmap Matrix)
  - Churn-Risk High-Value Customers: Table listing customers with RFM Recency > 90 days and Historical Spend > $1,000.

### Page 5: Returns and Data Quality
- **Visuals**:
  - Return Rate by Category & Region: Clustered Bar Chart
  - Return Reasons Breakdown: Donut Chart (`dim_return_reason[reason_group]`)
  - High Return Rate Outliers: Scatter or Bar chart highlighting products with return rates > 8%
  - **Data Quality Scorecard (from `rpt_dq_scorecard`)**:
    - Status Badge (SUCCESS / WARNING / FAILURE)
    - Records Read vs Rejected KPI
    - Table of DQ Rules Tested, Failure Counts, and Severity.

---

## 5. Row-Level Security (RLS) Setup (PRD §9.3)

To restrict regional managers to only view data from their region:
1. In Power BI Desktop, go to **Modeling** tab → **Manage roles**.
2. Click **Create** and name the role: `Region_Manager`.
3. Select table `dw_dim_store`.
4. Enter DAX filter expression:
   ```dax
   [region] = USERPRINCIPALNAME()
   // Or for static regional roles:
   // [region] = "North"
   ```
5. Click **Save**. Use **View as** to verify that filters propagate across all fact tables.
