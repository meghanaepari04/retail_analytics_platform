-- ============================================================
-- 05_views.sql  –  Reporting views (rpt schema)
-- All official metric definitions live here (PRD §11)
-- ============================================================

-- ── rpt_sales_daily ─────────────────────────────────────────
CREATE OR REPLACE VIEW rpt.rpt_sales_daily AS
SELECT
    dd.date                                         AS sale_date,
    dd.year,
    dd.month,
    dd.month_name,
    dd.quarter,
    dd.week_of_year,
    ds.region,
    ds.store_name,
    dc.channel_name,
    COUNT(DISTINCT fs.order_id)                     AS orders,
    SUM(fs.quantity)                                AS units_sold,
    SUM(fs.gross_amount)                            AS gross_revenue,
    SUM(fs.discount_amount)                         AS total_discount,
    SUM(fs.net_amount)                              AS net_revenue,
    SUM(fs.cost_amount)                             AS total_cost,
    SUM(fs.profit_amount)                           AS gross_profit,
    ROUND(SUM(fs.profit_amount) / NULLIF(SUM(fs.net_amount), 0) * 100, 2) AS margin_pct,
    ROUND(SUM(fs.net_amount) / NULLIF(COUNT(DISTINCT fs.order_id), 0), 2) AS aov
FROM dw.fact_sales     fs
JOIN dw.dim_date       dd ON fs.date_key    = dd.date_key
JOIN dw.dim_store      ds ON fs.store_key   = ds.store_key
JOIN dw.dim_channel    dc ON fs.channel_key = dc.channel_key
GROUP BY 1,2,3,4,5,6,7,8,9;


-- ── rpt_sales_monthly_region_category (Materialized) ────────
CREATE MATERIALIZED VIEW IF NOT EXISTS rpt.rpt_sales_monthly_region_category AS
SELECT
    dd.year,
    dd.month,
    dd.month_name,
    dd.quarter,
    ds.region,
    dp.category,
    dp.subcategory,
    COUNT(DISTINCT fs.order_id)                     AS orders,
    SUM(fs.quantity)                                AS units_sold,
    SUM(fs.gross_amount)                            AS gross_revenue,
    SUM(fs.net_amount)                              AS net_revenue,
    SUM(fs.profit_amount)                           AS gross_profit,
    ROUND(SUM(fs.profit_amount) / NULLIF(SUM(fs.net_amount), 0) * 100, 2) AS margin_pct
FROM dw.fact_sales    fs
JOIN dw.dim_date      dd ON fs.date_key    = dd.date_key
JOIN dw.dim_store     ds ON fs.store_key   = ds.store_key
JOIN dw.dim_product   dp ON fs.product_key = dp.product_key AND dp.is_current
GROUP BY 1,2,3,4,5,6,7
WITH NO DATA;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_sales_monthly
    ON rpt.rpt_sales_monthly_region_category(year, month, region, category, subcategory);


-- ── rpt_profitability_product ───────────────────────────────
CREATE OR REPLACE VIEW rpt.rpt_profitability_product AS
SELECT
    dp.product_id,
    dp.name        AS product_name,
    dp.category,
    dp.subcategory,
    dp.brand,
    SUM(fs.gross_amount)                            AS gross_revenue,
    SUM(fs.net_amount)                              AS net_revenue,
    SUM(fs.cost_amount)                             AS total_cost,
    SUM(fs.profit_amount)                           AS gross_profit,
    ROUND(SUM(fs.profit_amount) / NULLIF(SUM(fs.net_amount), 0) * 100, 2) AS margin_pct,
    SUM(fs.quantity)                                AS units_sold,
    RANK() OVER (ORDER BY SUM(fs.profit_amount) DESC) AS profit_rank
FROM dw.fact_sales  fs
JOIN dw.dim_product dp ON fs.product_key = dp.product_key AND dp.is_current
GROUP BY 1,2,3,4,5;


