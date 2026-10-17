"""
ETL Transform stage (PRD ETL-2).
Applies cleaning, normalization, deduplication and validation.
Writes cleaned data to data/processed/ and rejects to data/rejects/.
"""
from __future__ import annotations

import logging
from pathlib import Path
import pandas as pd
from pipeline.cleaning.dates import parse_date_column, validate_date_not_future, validate_return_after_order
from pipeline.cleaning.normalize import (
    normalize_column, clean_numeric_string,
    REGION_MAP, CATEGORY_MAP, PAYMENT_MAP, CHANNEL_MAP,
)
from pipeline.cleaning.deduplicate import deduplicate, flag_email_duplicates
from pipeline.cleaning.validate import (
    validate_positive, validate_not_null, validate_referential_integrity,
    flag_iqr_outliers, validate_orders_df, validate_order_items,
)

logger = logging.getLogger(__name__)


class TransformResult:
    def __init__(self, name: str):
        self.name = name
        self.clean: pd.DataFrame | None = None
        self.rejects: pd.DataFrame | None = None
        self.rows_in: int = 0
        self.rows_clean: int = 0
        self.rows_rejected: int = 0


def _save_reject(df: pd.DataFrame, path: Path, name: str, run_id: str) -> None:
    if len(df) == 0:
        return
    df = df.copy()
    df["_run_id"] = run_id
    out = path / f"{name}_rejects.csv"
    df.to_csv(out, index=False)
    logger.info("Rejects saved: %s (%d rows)", out, len(df))


def transform_stores(df: pd.DataFrame) -> TransformResult:
    res = TransformResult("stores")
    res.rows_in = len(df)
    df = df.copy()
    df["region"] = normalize_column(df["region"], REGION_MAP)
    df["store_name"] = df["store_name"].str.strip().str.title()
    df["city"] = df["city"].str.strip().str.title()
    # Dedup by store_id
    df, dupes = deduplicate(df, ["store_id"])
    res.clean = df
    res.rejects = dupes
    res.rows_clean = len(df)
    res.rows_rejected = len(dupes)
    return res


def transform_products(df: pd.DataFrame) -> TransformResult:
    res = TransformResult("products")
    res.rows_in = len(df)
    df = df.copy()

    # Clean numerics (handles "$12.34" format)
    df["list_price"] = clean_numeric_string(df["list_price"])
    df["cost"] = clean_numeric_string(df["cost"])
    df["category"] = normalize_column(df["category"], CATEGORY_MAP)
    df["name"] = df["name"].str.strip()
    df["brand"] = df["brand"].str.strip().str.title()

    # Validate: price > 0, cost >= 0
    bad_price = validate_positive(df["list_price"], "list_price")
    bad_cost = df["cost"].notna() & (pd.to_numeric(df["cost"], errors="coerce") < 0)
    reject_mask = bad_price | bad_cost
    df["_reject_reason"] = None
    df.loc[bad_price, "_reject_reason"] = "INVALID_LIST_PRICE"
    df.loc[bad_cost & ~bad_price, "_reject_reason"] = "NEGATIVE_COST"

    # Outliers: flag but quarantine
    outlier_price = flag_iqr_outliers(df["list_price"])
    df.loc[outlier_price & ~reject_mask, "_reject_reason"] = "OUTLIER_PRICE"
    reject_mask = reject_mask | outlier_price

    rejects = df[reject_mask].copy()
    clean = df[~reject_mask].drop(columns=["_reject_reason"])
    clean, dupes = deduplicate(clean, ["product_id"])
    rejects = pd.concat([rejects, dupes], ignore_index=True)

    res.clean = clean
    res.rejects = rejects
    res.rows_clean = len(clean)
    res.rows_rejected = len(rejects)
    return res


