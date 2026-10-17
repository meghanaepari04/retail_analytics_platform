"""Unit tests for cleaning modules (PRD §14)."""
from __future__ import annotations

import pytest
import pandas as pd
import numpy as np
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from pipeline.cleaning.dates import parse_date_column, validate_date_not_future, validate_return_after_order
from pipeline.cleaning.normalize import normalize_column, clean_numeric_string, REGION_MAP, CHANNEL_MAP
from pipeline.cleaning.deduplicate import deduplicate, flag_email_duplicates
from pipeline.cleaning.validate import (
    validate_positive, validate_non_negative, validate_not_null,
    flag_iqr_outliers, flag_zscore_outliers,
)


# ── Date tests ───────────────────────────────────────────────

class TestParseDateColumn:
    def test_iso_format(self):
        s = pd.Series(["2024-01-15", "2024-12-31"])
        parsed, bad = parse_date_column(s)
        assert bad.sum() == 0
        assert parsed.dt.year.tolist() == [2024, 2024]

    def test_slash_format(self):
        s = pd.Series(["15/01/2024"])
        parsed, bad = parse_date_column(s)
        assert bad.sum() == 0

    def test_unparseable(self):
        s = pd.Series(["not-a-date", "99/99/9999"])
        parsed, bad = parse_date_column(s)
        assert bad.sum() >= 1

    def test_null_passthrough(self):
        s = pd.Series([None, "2024-01-01"])
        parsed, bad = parse_date_column(s)
        assert bad.sum() == 0  # None → NaT, not flagged as bad

    def test_future_date(self):
        future = pd.Series([pd.Timestamp("2099-01-01")])
        mask = validate_date_not_future(future)
        assert mask.all()

    def test_return_before_order(self):
        ret = pd.to_datetime(pd.Series(["2024-01-01"]))
        order = pd.to_datetime(pd.Series(["2024-06-01"]))
        mask = validate_return_after_order(ret, order)
        assert mask.all()


# ── Normalize tests ──────────────────────────────────────────

class TestNormalizeColumn:
    def test_canonical_region(self):
        s = pd.Series(["north", "SOUTH", "Western", "cntrl"])
        result = normalize_column(s, REGION_MAP)
        assert result.tolist() == ["North", "South", "West", "Central"]

    def test_unknown_maps_to_unknown(self):
        s = pd.Series(["Atlantis"])
        result = normalize_column(s, REGION_MAP)
        assert result.tolist() == ["Unknown"]

    def test_null_passthrough(self):
        s = pd.Series([None, "Online"])
        result = normalize_column(s, CHANNEL_MAP)
        assert pd.isna(result.iloc[0])
        assert result.iloc[1] == "Online"


class TestCleanNumericString:
    def test_currency_symbol(self):
        s = pd.Series(["$1,234.56", "$99.99"])
        result = clean_numeric_string(s)
        assert result.tolist() == pytest.approx([1234.56, 99.99])

    def test_already_numeric(self):
        s = pd.Series(["10.5", "200"])
        result = clean_numeric_string(s)
        assert result.tolist() == pytest.approx([10.5, 200.0])

    def test_invalid_string(self):
        s = pd.Series(["abc"])
        result = clean_numeric_string(s)
        assert pd.isna(result.iloc[0])


# ── Deduplicate tests ────────────────────────────────────────

class TestDeduplicate:
    def test_removes_duplicates(self):
        df = pd.DataFrame({"id": ["A", "A", "B"], "val": [1, 2, 3]})
        clean, dupes = deduplicate(df, ["id"])
        assert len(clean) == 2
        assert len(dupes) == 1

    def test_latest_wins(self):
        df = pd.DataFrame({
            "id": ["A", "A"],
            "val": [1, 2],
            "ts": ["2024-01-01", "2024-06-01"],
        })
        clean, _ = deduplicate(df, ["id"], sort_column="ts", sort_ascending=False)
        assert len(clean) == 1
        assert clean.iloc[0]["val"] == 2

    def test_no_duplicates(self):
        df = pd.DataFrame({"id": ["A", "B", "C"], "val": [1, 2, 3]})
        clean, dupes = deduplicate(df, ["id"])
        assert len(clean) == 3
        assert len(dupes) == 0


class TestFlagEmailDuplicates:
    def test_flags_shared_email(self):
        df = pd.DataFrame({
            "customer_id": ["C1", "C2", "C3"],
            "email": ["a@b.com", "a@b.com", "c@d.com"],
        })
        result = flag_email_duplicates(df)
        assert result.loc[result["customer_id"].isin(["C1", "C2"]), "_is_email_duplicate"].all()
        assert not result.loc[result["customer_id"] == "C3", "_is_email_duplicate"].any()


# ── Validate tests ───────────────────────────────────────────

class TestValidatePositive:
    def test_negative_is_invalid(self):
        s = pd.Series([-1, 0, 1, 5])
        mask = validate_positive(s, "price")
        assert mask.tolist() == [True, True, False, False]

    def test_null_is_invalid(self):
        s = pd.Series([None, 5.0])
        mask = validate_positive(s, "price")
        assert mask.iloc[0]

    def test_string_price(self):
        s = pd.Series(["$10.00"])
        mask = validate_positive(s, "price")
        # "$10.00" → non-numeric → NaN → invalid
        assert mask.iloc[0]


class TestOutlierDetection:
    def test_iqr_flags_extreme(self):
        base = list(range(100))
        base.append(100_000)  # extreme outlier
        s = pd.Series(base, dtype=float)
        mask = flag_iqr_outliers(s, multiplier=3.0)
        assert mask.iloc[-1]  # extreme value flagged
        assert not mask.iloc[:50].any()  # normal values not flagged

    def test_zscore_flags_extreme(self):
        s = pd.Series([1.0] * 99 + [999.0])
        mask = flag_zscore_outliers(s, threshold=3.0)
        assert mask.iloc[-1]

    def test_empty_series(self):
        s = pd.Series([], dtype=float)
        mask = flag_iqr_outliers(s)
        assert len(mask) == 0
