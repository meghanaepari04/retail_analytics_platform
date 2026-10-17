"""Date cleaning and standardization (PRD DP-2)."""
from __future__ import annotations

import pandas as pd


KNOWN_FORMATS = [
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%m-%d-%Y",
    "%d-%b-%Y",
    "%B %d, %Y",
    "%m/%d/%Y",
    "%d.%m.%Y",
    "%Y%m%d",
]


def parse_date_column(series: pd.Series, column_name: str = "date") -> tuple[pd.Series, pd.Series]:
    """
    Attempt to parse a series of date strings into ISO 8601 (YYYY-MM-DD).

    Returns:
        clean: pd.Series of datetime64 (NaT where unparseable)
        bad_mask: boolean Series where True = unparseable / already NaT
    """
    # Fast path: pandas infer
    parsed = pd.to_datetime(series, infer_datetime_format=True, errors="coerce")

    # Second pass: try known formats for still-null values
    null_mask = parsed.isna() & series.notna()
    if null_mask.any():
        for fmt in KNOWN_FORMATS:
            still_null = parsed.isna() & series.notna()
            if not still_null.any():
                break
            attempt = pd.to_datetime(series[still_null], format=fmt, errors="coerce")
            parsed[still_null] = attempt

    bad_mask = parsed.isna() & series.notna()  # had a value but couldn't parse
    return parsed, bad_mask


def validate_date_not_future(series: pd.Series, reference: pd.Timestamp | None = None) -> pd.Series:
    """Return boolean mask where True = date is in the future (invalid for orders)."""
    ref = reference or pd.Timestamp.today().normalize()
    return series > ref


def validate_return_after_order(
    return_date: pd.Series, order_date: pd.Series
) -> pd.Series:
    """Return boolean mask where True = return_date < order_date (invalid)."""
    return return_date < order_date
