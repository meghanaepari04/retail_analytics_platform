"""
ETL Load stage (PRD ETL-2, ETL-3, ETL-5).
Resolves surrogate keys and loads cleaned DataFrames into dw schema
using idempotent upserts (INSERT … ON CONFLICT DO UPDATE).

Key design decisions:
- Loads into production dim/fact tables directly (no separate staging DB tables)
- Surrogate keys resolved via lookup maps built from dim tables
- SCD1 for v1; SCD2 merge function provided for week-3 upgrade
- Each table load wrapped in a transaction (no partial loads)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import pandas as pd
from sqlalchemy import text

from pipeline.db import get_engine

logger = logging.getLogger(__name__)
UTC = timezone.utc


# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _get_target_col_types(schema: str, table: str, engine) -> dict[str, str]:
    """Fetch column udt_names from target PostgreSQL table."""
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT column_name, udt_name 
            FROM information_schema.columns 
            WHERE table_schema = :schema AND table_name = :table
        """), {"schema": schema, "table": table}).fetchall()
    return {r[0]: r[1] for r in rows}


def _batch_insert(df: pd.DataFrame, table: str, schema: str, engine,
                  conflict_cols: list[str], chunksize: int = 20_000) -> int:
    """
    Insert rows in batches using INSERT … ON CONFLICT DO UPDATE.
    Uses a per-batch temp table to avoid memory issues on large loads.
    Returns total rows processed.
    """
    if df is None or len(df) == 0:
        return 0

    if conflict_cols:
        df = df.drop_duplicates(subset=conflict_cols, keep="last")

    # Replace empty strings with None so casting to int/date/numeric works
    df = df.replace({"": None})

    total = 0
    cols = list(df.columns)
    col_list = ", ".join(f'"{c}"' for c in cols)
    conflict_str = ", ".join(f'"{c}"' for c in conflict_cols)
    update_cols = [c for c in cols if c not in conflict_cols]
    if update_cols:
        update_str = ", ".join(f'"{c}" = EXCLUDED."{c}"' for c in update_cols)
    else:
        # Nothing to update; use DO NOTHING
        update_str = None

    type_map = _get_target_col_types(schema, table, engine)
    select_items = []
    for c in cols:
        t = type_map.get(c)
        if t in ("timestamptz", "timestamp", "date", "numeric", "int8", "int4", "int2", "bool", "float8", "float4"):
            select_items.append(f'"{c}"::{t}')
        else:
            select_items.append(f'"{c}"')
    select_list = ", ".join(select_items)

    for i in range(0, len(df), chunksize):
        chunk = df.iloc[i : i + chunksize]
        tmp = f"_etl_tmp_{table}_{i}"
        with engine.begin() as conn:
            # Write chunk to a temp table
            chunk.to_sql(
                tmp, conn, schema="pg_temp",
                if_exists="replace", index=False,
                method="multi", chunksize=5_000,
            )
            if update_str:
                upsert_sql = f"""
                    INSERT INTO {schema}."{table}" ({col_list})
                    SELECT {select_list} FROM pg_temp."{tmp}"
                    ON CONFLICT ({conflict_str}) DO UPDATE SET {update_str}
                """
            else:
                upsert_sql = f"""
                    INSERT INTO {schema}."{table}" ({col_list})
                    SELECT {select_list} FROM pg_temp."{tmp}"
                    ON CONFLICT ({conflict_str}) DO NOTHING
                """
            conn.execute(text(upsert_sql))
            conn.execute(text(f'DROP TABLE IF EXISTS pg_temp."{tmp}"'))
        total += len(chunk)

    return total


def _build_lookup(engine, table: str, schema: str, biz_key: str, surrogate_key: str) -> dict:
    """Build a {business_key → surrogate_key} dict from an existing dim table."""
    with engine.connect() as conn:
        rows = conn.execute(
            text(f'SELECT "{biz_key}", "{surrogate_key}" FROM {schema}."{table}"')
        ).fetchall()
    return {r[0]: r[1] for r in rows}


# ──────────────────────────────────────────────────────────────
# Dimension loaders
# ──────────────────────────────────────────────────────────────

