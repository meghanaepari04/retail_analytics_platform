"""Unit tests for the SQL validator in the AI assistant (PRD §10.2)."""
from __future__ import annotations

import pytest
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from assistant.assistant import validate_sql, SQLValidationError


class TestValidateSQL:
    def test_valid_select(self):
        sql = "SELECT product_name FROM rpt.rpt_profitability_product LIMIT 10"
        result = validate_sql(sql)
        assert "SELECT" in result.upper()

    def test_adds_limit_if_missing(self):
        sql = "SELECT * FROM rpt.rpt_sales_daily"
        result = validate_sql(sql)
        assert "LIMIT" in result.upper()

    def test_rejects_delete(self):
        with pytest.raises(SQLValidationError, match="DELETE"):
            validate_sql("DELETE FROM rpt.rpt_sales_daily")

    def test_rejects_drop(self):
        with pytest.raises(SQLValidationError, match="DROP"):
            validate_sql("DROP TABLE rpt.rpt_sales_daily")

    def test_rejects_insert(self):
        with pytest.raises(SQLValidationError, match="INSERT"):
            validate_sql("INSERT INTO rpt.rpt_sales_daily VALUES (1)")

    def test_rejects_disallowed_view(self):
        with pytest.raises(SQLValidationError, match="disallowed"):
            validate_sql("SELECT * FROM dw.fact_sales LIMIT 10")

    def test_rejects_multiple_statements(self):
        with pytest.raises(SQLValidationError, match="single"):
            validate_sql("SELECT 1; SELECT 2 FROM rpt.rpt_sales_daily")

    def test_allowed_views_all_valid(self):
        allowed = [
            "rpt.rpt_sales_daily",
            "rpt.rpt_profitability_product",
            "rpt.rpt_inventory_health",
            "rpt.rpt_customer_rfm",
            "rpt.rpt_returns_analysis",
            "rpt.rpt_opportunities",
        ]
        for view in allowed:
            sql = f"SELECT * FROM {view} LIMIT 5"
            result = validate_sql(sql)
            assert "SELECT" in result.upper()