def transform_customers(df: pd.DataFrame) -> TransformResult:
    res = TransformResult("customers")
    res.rows_in = len(df)
    df = df.copy()

    df["region"] = normalize_column(df["region"], REGION_MAP)
    df["name"] = df["name"].str.strip().str.title()
    df["email"] = df["email"].str.strip().str.lower()
    df["city"] = df["city"].str.strip().str.title()

    # Parse signup_date
    df["signup_date"], bad_dates = parse_date_column(df["signup_date"], "signup_date")

    reject_mask = bad_dates | validate_not_null(df["customer_id"])
    df["_reject_reason"] = None
    df.loc[bad_dates, "_reject_reason"] = "UNPARSEABLE_SIGNUP_DATE"
    df.loc[validate_not_null(df["customer_id"]), "_reject_reason"] = "NULL_CUSTOMER_ID"

    # Flag email duplicates (don't reject, just annotate)
    df = flag_email_duplicates(df)

    rejects = df[reject_mask].copy()
    clean = df[~reject_mask].drop(columns=["_reject_reason"])
    clean, dupes = deduplicate(clean, ["customer_id"], sort_column="signup_date")
    rejects = pd.concat([rejects, dupes], ignore_index=True)

    res.clean = clean
    res.rejects = rejects
    res.rows_clean = len(clean)
    res.rows_rejected = len(rejects)
    return res


def transform_orders(df: pd.DataFrame, valid_customer_ids: set) -> TransformResult:
    res = TransformResult("orders")
    res.rows_in = len(df)
    df = df.copy()

    df["channel"] = normalize_column(df["channel"], CHANNEL_MAP)
    df["payment_method"] = normalize_column(df["payment_method"], PAYMENT_MAP)
    df["discount"] = clean_numeric_string(df["discount"]).clip(0, 1)
    df["status"] = df["status"].str.strip().str.lower()

    # Validate
    df = validate_orders_df(df, valid_customer_ids)
    rejects = df[df["_reject_reason"].notna()].copy()
    clean = df[df["_reject_reason"].isna()].drop(columns=["_reject_reason"])
    clean, dupes = deduplicate(clean, ["order_id"], sort_column="order_date")
    rejects = pd.concat([rejects, dupes], ignore_index=True)

    res.clean = clean
    res.rejects = rejects
    res.rows_clean = len(clean)
    res.rows_rejected = len(rejects)
    return res


def transform_order_items(
    df: pd.DataFrame, valid_order_ids: set, valid_product_ids: set
) -> TransformResult:
    res = TransformResult("order_items")
    res.rows_in = len(df)
    df = df.copy()

    df["unit_price"] = clean_numeric_string(df["unit_price"])
    df["unit_cost"] = clean_numeric_string(df["unit_cost"])
    df["discount"] = clean_numeric_string(df["discount"]).clip(0, 1)
    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce")

    df = validate_order_items(df, valid_order_ids, valid_product_ids)
    rejects = df[df["_reject_reason"].notna()].copy()
    clean = df[df["_reject_reason"].isna()].drop(columns=["_reject_reason"])

    # Outlier quantities: quarantine extreme outliers
    outlier_qty = flag_iqr_outliers(clean["quantity"], multiplier=5.0)
    outlier_price = flag_iqr_outliers(clean["unit_price"], multiplier=5.0)
    outlier_mask = outlier_qty | outlier_price
    outlier_df = clean[outlier_mask].copy()
    outlier_df["_reject_reason"] = "OUTLIER_QUARANTINE"
    rejects = pd.concat([rejects, outlier_df], ignore_index=True)
    clean = clean[~outlier_mask]

    clean, dupes = deduplicate(clean, ["line_id"])
    rejects = pd.concat([rejects, dupes], ignore_index=True)

    res.clean = clean
    res.rejects = rejects
    res.rows_clean = len(clean)
    res.rows_rejected = len(rejects)
    return res


