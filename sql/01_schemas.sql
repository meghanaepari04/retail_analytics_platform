-- ============================================================
-- 01_schemas.sql  –  Schema and ops table creation
-- ============================================================

CREATE SCHEMA IF NOT EXISTS stg;
CREATE SCHEMA IF NOT EXISTS dw;
CREATE SCHEMA IF NOT EXISTS rpt;
CREATE SCHEMA IF NOT EXISTS ops;

-- ETL run log
CREATE TABLE IF NOT EXISTS ops.etl_run_log (
    run_id          TEXT PRIMARY KEY,
    run_date        DATE,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at     TIMESTAMPTZ,
    status          TEXT NOT NULL DEFAULT 'RUNNING',
    rows_read       BIGINT DEFAULT 0,
    rows_loaded     BIGINT DEFAULT 0,
    rows_rejected   BIGINT DEFAULT 0,
    error_message   TEXT
);

-- Data quality results
CREATE TABLE IF NOT EXISTS ops.dq_results (
    id              BIGSERIAL PRIMARY KEY,
    run_id          TEXT NOT NULL REFERENCES ops.etl_run_log(run_id),
    table_name      TEXT NOT NULL,
    rule_name       TEXT NOT NULL,
    failed_count    BIGINT NOT NULL DEFAULT 0,
    total_count     BIGINT NOT NULL DEFAULT 0,
    severity        TEXT NOT NULL DEFAULT 'INFO',  -- INFO | WARN | ERROR
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Reject records (raw payload stored as JSONB for traceability)
CREATE TABLE IF NOT EXISTS ops.reject_records (
    id              BIGSERIAL PRIMARY KEY,
    run_id          TEXT NOT NULL,
    source_table    TEXT NOT NULL,
    source_key      TEXT,
    reason_code     TEXT NOT NULL,
    raw_payload     JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_reject_records_run_id ON ops.reject_records(run_id);
CREATE INDEX IF NOT EXISTS idx_reject_records_source_table ON ops.reject_records(source_table);
