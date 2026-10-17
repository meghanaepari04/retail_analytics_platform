"""
Business rule validation and outlier detection (PRD DP-6, DP-7).
Returns boolean reject masks and annotated DataFrames.
"""
from __future__ import annotations

import pandas as pd
import numpy as np


# ─── Business rule validators ────────────────────────────────────────────────

def validate_positive(series: pd.Series, column_name: str) -> pd.Series:
    """True where value is not strictly positive (<=0 or NaN)."""
    numeric = pd.to_numeric(series, errors="coerce")
    return (numeric <= 0) | numeric.isna()


def validate_non_negative(series: pd.Series) -> pd.Series:
    """True where value is negative."""
    numeric = pd.to_numeric(series, errors="coerce")
    return numeric < 0


def validate_not_null(series: pd.Series) -> pd.Series:
    """True where value is null/NaN."""
    return series.isna()


def validate_referential_integrity(
    fk_series: pd.Series,
    pk_series: pd.Series,
    label: str = "FK",
) -> pd.Series:
    """True where fk value is not in the set of valid pk values."""
    valid = set(pk_series.dropna().unique())
    mask = ~fk_series.isin(valid)
    orphans = mask.sum()
    if orphans:
        print(f"    Referential: {orphans:,} orphaned {label} values")
    return mask


# ─── Outlier detection ───────────────────────────────────────────────────────

def flag_iqr_outliers(series: pd.Series, multiplier: float = 3.0) -> pd.Series:
    """
    Return a boolean Series: True = IQR outlier.
    Uses IQR with configurable multiplier (default 3.0 for extreme outliers only).
    """
    numeric = pd.to_numeric(series, errors="coerce")
    q1 = numeric.quantile(0.25)
    q3 = numeric.quantile(0.75)
    iqr = q3 - q1
    lower = q1 - multiplier * iqr
    upper = q3 + multiplier * iqr
    return (numeric < lower) | (numeric > upper)


def flag_zscore_outliers(series: pd.Series, threshold: float = 3.5) -> pd.Series:
    """Return boolean Series: True = |z-score| > threshold."""
    numeric = pd.to_numeric(series, errors="coerce")
    mean = numeric.mean()
    std = numeric.std()
    if std == 0:
        return pd.Series(False, index=series.index)
    z = (numeric - mean) / std
    return z.abs() > threshold


# ─── Composite table validators ──────────────────────────────────────────────

def validate_order_items(df: pd.DataFrame, valid_order_ids: set, valid_product_ids: set) -> pd.DataFrame:
    """
    Returns df with '_reject_reason' column (None = valid).
    Rules: qty > 0, price > 0, cost >= 0, valid FK references.
    """
    reasons = []
    for _, row in df.iterrows():
        r = []
        qty = pd.to_numeric(row.get("quantity"), errors="coerce")
        price = pd.to_numeric(row.get("unit_price"), errors="coerce")
        cost = pd.to_numeric(row.get("unit_cost"), errors="coerce")

        if pd.isna(qty) or qty <= 0:
            r.append("INVALID_QUANTITY")
        if pd.isna(price) or price <= 0:
            r.append("INVALID_PRICE")
        if pd.notna(cost) and cost < 0:
            r.append("NEGATIVE_COST")
        if row.get("order_id") not in valid_order_ids:
            r.append("ORPHAN_ORDER_ID")
        if row.get("product_id") not in valid_product_ids:
            r.append("ORPHAN_PRODUCT_ID")
        reasons.append("|".join(r) if r else None)

    df = df.copy()
    df["_reject_reason"] = reasons
    return df


def validate_orders_df(df: pd.DataFrame, valid_customer_ids: set) -> pd.DataFrame:
    """Validate orders table: future dates, orphan customer IDs."""
    today = pd.Timestamp.today().normalize()
    reasons = []
    for _, row in df.iterrows():
        r = []
        try:
            od = pd.to_datetime(row.get("order_date"), errors="coerce")
            if pd.isna(od):
                r.append("UNPARSEABLE_ORDER_DATE")
            elif od > today:
                r.append("FUTURE_ORDER_DATE")
        except Exception:
            r.append("UNPARSEABLE_ORDER_DATE")

        if row.get("customer_id") not in valid_customer_ids:
            r.append("ORPHAN_CUSTOMER_ID")

        reasons.append("|".join(r) if r else None)

    df = df.copy()
    df["_reject_reason"] = reasons
    return df
