-- ============================================================
-- 07_week3_enhancements.sql
-- Week 3 additions:
--   1. rpt_executive_summary   – pre-aggregated KPI view for dashboard
--   2. rpt_discount_impact     – discount band vs margin analysis
--   3. rpt_inventory_turnover  – turnover by category
--   4. rpt_new_vs_returning    – new vs returning customers per period
--   5. rpt_dq_scorecard        – self-serve DQ scorecard for BI
--   6. SCD2 upgrade helpers    – current-record shortcuts
-- ============================================================

-- ── 1. Executive KPI summary view ───────────────────────────────────────────
CREATE OR REPLACE VIEW rpt.rpt_executive_summary AS
WITH base AS (
    SELECT
        dd.year,
        dd.month,
        dd.quarter,
        SUM(fs.gross_amount)                            AS gross_revenue,
        SUM(fs.net_amount)                              AS net_revenue,
        SUM(fs.cost_amount)                             AS total_cost,
        SUM(fs.profit_amount)                           AS gross_profit,
        SUM(fs.discount_amount)                         AS total_discount,
        SUM(fs.quantity)                                AS units_sold,
        COUNT(DISTINCT fs.order_id)                     AS total_orders,
        COUNT(DISTINCT fs.customer_key)                 AS active_customers
    FROM dw.fact_sales  fs
    JOIN dw.dim_date    dd ON fs.date_key = dd.date_key
    GROUP BY 1, 2, 3
),
returns_base AS (
    SELECT
        dd.year, dd.month,
        SUM(fr.returned_qty)   AS returned_units,
        SUM(fr.refund_amount)  AS total_refund
    FROM dw.fact_returns fr
    JOIN dw.dim_date     dd ON fr.return_date_key = dd.date_key
    GROUP BY 1, 2
)
SELECT
    b.year, b.month, b.quarter,
    b.gross_revenue,
    b.net_revenue,
    b.gross_profit,
    b.total_cost,
    b.total_discount,
    b.units_sold,
    b.total_orders,
    b.active_customers,
    ROUND(b.gross_profit / NULLIF(b.net_revenue, 0) * 100, 2)          AS margin_pct,
    ROUND(b.net_revenue / NULLIF(b.total_orders, 0), 2)                AS aov,
    COALESCE(rb.returned_units, 0)                                      AS returned_units,
    ROUND(COALESCE(rb.returned_units, 0)::NUMERIC
          / NULLIF(b.units_sold, 0) * 100, 2)                          AS return_rate_pct
FROM base b
LEFT JOIN returns_base rb ON b.year = rb.year AND b.month = rb.month
ORDER BY b.year, b.month;


-- ── 2. Discount impact analysis ──────────────────────────────────────────────
CREATE OR REPLACE VIEW rpt.rpt_discount_impact AS
WITH discount_classified AS (
    SELECT
        fs.order_id,
        fs.quantity,
        fs.gross_amount,
        fs.discount_amount,
        fs.net_amount,
        fs.profit_amount,
        dp.category,
        CASE
            WHEN fs.discount_amount = 0                                          THEN '0% (No Discount)'
            WHEN fs.discount_amount / NULLIF(fs.gross_amount, 0) <= 0.05        THEN '1–5%'
            WHEN fs.discount_amount / NULLIF(fs.gross_amount, 0) <= 0.10        THEN '6–10%'
            WHEN fs.discount_amount / NULLIF(fs.gross_amount, 0) <= 0.20        THEN '11–20%'
            WHEN fs.discount_amount / NULLIF(fs.gross_amount, 0) <= 0.30        THEN '21–30%'
            ELSE '30%+'
        END AS discount_band
    FROM dw.fact_sales   fs
    JOIN dw.dim_product  dp ON fs.product_key = dp.product_key AND dp.is_current
)
SELECT
    discount_band,
    category,
    COUNT(DISTINCT order_id)                                    AS orders,
    SUM(quantity)                                               AS units_sold,
    SUM(gross_amount)                                           AS gross_revenue,
    SUM(discount_amount)                                        AS total_discount,
    SUM(net_amount)                                             AS net_revenue,
    SUM(profit_amount)                                          AS gross_profit,
    ROUND(SUM(profit_amount) / NULLIF(SUM(net_amount), 0) * 100, 2) AS margin_pct
FROM discount_classified
GROUP BY 1, 2;