def transform_returns(df: pd.DataFrame, valid_order_ids: set) -> TransformResult:
    res = TransformResult("returns")
    res.rows_in = len(df)
    df = df.copy()

    df["return_date"], bad_ret = parse_date_column(df["return_date"])
    df["_reject_reason"] = None

    orphan_order = ~df["order_id"].isin(valid_order_ids)
    df.loc[bad_ret, "_reject_reason"] = "UNPARSEABLE_RETURN_DATE"
    df.loc[orphan_order & ~bad_ret, "_reject_reason"] = "ORPHAN_ORDER_ID"
    df["refund_amount"] = clean_numeric_string(df["refund_amount"])

    rejects = df[df["_reject_reason"].notna()].copy()
    clean = df[df["_reject_reason"].isna()].drop(columns=["_reject_reason"])
    clean, dupes = deduplicate(clean, ["return_id"])
    rejects = pd.concat([rejects, dupes], ignore_index=True)

    res.clean = clean
    res.rejects = rejects
    res.rows_clean = len(clean)
    res.rows_rejected = len(rejects)
    return res


def transform_inventory(df: pd.DataFrame) -> TransformResult:
    res = TransformResult("inventory")
    res.rows_in = len(df)
    df = df.copy()

    for col in ["on_hand", "reserved", "reorder_level", "lead_time_days"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df["_reject_reason"] = None
    bad_onhand = df["on_hand"] < 0
    df.loc[bad_onhand, "_reject_reason"] = "NEGATIVE_ON_HAND"

    rejects = df[df["_reject_reason"].notna()].copy()
    clean = df[df["_reject_reason"].isna()].drop(columns=["_reject_reason"])

    res.clean = clean
    res.rejects = rejects
    res.rows_clean = len(clean)
    res.rows_rejected = len(rejects)
    return res


def run_transform(
    raw_dfs: dict[str, pd.DataFrame],
    reject_dir: str | Path,
    processed_dir: str | Path,
    run_id: str,
    reject_threshold: float = 0.12,
) -> dict[str, TransformResult]:
    """
    Run all transforms. Raise if any table exceeds reject_threshold rate.
    """
    reject_path = Path(reject_dir)
    reject_path.mkdir(parents=True, exist_ok=True)
    processed_path = Path(processed_dir)
    processed_path.mkdir(parents=True, exist_ok=True)

    results: dict[str, TransformResult] = {}

    # Order matters: dimensions first, then facts
    stores_res = transform_stores(raw_dfs.get("stores", pd.DataFrame()))
    results["stores"] = stores_res

    products_res = transform_products(raw_dfs.get("products", pd.DataFrame()))
    results["products"] = products_res

    customers_res = transform_customers(raw_dfs.get("customers", pd.DataFrame()))
    results["customers"] = customers_res

    valid_customer_ids = set(customers_res.clean["customer_id"].tolist()) if customers_res.clean is not None else set()
    valid_product_ids = set(products_res.clean["product_id"].tolist()) if products_res.clean is not None else set()

    orders_res = transform_orders(raw_dfs.get("orders", pd.DataFrame()), valid_customer_ids)
    results["orders"] = orders_res
    valid_order_ids = set(orders_res.clean["order_id"].tolist()) if orders_res.clean is not None else set()

    items_res = transform_order_items(raw_dfs.get("order_items", pd.DataFrame()), valid_order_ids, valid_product_ids)
    results["order_items"] = items_res

    returns_res = transform_returns(raw_dfs.get("returns", pd.DataFrame()), valid_order_ids)
    results["returns"] = returns_res

    inv_res = transform_inventory(raw_dfs.get("inventory", pd.DataFrame()))
    results["inventory"] = inv_res

    # Save processed and rejects; check thresholds
    for name, res in results.items():
        if res.clean is not None and len(res.clean) > 0:
            res.clean.to_csv(processed_path / f"{name}.csv", index=False)
        if res.rejects is not None and len(res.rejects) > 0:
            _save_reject(res.rejects, reject_path, name, run_id)
        if res.rows_in > 0:
            reject_pct = res.rows_rejected / res.rows_in
            logger.info("Transform %s: %d in → %d clean, %d rejected (%.1f%%)",
                        name, res.rows_in, res.rows_clean, res.rows_rejected, reject_pct * 100)
            if reject_pct > reject_threshold:
                raise RuntimeError(
                    f"FAIL-FAST: {name} reject rate {reject_pct*100:.1f}% exceeds {reject_threshold*100:.0f}% threshold"
                )

    return results