def load_dim_store(df: pd.DataFrame, run_id: str, engine) -> int:
    """Load dim_store. Returns rows upserted."""
    if df is None or len(df) == 0:
        return 0
    df = df.copy()
    df["_etl_run_id"] = run_id
    df["_updated_at"] = _now_iso()
    # Keep only columns that exist in the target table
    keep = ["store_id", "store_name", "city", "region", "country", "_etl_run_id", "_updated_at"]
    df = df[[c for c in keep if c in df.columns]]
    rows = _batch_insert(df, "dim_store", "dw", engine, ["store_id"])
    logger.info("dim_store: %d rows upserted", rows)
    return rows


def load_dim_product(df: pd.DataFrame, run_id: str, engine) -> int:
    """Load dim_product (SCD1 for v1 – overwrites current record)."""
    if df is None or len(df) == 0:
        return 0
    df = df.copy()
    today = datetime.now(UTC).date().isoformat()
    df["valid_from"] = today
    df["valid_to"] = "9999-12-31"
    df["is_current"] = True
    df["_etl_run_id"] = run_id
    keep = ["product_id", "sku", "name", "category", "subcategory", "brand",
            "supplier", "cost", "list_price", "valid_from", "valid_to", "is_current", "_etl_run_id"]
    df = df[[c for c in keep if c in df.columns]]
    rows = _batch_insert(df, "dim_product", "dw", engine, ["product_id", "valid_from"])
    logger.info("dim_product: %d rows upserted", rows)
    return rows


def load_dim_customer(df: pd.DataFrame, run_id: str, engine) -> int:
    """Load dim_customer (SCD1 for v1)."""
    if df is None or len(df) == 0:
        return 0
    df = df.copy()
    today = datetime.now(UTC).date().isoformat()
    df["valid_from"] = today
    df["valid_to"] = "9999-12-31"
    df["is_current"] = True
    df["_etl_run_id"] = run_id
    # Never expose raw email/phone in the warehouse (mask for PII)
    if "email" in df.columns:
        import hashlib
        df["email"] = df["email"].apply(
            lambda e: hashlib.sha256(str(e).encode()).hexdigest()[:16] if pd.notna(e) else None
        )
    keep = ["customer_id", "name", "email", "city", "region", "segment",
            "signup_date", "valid_from", "valid_to", "is_current", "_etl_run_id"]
    df = df[[c for c in keep if c in df.columns]]
    rows = _batch_insert(df, "dim_customer", "dw", engine, ["customer_id", "valid_from"])
    logger.info("dim_customer: %d rows upserted", rows)
    return rows


def load_dim_channel(engine) -> dict[str, int]:
    """Ensure all channel values exist; return {channel_name: channel_key} map."""
    channels = ["Online", "In-Store", "Marketplace", "Unknown"]
    with engine.begin() as conn:
        for ch in channels:
            conn.execute(text(
                "INSERT INTO dw.dim_channel (channel_name) VALUES (:n) ON CONFLICT (channel_name) DO NOTHING"
            ), {"n": ch})
    return _build_lookup(engine, "dim_channel", "dw", "channel_name", "channel_key")


def load_dim_return_reason(engine) -> dict[str, int]:
    """Ensure all return reasons exist; return {reason_name: reason_key} map."""
    reasons = [
        ("Defective", "Quality"), ("Wrong Item", "Fulfillment"),
        ("Changed Mind", "Customer"), ("Damaged in Transit", "Shipping"),
        ("Not as Described", "Quality"), ("Better Price Found", "Customer"),
        ("Unknown", "Other"),
    ]
    with engine.begin() as conn:
        for name, grp in reasons:
            conn.execute(text(
                "INSERT INTO dw.dim_return_reason (reason_name, reason_group) VALUES (:n,:g) ON CONFLICT (reason_name) DO NOTHING"
            ), {"n": name, "g": grp})
    return _build_lookup(engine, "dim_return_reason", "dw", "reason_name", "reason_key")


# ──────────────────────────────────────────────────────────────
# Fact loaders
# ──────────────────────────────────────────────────────────────