-- ── 3. Inventory turnover by category ────────────────────────────────────────
CREATE OR REPLACE VIEW rpt.rpt_inventory_turnover AS
WITH cogs AS (
    SELECT dp.category,
           SUM(fs.cost_amount) AS total_cogs
    FROM dw.fact_sales   fs
    JOIN dw.dim_product  dp ON fs.product_key = dp.product_key AND dp.is_current
    GROUP BY 1
),
avg_inv AS (
    SELECT dp.category,
           ROUND(AVG(fis.on_hand * dp.cost), 2) AS avg_inventory_value
    FROM dw.fact_inventory_snapshot  fis
    JOIN dw.dim_product              dp ON fis.product_key = dp.product_key AND dp.is_current
    GROUP BY 1
)
SELECT
    c.category,
    ROUND(c.total_cogs, 2)                                    AS total_cogs,
    ROUND(i.avg_inventory_value, 2)                           AS avg_inventory_value,
    ROUND(c.total_cogs / NULLIF(i.avg_inventory_value, 0), 2) AS inventory_turnover_ratio,
    ROUND(365.0 / NULLIF(c.total_cogs / NULLIF(i.avg_inventory_value, 0), 0), 1)
                                                               AS days_to_sell
FROM cogs c
JOIN avg_inv i USING (category)
ORDER BY inventory_turnover_ratio DESC;


-- ── 4. New vs returning customers by period ──────────────────────────────────
CREATE OR REPLACE VIEW rpt.rpt_new_vs_returning AS
WITH first_order AS (
    SELECT customer_key,
           MIN(date_key) AS first_order_date_key
    FROM dw.fact_sales
    GROUP BY 1
),
classified AS (
    SELECT
        fs.customer_key,
        dd.year,
        dd.month,
        dd.quarter,
        CASE
            WHEN fo.first_order_date_key = fs.date_key THEN 'New'
            ELSE 'Returning'
        END AS customer_type
    FROM dw.fact_sales   fs
    JOIN dw.dim_date     dd ON fs.date_key = dd.date_key
    JOIN first_order     fo ON fs.customer_key = fo.customer_key
)
SELECT
    year, month, quarter, customer_type,
    COUNT(DISTINCT customer_key) AS customers
FROM classified
GROUP BY 1, 2, 3, 4
ORDER BY 1, 2, 4;


-- ── 5. DQ Scorecard view ──────────────────────────────────────────────────────
-- Exposes the latest run's DQ results for direct BI consumption
CREATE OR REPLACE VIEW rpt.rpt_dq_scorecard AS
SELECT
    rl.run_id,
    rl.started_at                                               AS run_started,
    rl.status                                                   AS run_status,
    rl.rows_read,
    rl.rows_loaded,
    rl.rows_rejected,
    ROUND(rl.rows_rejected::NUMERIC / NULLIF(rl.rows_read, 0) * 100, 2) AS reject_rate_pct,
    dr.table_name,
    dr.rule_name,
    dr.failed_count,
    dr.total_count,
    ROUND(dr.failed_count::NUMERIC / NULLIF(dr.total_count, 0) * 100, 2) AS fail_pct,
    dr.severity
FROM ops.etl_run_log rl
LEFT JOIN ops.dq_results dr ON rl.run_id = dr.run_id
WHERE rl.run_id = (SELECT MAX(run_id) FROM ops.etl_run_log)
ORDER BY dr.severity DESC, fail_pct DESC;


-- ── 6. SCD2 helpers: current-dimension shortcut views ────────────────────────
-- These views expose only is_current=TRUE rows for simple joins
-- (avoids repeating the AND dp.is_current predicate everywhere)

CREATE OR REPLACE VIEW dw.dim_product_current AS
SELECT * FROM dw.dim_product WHERE is_current = TRUE;

CREATE OR REPLACE VIEW dw.dim_customer_current AS
SELECT * FROM dw.dim_customer WHERE is_current = TRUE;

-- Grant bi_reader/ai_reader access to the new rpt views
GRANT SELECT ON rpt.rpt_executive_summary    TO bi_reader, ai_reader;
GRANT SELECT ON rpt.rpt_discount_impact      TO bi_reader, ai_reader;
GRANT SELECT ON rpt.rpt_inventory_turnover   TO bi_reader, ai_reader;
GRANT SELECT ON rpt.rpt_new_vs_returning     TO bi_reader, ai_reader;
GRANT SELECT ON rpt.rpt_dq_scorecard         TO bi_reader, ai_reader;
GRANT SELECT ON dw.dim_product_current       TO bi_reader, ai_reader;
GRANT SELECT ON dw.dim_customer_current      TO bi_reader, ai_reader;
