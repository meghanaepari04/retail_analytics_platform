-- ============================================================
-- dashboard_validation.sql
-- Week 3 — PRD §14: Dashboard Validation
-- Validates that dashboard totals match SQL totals for
-- 10 representative slices (required by PRD).
-- Run after every ETL cycle; all queries should return
-- result_match = TRUE.
-- ============================================================

-- SLICE 1: Total net revenue across all time
SELECT
    'Total Net Revenue' AS check_name,
    SUM(net_amount) AS warehouse_total,
    (SELECT SUM(net_revenue) FROM rpt.rpt_sales_daily) AS view_total,
    ABS(SUM(net_amount) - (SELECT SUM(net_revenue) FROM rpt.rpt_sales_daily)) < 0.01 AS result_match
FROM dw.fact_sales;


-- SLICE 2: Total orders count
SELECT
    'Total Orders' AS check_name,
    COUNT(DISTINCT order_id) AS warehouse_count,
    (SELECT SUM(orders) FROM rpt.rpt_sales_daily) AS view_total,
    COUNT(DISTINCT order_id) = (SELECT SUM(orders) FROM rpt.rpt_sales_daily) AS result_match
FROM dw.fact_sales;


-- SLICE 3: Revenue for North region in 2025
SELECT
    'North Region 2025 Revenue' AS check_name,
    SUM(fs.net_amount) AS warehouse_total,
    (
        SELECT SUM(net_revenue) FROM rpt.rpt_sales_monthly_region_category
        WHERE region = 'North' AND year = 2025
    ) AS view_total,
    ABS(SUM(fs.net_amount) -
        (SELECT COALESCE(SUM(net_revenue),0)
         FROM rpt.rpt_sales_monthly_region_category
         WHERE region = 'North' AND year = 2025)
    ) < 0.01 AS result_match
FROM dw.fact_sales     fs
JOIN dw.dim_date       dd ON fs.date_key = dd.date_key
JOIN dw.dim_store      ds ON fs.store_key = ds.store_key
WHERE ds.region = 'North' AND dd.year = 2025;


-- SLICE 4: Total gross profit (warehouse vs profitability view)
SELECT
    'Total Gross Profit' AS check_name,
    SUM(profit_amount) AS warehouse_total,
    (SELECT SUM(gross_profit) FROM rpt.rpt_profitability_product) AS view_total,
    ABS(SUM(profit_amount) -
        (SELECT SUM(gross_profit) FROM rpt.rpt_profitability_product)
    ) < 0.01 AS result_match
FROM dw.fact_sales;


-- SLICE 5: Total returns count (resolved products in rpt view)
SELECT
    'Total Returns (Resolved Products)' AS check_name,
    COUNT(*) AS warehouse_count,
    (SELECT SUM(return_count) FROM rpt.rpt_returns_analysis) AS view_total,
    COUNT(*) = (SELECT SUM(return_count) FROM rpt.rpt_returns_analysis) AS result_match
FROM dw.fact_returns
WHERE product_key IS NOT NULL;


-- SLICE 6: Total refund amount (resolved products in rpt view)
SELECT
    'Total Refund Amount (Resolved Products)' AS check_name,
    SUM(refund_amount) AS warehouse_total,
    (SELECT SUM(total_refund) FROM rpt.rpt_returns_analysis) AS view_total,
    ABS(SUM(refund_amount) -
        (SELECT COALESCE(SUM(total_refund), 0) FROM rpt.rpt_returns_analysis)
    ) < 0.01 AS result_match
FROM dw.fact_returns
WHERE product_key IS NOT NULL;


-- SLICE 7: Customer count in RFM view matches distinct customers in fact_sales
SELECT
    'RFM Customer Count vs Fact' AS check_name,
    (SELECT COUNT(DISTINCT customer_key) FROM dw.fact_sales) AS warehouse_distinct,
    (SELECT COUNT(*) FROM rpt.rpt_customer_rfm) AS view_count,
    (SELECT COUNT(DISTINCT customer_key) FROM dw.fact_sales)
      = (SELECT COUNT(*) FROM rpt.rpt_customer_rfm) AS result_match;


-- SLICE 8: Margin % cross-check for Electronics category
SELECT
    'Electronics Margin % Cross-Check' AS check_name,
    ROUND(SUM(fs.profit_amount) / NULLIF(SUM(fs.net_amount), 0) * 100, 2) AS warehouse_margin,
    (
        SELECT ROUND(SUM(gross_profit) / NULLIF(SUM(net_revenue), 0) * 100, 2)
        FROM rpt.rpt_profitability_product
        WHERE category = 'Electronics'
    ) AS view_margin,
    ABS(
        SUM(fs.profit_amount) / NULLIF(SUM(fs.net_amount), 0) -
        (
            SELECT SUM(gross_profit) / NULLIF(SUM(net_revenue), 0)
            FROM rpt.rpt_profitability_product
            WHERE category = 'Electronics'
        )
    ) < 0.001 AS result_match
