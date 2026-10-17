-- ============================================================
-- 06_roles.sql  –  DB role separation (PRD §7.3, §10.2)
-- ============================================================

-- ETL writer: can write to stg, dw, ops; read rpt
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'etl_writer') THEN
        CREATE ROLE etl_writer LOGIN PASSWORD 'changeme_etl';
    END IF;
END$$;

GRANT USAGE  ON SCHEMA stg, dw, ops, rpt TO etl_writer;
GRANT CREATE ON SCHEMA stg, dw, ops      TO etl_writer;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA stg TO etl_writer;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA dw  TO etl_writer;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA ops TO etl_writer;
GRANT SELECT         ON ALL TABLES IN SCHEMA rpt TO etl_writer;
GRANT USAGE, SELECT  ON ALL SEQUENCES IN SCHEMA dw  TO etl_writer;
GRANT USAGE, SELECT  ON ALL SEQUENCES IN SCHEMA ops TO etl_writer;


-- BI reader: read-only on rpt schema only
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'bi_reader') THEN
        CREATE ROLE bi_reader LOGIN PASSWORD 'changeme_bi';
    END IF;
END$$;

GRANT USAGE  ON SCHEMA rpt TO bi_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA rpt TO bi_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA rpt GRANT SELECT ON TABLES TO bi_reader;


-- AI reader: read-only on rpt schema (no PII – enforced by view definitions)
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'ai_reader') THEN
        CREATE ROLE ai_reader LOGIN PASSWORD 'changeme_ai';
    END IF;
END$$;

GRANT USAGE  ON SCHEMA rpt TO ai_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA rpt TO ai_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA rpt GRANT SELECT ON TABLES TO ai_reader;

-- Explicitly REVOKE access to any PII-containing tables for ai_reader
-- (belt-and-suspenders – the rpt views already exclude PII columns)
REVOKE ALL ON SCHEMA stg FROM ai_reader;
REVOKE ALL ON SCHEMA dw  FROM ai_reader;
REVOKE ALL ON SCHEMA ops FROM ai_reader;