def load_fact_sales(
    orders_df: pd.DataFrame,
    items_df: pd.DataFrame,
    run_id: str,
    engine,
) -> int:
    """
    Build fact_sales rows:
    - Join items → orders to get date/store/customer/channel
    - Resolve surrogate keys via lookup maps
    - Compute measures (gross, net, profit)
    - Upsert on line_id
    """
    if items_df is None or len(items_df) == 0:
        return 0

    logger.info("Building fact_sales lookup maps…")
    # Lookup maps
    date_map = _build_lookup(engine, "dim_date", "dw", "date", "date_key")
    store_map = _build_lookup(engine, "dim_store", "dw", "store_id", "store_key")
    cust_map = _build_lookup(engine, "dim_customer", "dw", "customer_id", "customer_key")
    chan_map = load_dim_channel(engine)
    prod_map = _build_lookup(engine, "dim_product", "dw", "product_id", "product_key")

    logger.info("Merging items with orders…")
    df = items_df.merge(
        orders_df[["order_id", "customer_id", "order_date", "store_id", "channel",
                   "status", "payment_method", "discount"]].rename(columns={"discount": "order_discount"}),
        on="order_id",
        how="left",
    )

    # Parse dates (already cleaned, but ensure date type)
    df["order_date"] = pd.to_datetime(df["order_date"], errors="coerce")

    logger.info("Resolving surrogate keys…")
    df["date_key"] = pd.to_numeric(df["order_date"].dt.strftime("%Y%m%d"), errors="coerce")
    df["store_key"] = df["store_id"].map(store_map)
    df["customer_key"] = df["customer_id"].map(cust_map)
    df["channel_key"] = df["channel"].map(chan_map)
    df["product_key"] = df["product_id"].map(prod_map)

    # Drop rows with no date_key (can't place in fact table without a date)
    missing_date = df["date_key"].isna().sum()
    if missing_date > 0:
        logger.warning("Dropping %d rows with unresolvable date_key", missing_date)
    df = df[df["date_key"].notna()].copy()

    # Ensure numeric types
    for col in ["quantity", "unit_price", "unit_cost", "discount", "order_discount"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    # Combine line + order discount
    df["combined_discount"] = (df["discount"] + df["order_discount"]).clip(0, 1)

    # Compute measures
    df["gross_amount"] = (df["quantity"] * df["unit_price"]).round(2)
    df["discount_amount"] = (df["gross_amount"] * df["combined_discount"]).round(2)
    df["net_amount"] = (df["gross_amount"] - df["discount_amount"]).round(2).clip(lower=0)
    df["cost_amount"] = (df["quantity"] * df["unit_cost"]).round(2)
    df["profit_amount"] = (df["net_amount"] - df["cost_amount"]).round(2)
    df["discount_rate"] = df["combined_discount"].round(4)
    df["_etl_run_id"] = run_id

    # Select final columns matching dw.fact_sales schema
    fact_cols = [
        "line_id", "order_id", "date_key", "customer_key", "product_key",
        "store_key", "channel_key", "quantity", "unit_price", "unit_cost",
        "discount_rate", "gross_amount", "discount_amount", "net_amount",
        "cost_amount", "profit_amount", "_etl_run_id",
    ]
    df = df[[c for c in fact_cols if c in df.columns]]

    # Cast key columns to Int64 (nullable int) so NaN → NULL not 0
    for k in ["date_key", "customer_key", "product_key", "store_key", "channel_key"]:
        if k in df.columns:
            df[k] = df[k].astype("Int64")

    rows = _batch_insert(df, "fact_sales", "dw", engine, ["line_id", "date_key"])
    logger.info("fact_sales: %d rows upserted", rows)
    return rows


def load_fact_returns(
    returns_df: pd.DataFrame,
    run_id: str,
    engine,
) -> int:
    if returns_df is None or len(returns_df) == 0:
        return 0

    date_map = _build_lookup(engine, "dim_date", "dw", "date", "date_key")
    prod_map = _build_lookup(engine, "dim_product", "dw", "product_id", "product_key")
    reason_map = load_dim_return_reason(engine)

    df = returns_df.copy()
    df["return_date"] = pd.to_datetime(df["return_date"], errors="coerce")
    df["return_date_key"] = pd.to_numeric(df["return_date"].dt.strftime("%Y%m%d"), errors="coerce")
    df["product_key"] = df["product_id"].map(prod_map)
    df["reason_key"] = df["reason"].map(reason_map).fillna(reason_map.get("Unknown"))
    if "quantity" in df.columns:
        df["returned_qty"] = pd.to_numeric(df["quantity"], errors="coerce").fillna(1).astype(int)
    else:
        df["returned_qty"] = 1
    if "refund_amount" in df.columns:
        df["refund_amount"] = pd.to_numeric(df["refund_amount"], errors="coerce")
    else:
        df["refund_amount"] = None
    df["_etl_run_id"] = run_id

    fact_cols = ["return_id", "order_id", "return_date_key", "product_key",
                 "reason_key", "returned_qty", "refund_amount", "_etl_run_id"]
    df = df[[c for c in fact_cols if c in df.columns]]
    for k in ["return_date_key", "product_key", "reason_key"]:
        if k in df.columns:
            df[k] = df[k].astype("Int64")

    rows = _batch_insert(df, "fact_returns", "dw", engine, ["return_id"])
    logger.info("fact_returns: %d rows upserted", rows)
    return rows


def load_fact_inventory(
    inventory_df: pd.DataFrame,
    run_id: str,
    engine,
) -> int:
    if inventory_df is None or len(inventory_df) == 0:
        return 0

    date_map = _build_lookup(engine, "dim_date", "dw", "date", "date_key")
    prod_map = _build_lookup(engine, "dim_product", "dw", "product_id", "product_key")
    store_map = _build_lookup(engine, "dim_store", "dw", "store_id", "store_key")

    df = inventory_df.copy()
    df["snapshot_date_key"] = pd.to_numeric(pd.to_datetime(df["snapshot_date"], errors="coerce").dt.strftime("%Y%m%d"), errors="coerce")
    df["product_key"] = df["product_id"].map(prod_map)
    df["store_key"] = df["store_id"].map(store_map)

    # Only load where all keys resolved
    pre = len(df)
    df = df[df["snapshot_date_key"].notna() & df["product_key"].notna() & df["store_key"].notna()].copy()
    logger.info("Inventory: %d/%d rows have all keys resolved", len(df), pre)

    for col in ["on_hand", "reserved", "reorder_level", "lead_time_days"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).clip(lower=0).astype(int)
    df["available"] = (df["on_hand"] - df["reserved"]).clip(lower=0)
    df["_etl_run_id"] = run_id

    fact_cols = ["snapshot_date_key", "product_key", "store_key",
                 "on_hand", "reserved", "available", "reorder_level", "lead_time_days", "_etl_run_id"]
    df = df[[c for c in fact_cols if c in df.columns]]
    for k in ["snapshot_date_key", "product_key", "store_key"]:
        if k in df.columns:
            df[k] = df[k].astype("Int64")

    rows = _batch_insert(df, "fact_inventory_snapshot", "dw", engine,
                         ["snapshot_date_key", "product_key", "store_key"])
    logger.info("fact_inventory_snapshot: %d rows upserted", rows)
    return rows


# ──────────────────────────────────────────────────────────────
# Reject logger
# ──────────────────────────────────────────────────────────────

def log_rejects(results: dict, run_id: str, engine) -> None:
    """Write all rejected rows to ops.reject_records."""
    records = []
    for table_name, res in results.items():
        if res.rejects is None or len(res.rejects) == 0:
            continue
        id_candidates = [f"{table_name[:-1]}_id", "line_id", "return_id", "order_id"]
        id_col = next((c for c in id_candidates if c in res.rejects.columns), None)
        for _, row in res.rejects.iterrows():
            records.append({
                "run_id": run_id,
                "source_table": table_name,
                "source_key": str(row[id_col]) if id_col else "",
                "reason_code": str(row.get("_reject_reason", "UNKNOWN")),
                "raw_payload": row.to_json(),
            })
    if not records:
        return

    _ensure_ops_tables(engine)
    df = pd.DataFrame(records)
    with engine.begin() as conn:
        df.to_sql("reject_records", schema="ops", con=conn,
                  if_exists="append", index=False, method="multi", chunksize=5_000)
    logger.info("Logged %d reject records to ops.reject_records", len(records))


def _ensure_ops_tables(engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS ops"))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS ops.reject_records (
                id           BIGSERIAL PRIMARY KEY,
                run_id       TEXT NOT NULL,
                source_table TEXT NOT NULL,
                source_key   TEXT,
                reason_code  TEXT NOT NULL,
                raw_payload  TEXT,
                created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS ops.dq_results (
                id           BIGSERIAL PRIMARY KEY,
                run_id       TEXT NOT NULL,
                table_name   TEXT NOT NULL,
                rule_name    TEXT NOT NULL,
                failed_count BIGINT NOT NULL DEFAULT 0,
                total_count  BIGINT NOT NULL DEFAULT 0,
                severity     TEXT NOT NULL DEFAULT 'INFO',
                created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))


# ──────────────────────────────────────────────────────────────
# Top-level orchestrators
# ──────────────────────────────────────────────────────────────

def load_dimensions(results: dict, run_id: str, engine=None) -> dict[str, int]:
    """Load all dimension tables. Returns {table: rows_loaded}."""
    if engine is None:
        engine = get_engine()
    counts: dict[str, int] = {}

    stores = results.get("stores")
    if stores and stores.clean is not None:
        counts["dim_store"] = load_dim_store(stores.clean, run_id, engine)

    products = results.get("products")
    if products and products.clean is not None:
        counts["dim_product"] = load_dim_product(products.clean, run_id, engine)

    customers = results.get("customers")
    if customers and customers.clean is not None:
        counts["dim_customer"] = load_dim_customer(customers.clean, run_id, engine)

    return counts


def load_facts(results: dict, run_id: str, engine=None) -> dict[str, int]:
    """Load all fact tables with surrogate key resolution. Returns {table: rows_loaded}."""
    if engine is None:
        engine = get_engine()
    counts: dict[str, int] = {}

    orders = results.get("orders")
    items = results.get("order_items")
    if orders and orders.clean is not None and items and items.clean is not None:
        counts["fact_sales"] = load_fact_sales(orders.clean, items.clean, run_id, engine)

    returns = results.get("returns")
    if returns and returns.clean is not None:
        counts["fact_returns"] = load_fact_returns(returns.clean, run_id, engine)

    inventory = results.get("inventory")
    if inventory and inventory.clean is not None:
        counts["fact_inventory_snapshot"] = load_fact_inventory(inventory.clean, run_id, engine)

    return counts


def refresh_materialized_views(engine=None) -> None:
    """Refresh materialized views in the rpt schema."""
    if engine is None:
        engine = get_engine()
    # Try concurrent refresh first; fallback to standard refresh if unpopulated
    try:
        with engine.begin() as conn:
            conn.execute(text(
                "REFRESH MATERIALIZED VIEW CONCURRENTLY rpt.rpt_sales_monthly_region_category"
            ))
        logger.info("Materialized views refreshed (concurrently)")
    except Exception:
        try:
            with engine.begin() as conn:
                conn.execute(text(
                    "REFRESH MATERIALIZED VIEW rpt.rpt_sales_monthly_region_category"
                ))
            logger.info("Materialized views refreshed (initial populate)")
        except Exception as e:
            logger.warning("Could not refresh materialized views: %s", e)


def run_load(results: dict, run_id: str, engine=None) -> dict[str, int]:
    """
    Load all cleaned data into the dw schema.
    Returns dict of {table: rows_loaded}.
    """
    if engine is None:
        engine = get_engine()
    _ensure_ops_tables(engine)
    counts: dict[str, int] = {}

    # Dimensions first, then facts, then rejects and view refreshes
    counts.update(load_dimensions(results, run_id, engine))
    counts.update(load_facts(results, run_id, engine))
    log_rejects(results, run_id, engine)
    refresh_materialized_views(engine)

    return counts

