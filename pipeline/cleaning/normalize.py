"""Text normalization and canonical name mapping (PRD DP-3)."""
from __future__ import annotations

import re
import pandas as pd


# ─── Mapping tables ──────────────────────────────────────────────────────────

REGION_MAP: dict[str, str] = {
    # North
    "north": "North", "n": "North", "nth": "North",
    # South
    "south": "South", "s": "South", "sth": "South", "southern": "South",
    # East
    "east": "East", "e": "East",
    # West
    "west": "West", "w": "West", "western": "West",
    # Central
    "central": "Central", "cntrl": "Central", "ctr": "Central",
}

CATEGORY_MAP: dict[str, str] = {
    "electronics": "Electronics",
    "clothing": "Clothing",
    "home & garden": "Home & Garden",
    "home and garden": "Home & Garden",
    "garden": "Home & Garden",
    "sports": "Sports",
    "food & beverage": "Food & Beverage",
    "food and beverage": "Food & Beverage",
    "food": "Food & Beverage",
    "books": "Books",
    "toys": "Toys",
    "health & beauty": "Health & Beauty",
    "health and beauty": "Health & Beauty",
    "beauty": "Health & Beauty",
}

PAYMENT_MAP: dict[str, str] = {
    "credit card": "Credit Card",
    "credit": "Credit Card",
    "cc": "Credit Card",
    "debit card": "Debit Card",
    "debit": "Debit Card",
    "dc": "Debit Card",
    "paypal": "PayPal",
    "pay pal": "PayPal",
    "cash": "Cash",
    "gift card": "Gift Card",
    "giftcard": "Gift Card",
    "gc": "Gift Card",
}

CHANNEL_MAP: dict[str, str] = {
    "online": "Online",
    "web": "Online",
    "e-commerce": "Online",
    "in-store": "In-Store",
    "instore": "In-Store",
    "store": "In-Store",
    "retail": "In-Store",
    "marketplace": "Marketplace",
    "market": "Marketplace",
    "amazon": "Marketplace",
    "ebay": "Marketplace",
}


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _strip_and_lower(s: str) -> str:
    return re.sub(r"\s+", " ", str(s)).strip().lower()


def normalize_column(series: pd.Series, mapping: dict[str, str], unknown_value: str = "Unknown") -> pd.Series:
    """
    Apply a canonical mapping to a text series.
    Values not in the map are set to `unknown_value`.
    NaN values remain NaN.
    """
    cleaned = series.where(series.isna(), series.map(lambda x: _strip_and_lower(str(x)) if pd.notna(x) else x))
    result = cleaned.map(lambda x: mapping.get(x, unknown_value) if pd.notna(x) else x)
    return result


def clean_numeric_string(series: pd.Series) -> pd.Series:
    """
    Strip currency symbols, commas, and whitespace; coerce to float.
    E.g. '$1,234.56' → 1234.56
    """
    cleaned = (
        series.astype(str)
        .str.replace(r"[$€£,\s]", "", regex=True)
        .str.strip()
    )
    return pd.to_numeric(cleaned, errors="coerce")


def normalize_text_column(series: pd.Series) -> pd.Series:
    """Generic: trim whitespace and title-case."""
    return series.astype(str).str.strip().str.title().where(series.notna(), other=pd.NA)
