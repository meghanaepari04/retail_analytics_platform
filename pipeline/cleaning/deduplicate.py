"""
Deduplication module (PRD DP-5).
Survivorship rule: latest record wins (based on a sort key).
"""
from __future__ import annotations

import pandas as pd


def deduplicate(
    df: pd.DataFrame,
    key_columns: list[str],
    sort_column: str | None = None,
    sort_ascending: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Remove duplicates based on key_columns.
    If sort_column is given, sort first so latest/best record is kept.

    Returns:
        clean_df: deduplicated DataFrame
        dupes_df: removed duplicate rows (for reject tracking)
    """
    original_len = len(df)

    if sort_column and sort_column in df.columns:
        df = df.sort_values(sort_column, ascending=sort_ascending)

    clean_df = df.drop_duplicates(subset=key_columns, keep="first").reset_index(drop=True)
    dupes_mask = df.duplicated(subset=key_columns, keep="first")
    dupes_df = df[dupes_mask].copy()
    dupes_df["_reject_reason"] = "DUPLICATE"

    removed = original_len - len(clean_df)
    if removed > 0:
        print(f"    Dedup: removed {removed:,} duplicate rows on keys={key_columns}")

    return clean_df, dupes_df


def flag_email_duplicates(df: pd.DataFrame, id_col: str = "customer_id", email_col: str = "email") -> pd.DataFrame:
    """
    Flag customers that share the same email (different IDs).
    Adds a '_is_email_duplicate' boolean column.
    """
    non_null_emails = df[df[email_col].notna()]
    dup_emails = non_null_emails[non_null_emails.duplicated(subset=[email_col], keep=False)][email_col].unique()
    df["_is_email_duplicate"] = df[email_col].isin(dup_emails)
    return df