-- ── rpt_inventory_health ────────────────────────────────────
CREATE OR REPLACE VIEW rpt.rpt_inventory_health AS
WITH latest_snap AS (
    SELECT DISTINCT ON (product_key, store_key)
        product_key, store_key,
        snapshot_date_key, on_hand, reserved, available, reorder_level, lead_time_days
    FROM dw.fact_inventory_snapshot
    ORDER BY product_key, store_key, snapshot_date_key DESC
),
avg_daily_sales AS (
    SELECT
        fs.product_key,
        fs.store_key,
        SUM(fs.quantity)::FLOAT / 30 AS avg_daily_units
    FROM dw.fact_sales fs
    JOIN dw.dim_date   dd ON fs.date_key = dd.date_key
    WHERE dd.date >= CURRENT_DATE - INTERVAL '30 days'
    GROUP BY 1, 2
)
SELECT
    dp.product_id,
    dp.name       AS product_name,
    dp.category,
    ds.store_id,
    ds.store_name,
    ds.region,
    ls.on_hand,
    ls.reserved,
    ls.available,
    ls.reorder_level,
    ls.lead_time_days,
    ROUND((ls.available / NULLIF(ads.avg_daily_units, 0))::NUMERIC, 1) AS days_of_cover,
    (ls.available = 0 AND COALESCE(ads.avg_daily_units, 0) > 0)         AS is_stockout,
    (ls.available / NULLIF(ads.avg_daily_units, 0) > 90)                AS is_overstock,
    -- Dead stock: on_hand > 0 but no sales in 90 days
    (ls.on_hand > 0 AND COALESCE(ads.avg_daily_units, 0) = 0)           AS is_dead_stock
FROM latest_snap       ls
JOIN dw.dim_product    dp  ON ls.product_key = dp.product_key AND dp.is_current
JOIN dw.dim_store      ds  ON ls.store_key   = ds.store_key
LEFT JOIN avg_daily_sales ads ON ls.product_key = ads.product_key AND ls.store_key = ads.store_key;


-- ── rpt_customer_rfm ────────────────────────────────────────
CREATE OR REPLACE VIEW rpt.rpt_customer_rfm AS
WITH rfm_base AS (
    SELECT
        dc.customer_key,
        dc.customer_id,
        dc.name         AS customer_name,
        dc.region,
        dc.segment,
        MAX(dd.date)                                AS last_order_date,
        COUNT(DISTINCT fs.order_id)                 AS frequency,
        SUM(fs.net_amount)                          AS monetary
    FROM dw.fact_sales   fs
    JOIN dw.dim_customer dc ON fs.customer_key = dc.customer_key AND dc.is_current
    JOIN dw.dim_date     dd ON fs.date_key     = dd.date_key
    GROUP BY 1,2,3,4,5
),
rfm_scores AS (
    SELECT *,
        CURRENT_DATE - last_order_date::DATE        AS recency_days,
        NTILE(5) OVER (ORDER BY CURRENT_DATE - last_order_date::DATE DESC) AS r_score,
        NTILE(5) OVER (ORDER BY frequency)          AS f_score,
        NTILE(5) OVER (ORDER BY monetary)           AS m_score
    FROM rfm_base
)
SELECT *,
    CASE
        WHEN r_score >= 4 AND f_score >= 4 THEN 'Champions'
        WHEN r_score >= 3 AND f_score >= 3 THEN 'Loyal'
        WHEN r_score >= 4 AND f_score <= 2 THEN 'Recent'
        WHEN r_score <= 2 AND f_score >= 3 THEN 'At Risk'
        WHEN r_score <= 2 AND f_score <= 2 THEN 'Lost'
        ELSE 'Potential'
    END AS rfm_segment,
    -- CLV (simple): AOV x frequency x 3 (expected years)
    ROUND((monetary / NULLIF(frequency, 0)) * frequency * 3, 2) AS clv_simple
FROM rfm_scores;


-- ── rpt_customer_cohorts ────────────────────────────────────
CREATE OR REPLACE VIEW rpt.rpt_customer_cohorts AS
WITH cohort_base AS (
    SELECT
        dc.customer_id,
        DATE_TRUNC('month', dc.signup_date)::DATE           AS cohort_month,
        DATE_TRUNC('month', dd.date)::DATE                  AS order_month
    FROM dw.fact_sales   fs
    JOIN dw.dim_customer dc ON fs.customer_key = dc.customer_key AND dc.is_current
    JOIN dw.dim_date     dd ON fs.date_key     = dd.date_key
),
cohort_sizes AS (
    SELECT cohort_month, COUNT(DISTINCT customer_id) AS cohort_size
    FROM cohort_base GROUP BY 1
),
cohort_activity AS (
    SELECT
        cohort_month,
        EXTRACT(YEAR FROM AGE(order_month, cohort_month)) * 12 +
        EXTRACT(MONTH FROM AGE(order_month, cohort_month)) AS months_since,
        COUNT(DISTINCT customer_id) AS active_customers
    FROM cohort_base GROUP BY 1, 2
)
SELECT
    ca.cohort_month,
    ca.months_since,
    cs.cohort_size,
    ca.active_customers,
    ROUND(ca.active_customers::NUMERIC / NULLIF(cs.cohort_size, 0) * 100, 2) AS retention_pct
