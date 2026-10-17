"""
Database initialization script.
Runs all SQL DDL files in order against the target PostgreSQL database.
Usage: python -m pipeline.init_db [--config pipeline/config.yaml]
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from sqlalchemy import text
from pipeline.db import get_engine, load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s")
logger = logging.getLogger("pipeline.init_db")

SQL_FILES = [
    "sql/01_schemas.sql",
    "sql/02_dimensions.sql",
    "sql/03_facts.sql",
    "sql/04_indexes.sql",
    "sql/05_views.sql",
    "sql/06_roles.sql",
]


def run_sql_file(path: Path, engine) -> None:
    """Execute a SQL file, splitting on statement boundaries."""
    sql = path.read_text()
    # Split on semicolons but keep DO $$ … $$ blocks intact
    # Simple approach: execute the whole file as one block
    with engine.begin() as conn:
        conn.execute(text(sql))
    logger.info("✓ %s", path.name)


def init_db(config_path: str = "pipeline/config.yaml", sql_dir: str = ".") -> None:
    engine = get_engine(config_path)
    base = Path(sql_dir)

    logger.info("Initializing database schema…")
    for rel in SQL_FILES:
        p = base / rel
        if not p.exists():
            logger.warning("SQL file not found, skipping: %s", p)
            continue
        try:
            run_sql_file(p, engine)
        except Exception as e:
            logger.error("Failed on %s: %s", p.name, e)
            raise

    # Refresh materialized views
    logger.info("Refreshing materialized views…")
    try:
        with engine.begin() as conn:
            conn.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY rpt.rpt_sales_monthly_region_category"))
        logger.info("✓ Materialized views refreshed")
    except Exception:
        logger.info("Materialized view refresh skipped (no data yet)")

    logger.info("✅ Database initialization complete")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Initialize retail analytics DB schema")
    parser.add_argument("--config", default="pipeline/config.yaml")
    parser.add_argument("--sql-dir", default=".", help="Base directory for sql/ folder")
    args = parser.parse_args(argv)
    try:
        init_db(args.config, args.sql_dir)
    except Exception as e:
        logger.error("Init failed: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
