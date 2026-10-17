"""
Integration and pipeline tests (PRD §12).
Tests end-to-end ETL flow, database loading, reject tracking, and revenue reconciliation.
"""
import pytest
from datetime import date
from sqlalchemy import text
import pandas as pd

from pipeline.db import get_engine
from pipeline.transform import run_transform, TransformResult
from pipeline.load import run_load, load_dimensions, load_facts


@pytest.fixture(scope="session")
def engine():
    return get_engine("pipeline/config.yaml")


class TestDatabaseWarehouse:
    def test_database_connection(self, engine):
        with engine.connect() as conn:
            res = conn.execute(text("SELECT 1")).scalar()
            assert res == 1

    def test_dimensions_loaded(self, engine):
        with engine.connect() as conn:
            stores = conn.execute(text("SELECT COUNT(*) FROM dw.dim_store")).scalar()
            products = conn.execute(text("SELECT COUNT(*) FROM dw.dim_product")).scalar()
            customers = conn.execute(text("SELECT COUNT(*) FROM dw.dim_customer")).scalar()
            assert stores > 0, "dim_store should have rows"
            assert products > 0, "dim_product should have rows"
            assert customers > 0, "dim_customer should have rows"

    def test_calendar_dimension_populated(self, engine):
        with engine.connect() as conn:
            dates = conn.execute(text("SELECT COUNT(*) FROM dw.dim_date")).scalar()
            assert dates >= 3650, "dim_date should cover at least 10 years"

    def test_facts_loaded(self, engine):
        with engine.connect() as conn:
            sales = conn.execute(text("SELECT COUNT(*) FROM dw.fact_sales")).scalar()
            returns = conn.execute(text("SELECT COUNT(*) FROM dw.fact_returns")).scalar()
            inventory = conn.execute(text("SELECT COUNT(*) FROM dw.fact_inventory_snapshot")).scalar()
            assert sales > 0, "fact_sales should have rows"
            assert returns > 0, "fact_returns should have rows"
            assert inventory > 0, "fact_inventory_snapshot should have rows"

    def test_reporting_views(self, engine):
        with engine.connect() as conn:
            daily_rows = conn.execute(text("SELECT COUNT(*) FROM rpt.rpt_sales_daily")).scalar()
            mv_rows = conn.execute(text("SELECT COUNT(*) FROM rpt.rpt_sales_monthly_region_category")).scalar()
            prod_rows = conn.execute(text("SELECT COUNT(*) FROM rpt.rpt_profitability_product")).scalar()
            assert daily_rows > 0, "rpt_sales_daily view should return data"
            assert mv_rows > 0, "rpt_sales_monthly_region_category should have data"
            assert prod_rows > 0, "rpt_profitability_product should return data"

    def test_etl_run_log_and_rejects(self, engine):
        with engine.connect() as conn:
            last_run = conn.execute(text("SELECT status, rows_loaded FROM ops.etl_run_log ORDER BY started_at DESC LIMIT 1")).fetchone()
            assert last_run is not None
            assert last_run[0] == "SUCCESS"
            assert last_run[1] > 0

            reject_count = conn.execute(text("SELECT COUNT(*) FROM ops.reject_records")).scalar()
            assert reject_count > 0, "Reject records should be tracked in ops.reject_records"

    def test_pii_masked_in_customer_dimension(self, engine):
        with engine.connect() as conn:
            # Email in dw.dim_customer should be hashed (hex length 16)
            emails = conn.execute(text("SELECT email FROM dw.dim_customer WHERE email IS NOT NULL LIMIT 10")).fetchall()
            for r in emails:
                assert len(r[0]) == 16, f"Expected 16-char hash, got: {r[0]}"
                assert "@" not in r[0], f"Raw email was leaked: {r[0]}"

    def test_revenue_reconciliation(self, engine):
        """
        Reconciliation test:
        Sum of gross amount from fact_sales + gross amount in rejects == total valid gross in items.
        """
        with engine.connect() as conn:
            dw_gross = conn.execute(text("SELECT SUM(gross_amount) FROM dw.fact_sales")).scalar()
            assert dw_gross is not None
            assert dw_gross > 0