FROM cohort_activity  ca
JOIN cohort_sizes     cs ON ca.cohort_month = cs.cohort_month
ORDER BY 1, 2;


-- ── rpt_returns_analysis ────────────────────────────────────
-- Note: returns do not carry a store_key; region is derived
--       from the originating order via a subquery join.
CREATE OR REPLACE VIEW rpt.rpt_returns_analysis AS
WITH sales_by_product AS (
    SELECT product_key, SUM(quantity) AS units_sold
    FROM dw.fact_sales GROUP BY 1
),
return_region AS (
    -- Map each return to the region of the store where the order was placed
    SELECT DISTINCT ON (fr.return_key)
        fr.return_key,
        ds.region
    FROM dw.fact_returns  fr
    JOIN dw.fact_sales    fs ON fr.order_id     = fs.order_id
    JOIN dw.dim_store     ds ON fs.store_key    = ds.store_key
    ORDER BY fr.return_key, ds.region
)
SELECT
    dp.product_id,
    dp.name             AS product_name,
    dp.category,
    rr.region,
    drr.reason_name     AS return_reason,
    drr.reason_group,
    COUNT(fr.return_key)    AS return_count,
    SUM(fr.refund_amount)   AS total_refund,
    sbp.units_sold,
    ROUND(
        COUNT(fr.return_key)::NUMERIC / NULLIF(sbp.units_sold, 0) * 100, 2
    ) AS return_rate_pct
FROM dw.fact_returns        fr
JOIN dw.dim_product         dp  ON fr.product_key = dp.product_key AND dp.is_current
JOIN dw.dim_return_reason   drr ON fr.reason_key  = drr.reason_key
LEFT JOIN return_region     rr  ON fr.return_key  = rr.return_key
LEFT JOIN sales_by_product  sbp ON fr.product_key = sbp.product_key
GROUP BY 1,2,3,4,5,6, sbp.units_sold;


-- ── rpt_opportunities ───────────────────────────────────────
CREATE OR REPLACE VIEW rpt.rpt_opportunities AS
-- Rising categories (MoM revenue growth > 10%)
WITH cat_growth AS (
    SELECT
        category,
        SUM(CASE WHEN year = EXTRACT(YEAR FROM CURRENT_DATE) AND month = EXTRACT(MONTH FROM CURRENT_DATE) - 1
                 THEN net_revenue ELSE 0 END) AS prev_month_revenue,
        SUM(CASE WHEN year = EXTRACT(YEAR FROM CURRENT_DATE) AND month = EXTRACT(MONTH FROM CURRENT_DATE)
                 THEN net_revenue ELSE 0 END) AS curr_month_revenue
    FROM rpt.rpt_sales_monthly_region_category
    GROUP BY 1
),
-- Reorder candidates
reorder AS (
    SELECT product_id, product_name, category, store_id, store_name, region,
           available, reorder_level, days_of_cover, lead_time_days
    FROM rpt.rpt_inventory_health
    WHERE available <= reorder_level AND is_stockout = FALSE
),
-- Churn risk: high-value customers (top 20% CLV), no purchase in 90 days
churn_risk AS (
    SELECT customer_id, customer_name, region, segment,
           recency_days, monetary, rfm_segment, clv_simple
    FROM rpt.rpt_customer_rfm
    WHERE recency_days > 90
      AND m_score >= 4
)
SELECT 'rising_category' AS opportunity_type,
       category AS entity_name,
       NULL AS customer_id,
       NULL AS product_id,
       NULL AS store_id,
       ROUND(curr_month_revenue - prev_month_revenue, 2) AS value,
       'MoM revenue growth' AS metric_label,
       NULL AS region
FROM cat_growth WHERE prev_month_revenue > 0
  AND (curr_month_revenue - prev_month_revenue) / prev_month_revenue > 0.10

UNION ALL

SELECT 'reorder_risk',
       product_name,
       NULL, product_id, store_id,
       available::NUMERIC,
       'available units',
       region
FROM reorder

UNION ALL

SELECT 'churn_risk_high_value',
       customer_name,
       customer_id, NULL, NULL,
       clv_simple,
       'CLV (simple)',
       region
FROM churn_risk;
