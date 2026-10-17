-- ============================================================
-- 04_indexes.sql  –  Performance indexes
-- ============================================================

-- ── fact_sales ──────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_fact_sales_date_key      ON dw.fact_sales(date_key);
CREATE INDEX IF NOT EXISTS idx_fact_sales_product_key   ON dw.fact_sales(product_key);
CREATE INDEX IF NOT EXISTS idx_fact_sales_store_key     ON dw.fact_sales(store_key);
CREATE INDEX IF NOT EXISTS idx_fact_sales_customer_key  ON dw.fact_sales(customer_key);
CREATE INDEX IF NOT EXISTS idx_fact_sales_channel_key   ON dw.fact_sales(channel_key);
CREATE INDEX IF NOT EXISTS idx_fact_sales_order_id      ON dw.fact_sales(order_id);
-- Composite for regional time-series queries
CREATE INDEX IF NOT EXISTS idx_fact_sales_date_store    ON dw.fact_sales(date_key, store_key);
CREATE INDEX IF NOT EXISTS idx_fact_sales_date_product  ON dw.fact_sales(date_key, product_key);

-- ── fact_returns ────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_fact_returns_date_key    ON dw.fact_returns(return_date_key);
CREATE INDEX IF NOT EXISTS idx_fact_returns_product_key ON dw.fact_returns(product_key);
CREATE INDEX IF NOT EXISTS idx_fact_returns_reason_key  ON dw.fact_returns(reason_key);
CREATE INDEX IF NOT EXISTS idx_fact_returns_order_id    ON dw.fact_returns(order_id);

-- ── fact_inventory_snapshot ─────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_inv_snap_date_key        ON dw.fact_inventory_snapshot(snapshot_date_key);
CREATE INDEX IF NOT EXISTS idx_inv_snap_product_key     ON dw.fact_inventory_snapshot(product_key);
CREATE INDEX IF NOT EXISTS idx_inv_snap_store_key       ON dw.fact_inventory_snapshot(store_key);

-- ── dim tables ──────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_dim_customer_region      ON dw.dim_customer(region);
CREATE INDEX IF NOT EXISTS idx_dim_customer_segment     ON dw.dim_customer(segment);
CREATE INDEX IF NOT EXISTS idx_dim_product_category     ON dw.dim_product(category);
CREATE INDEX IF NOT EXISTS idx_dim_product_brand        ON dw.dim_product(brand);
CREATE INDEX IF NOT EXISTS idx_dim_store_region         ON dw.dim_store(region);
CREATE INDEX IF NOT EXISTS idx_dim_date_year_month      ON dw.dim_date(year, month);
CREATE INDEX IF NOT EXISTS idx_dim_date_quarter         ON dw.dim_date(year, quarter);