FROM dw.fact_sales     fs
JOIN dw.dim_product    dp ON fs.product_key = dp.product_key AND dp.is_current
WHERE dp.category = 'Electronics';


-- SLICE 9: Units sold in fact vs daily view (same period)
SELECT
    'Units Sold Reconciliation (2025)' AS check_name,
    SUM(fs.quantity) AS warehouse_units,
    (
        SELECT SUM(units_sold) FROM rpt.rpt_sales_daily
        WHERE year = 2025
    ) AS view_units,
    SUM(fs.quantity) = (
        SELECT COALESCE(SUM(units_sold), 0) FROM rpt.rpt_sales_daily WHERE year = 2025
    ) AS result_match
FROM dw.fact_sales  fs
JOIN dw.dim_date    dd ON fs.date_key = dd.date_key
WHERE dd.year = 2025;


-- SLICE 10: SCD2 integrity — exactly one current row per customer_id
SELECT
    'SCD2 Customer Integrity' AS check_name,
    COUNT(*) AS violations,
    COUNT(*) = 0 AS result_match
FROM (
    SELECT customer_id, COUNT(*) AS current_count
    FROM dw.dim_customer
    WHERE is_current = TRUE
    GROUP BY 1
    HAVING COUNT(*) > 1
) dupes;


-- ── Summary: All 10 Reconciliation Slices
SELECT check_name, result_match FROM (
    -- SLICE 1
    SELECT '1. Total Net Revenue' AS check_name,
           ABS(SUM(net_amount) - (SELECT SUM(net_revenue) FROM rpt.rpt_sales_daily)) < 0.01 AS result_match
    FROM dw.fact_sales
    UNION ALL
    -- SLICE 2
    SELECT '2. Total Orders',
           COUNT(DISTINCT order_id) = (SELECT SUM(orders) FROM rpt.rpt_sales_daily)
    FROM dw.fact_sales
    UNION ALL
    -- SLICE 3
    SELECT '3. North Region 2025 Revenue',
           ABS(SUM(fs.net_amount) -
               (SELECT COALESCE(SUM(net_revenue),0)
                FROM rpt.rpt_sales_monthly_region_category
                WHERE region = 'North' AND year = 2025)
           ) < 0.01
    FROM dw.fact_sales fs
    JOIN dw.dim_date dd ON fs.date_key = dd.date_key
    JOIN dw.dim_store ds ON fs.store_key = ds.store_key
    WHERE ds.region = 'North' AND dd.year = 2025
    UNION ALL
    -- SLICE 4
    SELECT '4. Total Gross Profit',
           ABS(SUM(profit_amount) - (SELECT SUM(gross_profit) FROM rpt.rpt_profitability_product)) < 0.01
    FROM dw.fact_sales
    UNION ALL
    -- SLICE 5
    SELECT '5. Total Returns (Resolved)',
           COUNT(*) = (SELECT SUM(return_count) FROM rpt.rpt_returns_analysis)
    FROM dw.fact_returns
    WHERE product_key IS NOT NULL
    UNION ALL
    -- SLICE 6
    SELECT '6. Total Refund (Resolved)',
           ABS(SUM(refund_amount) - (SELECT COALESCE(SUM(total_refund), 0) FROM rpt.rpt_returns_analysis)) < 0.01
    FROM dw.fact_returns
    WHERE product_key IS NOT NULL
    UNION ALL
    -- SLICE 7
    SELECT '7. RFM Customer Count',
           (SELECT COUNT(DISTINCT customer_key) FROM dw.fact_sales) = (SELECT COUNT(*) FROM rpt.rpt_customer_rfm)
    UNION ALL
    -- SLICE 8
    SELECT '8. Category Margin %',
           ABS(
               (SELECT SUM(profit_amount) / NULLIF(SUM(net_amount), 0) FROM dw.fact_sales fs JOIN dw.dim_product dp ON fs.product_key = dp.product_key AND dp.is_current WHERE dp.category = 'Electronics') -
               (SELECT SUM(gross_profit) / NULLIF(SUM(net_revenue), 0) FROM rpt.rpt_profitability_product WHERE category = 'Electronics')
           ) < 0.001
    UNION ALL
    -- SLICE 9
    SELECT '9. Units Sold Reconciliation',
           (SELECT SUM(quantity) FROM dw.fact_sales fs JOIN dw.dim_date dd ON fs.date_key = dd.date_key WHERE dd.year = 2025) =
           (SELECT COALESCE(SUM(units_sold), 0) FROM rpt.rpt_sales_daily WHERE year = 2025)
    UNION ALL
    -- SLICE 10
    SELECT '10. SCD2 Customer Integrity',
           NOT EXISTS (
               SELECT 1 FROM dw.dim_customer WHERE is_current GROUP BY customer_id HAVING COUNT(*) > 1
           )
) summary_checks
ORDER BY check_name;
