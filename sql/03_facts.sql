-- ============================================================
-- 03_facts.sql  –  Fact tables
-- ============================================================

-- ── fact_sales ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dw.fact_sales (
    sales_key           BIGSERIAL,
    line_id             TEXT NOT NULL,
    order_id            TEXT NOT NULL,
    date_key            INT  NOT NULL REFERENCES dw.dim_date(date_key),
    customer_key        BIGINT REFERENCES dw.dim_customer(customer_key),
    product_key         BIGINT REFERENCES dw.dim_product(product_key),
    store_key           BIGINT REFERENCES dw.dim_store(store_key),
    channel_key         SMALLINT REFERENCES dw.dim_channel(channel_key),
    -- Measures
    quantity            INT    NOT NULL,
    unit_price          NUMERIC(12,2) NOT NULL,
    unit_cost           NUMERIC(12,2),
    discount_rate       NUMERIC(5,4)  DEFAULT 0,
    gross_amount        NUMERIC(14,2) NOT NULL,
    discount_amount     NUMERIC(14,2) NOT NULL DEFAULT 0,
    net_amount          NUMERIC(14,2) NOT NULL,
    cost_amount         NUMERIC(14,2),
    profit_amount       NUMERIC(14,2),
    -- Constraints
    CONSTRAINT chk_sales_qty    CHECK (quantity > 0),
    CONSTRAINT chk_sales_net    CHECK (net_amount >= 0),
    CONSTRAINT chk_sales_gross  CHECK (gross_amount >= 0),
    -- ETL metadata
    _etl_run_id         TEXT,
    PRIMARY KEY (sales_key, date_key),
    CONSTRAINT uq_sales_line UNIQUE (line_id, date_key)
) PARTITION BY RANGE (date_key);

CREATE TABLE IF NOT EXISTS dw.fact_sales_default PARTITION OF dw.fact_sales DEFAULT;

-- Monthly partitions for 2023-2026
DO $$
DECLARE
    yr INT;
    mo INT;
    part_name TEXT;
    start_key INT;
    end_key INT;
BEGIN
    FOR yr IN 2023..2026 LOOP
        FOR mo IN 1..12 LOOP
            part_name := FORMAT('fact_sales_%s_%s', yr, LPAD(mo::TEXT, 2, '0'));
            start_key := yr * 10000 + mo * 100 + 1;
            end_key   := CASE WHEN mo < 12 THEN yr * 10000 + (mo+1) * 100 + 1
                              ELSE (yr+1) * 10000 + 0101 END;
            -- Simplified: partition by month range on date_key YYYYMMDD
            EXECUTE FORMAT(
                'CREATE TABLE IF NOT EXISTS dw.%I PARTITION OF dw.fact_sales
                 FOR VALUES FROM (%L) TO (%L)',
                part_name,
                yr * 10000 + mo * 100,
                CASE WHEN mo < 12
                     THEN yr * 10000 + (mo+1) * 100
                     ELSE (yr+1) * 10000 + 100
                END
            );
        END LOOP;
    END LOOP;
END $$;


-- ── fact_returns ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dw.fact_returns (
    return_key          BIGSERIAL PRIMARY KEY,
    return_id           TEXT NOT NULL UNIQUE,
    order_id            TEXT NOT NULL,
    return_date_key     INT  REFERENCES dw.dim_date(date_key),
    product_key         BIGINT REFERENCES dw.dim_product(product_key),
    reason_key          SMALLINT REFERENCES dw.dim_return_reason(reason_key),
    -- Measures
    returned_qty        INT    NOT NULL DEFAULT 1,
    refund_amount       NUMERIC(14,2),
    CONSTRAINT chk_return_qty CHECK (returned_qty > 0),
    -- ETL metadata
    _etl_run_id         TEXT
);


-- ── fact_inventory_snapshot ─────────────────────────────────
CREATE TABLE IF NOT EXISTS dw.fact_inventory_snapshot (
    snapshot_key        BIGSERIAL PRIMARY KEY,
    snapshot_date_key   INT  NOT NULL REFERENCES dw.dim_date(date_key),
    product_key         BIGINT NOT NULL REFERENCES dw.dim_product(product_key),
    store_key           BIGINT NOT NULL REFERENCES dw.dim_store(store_key),
    -- Measures
    on_hand             INT NOT NULL DEFAULT 0,
    reserved            INT NOT NULL DEFAULT 0,
    available           INT NOT NULL DEFAULT 0,
    reorder_level       INT,
    lead_time_days      INT,
    CONSTRAINT chk_inv_onhand    CHECK (on_hand >= 0),
    CONSTRAINT chk_inv_reserved  CHECK (reserved >= 0),
    CONSTRAINT chk_inv_available CHECK (available >= 0),
    CONSTRAINT uq_inv_snapshot UNIQUE (snapshot_date_key, product_key, store_key),
    -- ETL metadata
    _etl_run_id         TEXT
);

-- Staging tables (ETL loads here or directly)
CREATE TABLE IF NOT EXISTS dw.fact_sales_staging              (LIKE dw.fact_sales INCLUDING DEFAULTS EXCLUDING CONSTRAINTS);
CREATE TABLE IF NOT EXISTS dw.fact_returns_staging            (LIKE dw.fact_returns INCLUDING DEFAULTS EXCLUDING CONSTRAINTS);
CREATE TABLE IF NOT EXISTS dw.fact_inventory_snapshot_staging (LIKE dw.fact_inventory_snapshot INCLUDING DEFAULTS EXCLUDING CONSTRAINTS);

