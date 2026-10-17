"""
ETL Extract stage (PRD ETL-1, ETL-2).
Reads raw CSVs into pandas DataFrames and loads them into the stg schema.
"""
from __future__ import annotations

import logging
from pathlib import Path
import pandas as pd
from sqlalchemy import text
from pipeline.db import get_engine

logger = logging.getLogger(__name__)

SOURCE_TABLES = [
    "orders",
    "order_items",
    "customers",
    "products",
    "inventory",
    "returns",
    "stores",
]


def extract_csv(raw_dir: str | Path) -> dict[str, pd.DataFrame]:
    """Read all source CSVs from raw_dir. Return dict of {table_name: DataFrame}."""
    raw_path = Path(raw_dir)
    dfs: dict[str, pd.DataFrame] = {}
    for table in SOURCE_TABLES:
        csv_file = raw_path / f"{table}.csv"
        if not csv_file.exists():
            logger.warning("Missing raw file: %s", csv_file)
            continue
        df = pd.read_csv(csv_file, dtype=str, keep_default_na=False, na_values=["", "NULL", "null", "NA", "N/A"])
        logger.info("Extracted %s: %d rows", table, len(df))
        dfs[table] = df
    return dfs


def load_to_staging(dfs: dict[str, pd.DataFrame], run_id: str) -> None:
    """Load raw DataFrames (as text) into stg schema. Drops and recreates each run."""
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS stg"))

    for table, df in dfs.items():
        df = df.copy()
        df["_run_id"] = run_id
        df["_load_ts"] = pd.Timestamp.utcnow().isoformat()
        stg_table = f"stg.{table}_raw"
        with engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS {stg_table} CASCADE"))
        df.to_sql(
            name=f"{table}_raw",
            schema="stg",
            con=engine,
            if_exists="replace",
            index=False,
            method="multi",
            chunksize=10_000,
        )
        logger.info("Loaded stg.%s_raw: %d rows", table, len(df))
