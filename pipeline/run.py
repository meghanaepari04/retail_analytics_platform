"""
ETL Pipeline Entry Point (PRD ETL-1).
Usage: python -m pipeline.run [--date YYYY-MM-DD] [--config pipeline/config.yaml]
"""
from __future__ import annotations

import argparse
import logging
import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
from sqlalchemy import text

from pipeline.db import get_engine, load_config
from pipeline.extract import extract_csv, load_to_staging
from pipeline.transform import run_transform
from pipeline.load import run_load, load_dimensions, load_facts, log_rejects

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("pipeline.run")

UTC = timezone.utc


def _log_run_start(run_id: str, run_date: str, engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS ops"))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS ops.etl_run_log (
                run_id TEXT PRIMARY KEY,
                run_date DATE,
                started_at TIMESTAMPTZ,
                finished_at TIMESTAMPTZ,
                status TEXT,
                rows_read BIGINT DEFAULT 0,
                rows_loaded BIGINT DEFAULT 0,
                rows_rejected BIGINT DEFAULT 0,
                error_message TEXT
            )
        """))
        conn.execute(text("""
            INSERT INTO ops.etl_run_log (run_id, run_date, started_at, status)
            VALUES (:run_id, :run_date, :started_at, 'RUNNING')
            ON CONFLICT (run_id) DO NOTHING
        """), {"run_id": run_id, "run_date": run_date, "started_at": datetime.now(UTC).isoformat()})


def _log_run_finish(run_id: str, status: str, rows_read: int, rows_loaded: int, rows_rejected: int, error: str | None, engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE ops.etl_run_log
            SET finished_at=:fin, status=:status, rows_read=:rr, rows_loaded=:rl,
                rows_rejected=:rj, error_message=:err
            WHERE run_id=:run_id
        """), {
            "fin": datetime.now(UTC).isoformat(),
            "status": status,
            "rr": rows_read,
            "rl": rows_loaded,
            "rj": rows_rejected,
            "err": error,
            "run_id": run_id,
        })


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Retail Analytics ETL Pipeline")
    parser.add_argument("--date", default=str(date.today()), help="Run date (YYYY-MM-DD)")
    parser.add_argument("--config", default="pipeline/config.yaml")
    parser.add_argument("--raw-dir", default=None, help="Override raw data directory")
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    paths = cfg.get("paths", {})
    raw_dir = args.raw_dir or paths.get("raw_data", "data/raw")
    processed_dir = paths.get("processed_data", "data/processed")
    reject_dir = paths.get("rejects", "data/rejects")
    reject_threshold = float(cfg.get("etl", {}).get("reject_threshold_pct", 12)) / 100.0

    run_id = str(uuid.uuid4())
    run_date = args.date

    logger.info("=" * 60)
    logger.info("ETL RUN  run_id=%s  date=%s", run_id, run_date)
    logger.info("=" * 60)

    engine = get_engine(args.config)

    _log_run_start(run_id, run_date, engine)

    rows_read = rows_loaded = rows_rejected = 0
    status = "FAILED"
    error_msg = None

    try:
        # ── Stage 1: Extract ─────────────────────────────────────────────
        logger.info("STAGE 1/4  Extract")
        raw_dfs = extract_csv(raw_dir)
        rows_read = sum(len(df) for df in raw_dfs.values())
        load_to_staging(raw_dfs, run_id)

        # ── Stage 2: Transform ───────────────────────────────────────────
        logger.info("STAGE 2/4  Transform")
        results = run_transform(raw_dfs, reject_dir, processed_dir, run_id, reject_threshold=reject_threshold)
        rows_rejected = sum(r.rows_rejected for r in results.values())

        # ── Stage 3: Validate ────────────────────────────────────────────
        logger.info("STAGE 3/4  Validate (reject threshold check in transform)")
        # DQ summary written to ops.dq_results
        _write_dq_results(results, run_id, engine)

        # ── Stage 4: Load ────────────────────────────────────────────────
        logger.info("STAGE 4/4  Load")
        load_counts = run_load(results, run_id, engine)
        rows_loaded = sum(load_counts.values())

        status = "SUCCESS"
        logger.info("Pipeline complete ✓  loaded=%d  rejected=%d", rows_loaded, rows_rejected)

    except Exception as exc:
        error_msg = str(exc)
        logger.error("Pipeline FAILED: %s", error_msg, exc_info=True)

    finally:
        _log_run_finish(run_id, status, rows_read, rows_loaded, rows_rejected, error_msg, engine)

    return 0 if status == "SUCCESS" else 1


def _write_dq_results(results, run_id: str, engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS ops"))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS ops.dq_results (
                run_id TEXT,
                table_name TEXT,
                rule_name TEXT,
                failed_count BIGINT,
                total_count BIGINT,
                severity TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """))
    rows = []
    for name, res in results.items():
        rows.append({
            "run_id": run_id,
            "table_name": name,
            "rule_name": "overall_reject_rate",
            "failed_count": res.rows_rejected,
            "total_count": res.rows_in,
            "severity": "ERROR" if res.rows_in > 0 and res.rows_rejected / res.rows_in > 0.10 else "INFO",
        })
    if rows:
        pd.DataFrame(rows).to_sql("dq_results", schema="ops", con=engine, if_exists="append", index=False)


if __name__ == "__main__":
    sys.exit(main())
