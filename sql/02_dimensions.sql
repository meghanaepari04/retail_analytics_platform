-- ============================================================
-- 02_dimensions.sql  –  Star schema dimension tables
-- ============================================================

-- ── dim_date (generated calendar) ──────────────────────────
CREATE TABLE IF NOT EXISTS dw.dim_date (
    date_key        INT PRIMARY KEY,        -- YYYYMMDD
    date            DATE NOT NULL UNIQUE,
    day_of_week     SMALLINT NOT NULL,      -- 0=Sunday
    day_name        TEXT NOT NULL,
    day_of_month    SMALLINT NOT NULL,
    day_of_year     SMALLINT NOT NULL,
    week_of_year    SMALLINT NOT NULL,
    month           SMALLINT NOT NULL,
    month_name      TEXT NOT NULL,
    quarter         SMALLINT NOT NULL,
    year            SMALLINT NOT NULL,
    is_weekend      BOOLEAN NOT NULL DEFAULT FALSE,
    is_holiday      BOOLEAN NOT NULL DEFAULT FALSE,
    fiscal_quarter  SMALLINT,
    fiscal_year     SMALLINT
);

-- Populate dim_date for 2020-01-01 through 2030-12-31
INSERT INTO dw.dim_date (
    date_key, date, day_of_week, day_name, day_of_month, day_of_year,
    week_of_year, month, month_name, quarter, year, is_weekend
)
SELECT
    TO_CHAR(d, 'YYYYMMDD')::INT,
    d,
    EXTRACT(DOW FROM d)::SMALLINT,
    TO_CHAR(d, 'Day'),
    EXTRACT(DAY FROM d)::SMALLINT,
    EXTRACT(DOY FROM d)::SMALLINT,
    EXTRACT(WEEK FROM d)::SMALLINT,
    EXTRACT(MONTH FROM d)::SMALLINT,
    TO_CHAR(d, 'Month'),
    EXTRACT(QUARTER FROM d)::SMALLINT,
    EXTRACT(YEAR FROM d)::SMALLINT,
    EXTRACT(DOW FROM d) IN (0, 6)
FROM GENERATE_SERIES('2020-01-01'::DATE, '2030-12-31'::DATE, '1 day') AS t(d)
ON CONFLICT (date_key) DO NOTHING;


-- ── dim_store ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dw.dim_store (
    store_key       BIGSERIAL PRIMARY KEY,
    store_id        TEXT NOT NULL UNIQUE,
    store_name      TEXT NOT NULL,
    city            TEXT,
    region          TEXT NOT NULL,
    country         TEXT NOT NULL DEFAULT 'USA',
    _etl_run_id     TEXT,
    _updated_at     TIMESTAMPTZ
);


-- ── dim_channel ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dw.dim_channel (
    channel_key     SMALLSERIAL PRIMARY KEY,
    channel_name    TEXT NOT NULL UNIQUE
);

INSERT INTO dw.dim_channel (channel_name)
VALUES ('Online'), ('In-Store'), ('Marketplace'), ('Unknown')
ON CONFLICT (channel_name) DO NOTHING;


-- ── dim_return_reason ───────────────────────────────────────
CREATE TABLE IF NOT EXISTS dw.dim_return_reason (
    reason_key      SMALLSERIAL PRIMARY KEY,
    reason_name     TEXT NOT NULL UNIQUE,
    reason_group    TEXT
);

INSERT INTO dw.dim_return_reason (reason_name, reason_group) VALUES
    ('Defective',               'Quality'),
    ('Wrong Item',              'Fulfillment'),
    ('Changed Mind',            'Customer'),
    ('Damaged in Transit',      'Shipping'),
    ('Not as Described',        'Quality'),
    ('Better Price Found',      'Customer'),
    ('Unknown',                 'Other')
ON CONFLICT (reason_name) DO NOTHING;


-- ── dim_customer (SCD Type 2) ───────────────────────────────
CREATE TABLE IF NOT EXISTS dw.dim_customer (
    customer_key    BIGSERIAL PRIMARY KEY,
    customer_id     TEXT NOT NULL,
    name            TEXT,
    email           TEXT,               -- hashed/masked in AI-facing views
    city            TEXT,
    region          TEXT,
    segment         TEXT,
    signup_date     DATE,
    valid_from      DATE NOT NULL DEFAULT CURRENT_DATE,
    valid_to        DATE NOT NULL DEFAULT '9999-12-31',
    is_current      BOOLEAN NOT NULL DEFAULT TRUE,
    _etl_run_id     TEXT,
    CONSTRAINT uq_customer_version UNIQUE (customer_id, valid_from)
);

CREATE INDEX IF NOT EXISTS idx_dim_customer_id ON dw.dim_customer(customer_id);
CREATE INDEX IF NOT EXISTS idx_dim_customer_current ON dw.dim_customer(customer_id) WHERE is_current;


-- ── dim_product (SCD Type 2) ────────────────────────────────
CREATE TABLE IF NOT EXISTS dw.dim_product (
    product_key     BIGSERIAL PRIMARY KEY,
    product_id      TEXT NOT NULL,
    sku             TEXT,
    name            TEXT NOT NULL,
    category        TEXT NOT NULL,
    subcategory     TEXT,
    brand           TEXT,
    supplier        TEXT,
    cost            NUMERIC(12,2),
    list_price      NUMERIC(12,2),
    valid_from      DATE NOT NULL DEFAULT CURRENT_DATE,
    valid_to        DATE NOT NULL DEFAULT '9999-12-31',
    is_current      BOOLEAN NOT NULL DEFAULT TRUE,
    _etl_run_id     TEXT,
    CONSTRAINT uq_product_version UNIQUE (product_id, valid_from),
    CONSTRAINT chk_product_price CHECK (list_price IS NULL OR list_price > 0),
    CONSTRAINT chk_product_cost  CHECK (cost IS NULL OR cost >= 0)
);

CREATE INDEX IF NOT EXISTS idx_dim_product_id ON dw.dim_product(product_id);
CREATE INDEX IF NOT EXISTS idx_dim_product_current ON dw.dim_product(product_id) WHERE is_current;
CREATE INDEX IF NOT EXISTS idx_dim_product_category ON dw.dim_product(category);

-- ── Staging helpers (ETL writes here, then merges into dim tables)
CREATE TABLE IF NOT EXISTS dw.dim_customer_staging (LIKE dw.dim_customer INCLUDING DEFAULTS);
CREATE TABLE IF NOT EXISTS dw.dim_product_staging  (LIKE dw.dim_product  INCLUDING DEFAULTS);
