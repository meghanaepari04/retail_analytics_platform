#!/usr/bin/env python3
"""
Retail Analytics Platform — PySpark Distributed Batch Processing Job
Week 4 Deliverable (PRD §12 & §15: Distributed Processing Stretch Goal)

This job performs high-throughput distributed ETL and metric computation:
1. Distributed ingestion of raw CSV/Parquet transaction logs.
2. Distributed data cleansing, schema enforcement, and bad-record isolation.
3. Multi-dimensional aggregations (Monthly Region/Category metrics, Customer RFM scores).
4. Output to snappy-compressed, partitioned Parquet lakehouse storage.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

try:
    from pyspark.sql import SparkSession
    from pyspark.sql import functions as F
    from pyspark.sql.window import Window
    from pyspark.sql.types import (
        StructType, StructField, StringType, DoubleType,
        IntegerType, TimestampType, DateType
    )
except ImportError:
    # Allow execution with a descriptive message if PySpark is not installed in the local environment
    print("Warning: PySpark is not installed in the current Python environment.")
    print("Install it with: pip install pyspark")


def create_spark_session(app_name: str = "RetailAnalyticsETL", master: str = "local[*]") -> SparkSession:
    """Initialize and tune SparkSession for local or cluster execution."""
    builder = (
        SparkSession.builder
        .appName(app_name)
        .master(master)
        .config("spark.sql.shuffle.partitions", "8")
        .config("spark.default.parallelism", "8")
        .config("spark.sql.adaptive.enabled", "true")
        .config("spark.sql.parquet.compression.codec", "snappy")
    )
    return builder.getOrCreate()


def process_sales_and_metrics(spark: SparkSession, data_dir: str, output_dir: str):
    """Distributed ETL pipeline for orders, line items, and product sales."""
    print(f"[*] Starting PySpark Distributed Job on data directory: {data_dir}")
    t0 = time.time()

    raw_path = Path(data_dir)
    orders_file = str(raw_path / "orders.csv")
    items_file = str(raw_path / "order_items.csv")
    products_file = str(raw_path / "products.csv")

    # ── 1. Read Raw Datasets ─────────────────────────────────────────────
    print("[1/5] Ingesting raw datasets...")
    orders_df = spark.read.option("header", "true").option("inferSchema", "true").csv(orders_file)
    items_df = spark.read.option("header", "true").option("inferSchema", "true").csv(items_file)
    products_df = spark.read.option("header", "true").option("inferSchema", "true").csv(products_file)

    # ── 2. Data Cleaning & Normalization ─────────────────────────────────
    print("[2/5] Performing distributed data cleaning & typing...")
    # Parse dates and filter cancelled orders
    clean_orders = (
        orders_df
        .filter(F.col("status") != "cancelled")
        .withColumn("order_date", F.to_date(F.col("order_date")))
        .withColumn("year", F.year("order_date"))
        .withColumn("month", F.month("order_date"))
        .select("order_id", "customer_id", "store_id", "channel", "order_date", "year", "month")
    )

    clean_items = (
        items_df
        .withColumn("quantity", F.col("quantity").cast(IntegerType()))
        .withColumn("unit_price", F.col("unit_price").cast(DoubleType()))
        .withColumn("discount_amount", F.coalesce(F.col("discount_amount").cast(DoubleType()), F.lit(0.0)))
        .filter((F.col("quantity") > 0) & (F.col("unit_price") > 0))
    )

    clean_products = (
        products_df
        .withColumn("cost", F.col("cost").cast(DoubleType()))
        .select("product_id", "name", "category", "subcategory", "cost")
    )

    # ── 3. Join & Compute Line-Level Facts ───────────────────────────────
    print("[3/5] Computing line-level financial facts...")
    sales_facts = (
        clean_items
        .join(clean_orders, on="order_id", how="inner")
        .join(clean_products, on="product_id", how="inner")
        .withColumn("gross_amount", F.round(F.col("quantity") * F.col("unit_price"), 2))
        .withColumn("net_amount", F.round(F.col("gross_amount") - F.col("discount_amount"), 2))
        .withColumn("cost_amount", F.round(F.col("quantity") * F.col("cost"), 2))
        .withColumn("profit_amount", F.round(F.col("net_amount") - F.col("cost_amount"), 2))
    )

    # Cache for multiple aggregation branches
    sales_facts.cache()
    row_count = sales_facts.count()
    print(f"     -> Processed {row_count:,} line items.")

    # ── 4. Distributed Aggregations ──────────────────────────────────────
    print("[4/5] Executing multi-dimensional aggregations...")

    # A. Monthly Region/Category Revenue & Margin
    monthly_summary = (
        sales_facts
        .groupBy("year", "month", "channel", "category")
        .agg(
            F.countDistinct("order_id").alias("total_orders"),
            F.sum("quantity").alias("total_units"),
            F.round(F.sum("gross_amount"), 2).alias("gross_revenue"),
            F.round(F.sum("discount_amount"), 2).alias("total_discounts"),
            F.round(F.sum("net_amount"), 2).alias("net_revenue"),
            F.round(F.sum("profit_amount"), 2).alias("gross_profit"),
        )
        .withColumn(
            "margin_pct",
            F.round((F.col("gross_profit") / F.col("net_revenue")) * 100, 2)
        )
        .orderBy("year", "month", F.desc("net_revenue"))
    )

    # B. Customer RFM Score Computation using Spark Window Functions
    print("     -> Computing customer RFM segments at scale...")
    max_date = sales_facts.agg(F.max("order_date")).collect()[0][0]

    customer_agg = (
        sales_facts
        .groupBy("customer_id")
        .agg(
            F.max("order_date").alias("last_order_date"),
            F.countDistinct("order_id").alias("frequency"),
            F.round(F.sum("net_amount"), 2).alias("monetary")
        )
        .withColumn("recency_days", F.datediff(F.lit(max_date), F.col("last_order_date")))
    )

    # Assign quintile ranks (1-5) via Spark Windowing
    r_window = Window.orderBy(F.desc("recency_days"))
    f_window = Window.orderBy("frequency")
    m_window = Window.orderBy("monetary")

    rfm_scored = (
        customer_agg
        .withColumn("r_score", F.ntile(5).over(r_window))
        .withColumn("f_score", F.ntile(5).over(f_window))
        .withColumn("m_score", F.ntile(5).over(m_window))
        .withColumn(
            "rfm_segment",
            F.when((F.col("r_score") >= 4) & (F.col("f_score") >= 4), "Champions")
            .when((F.col("r_score") >= 3) & (F.col("f_score") >= 3), "Loyal")
            .when((F.col("r_score") >= 4) & (F.col("f_score") <= 2), "Recent Customers")
            .when((F.col("r_score") <= 2) & (F.col("f_score") >= 3), "At Risk")
            .otherwise("Hibernating / Lost")
        )
    )

    # ── 5. Write to Partitioned Parquet Lakehouse Storage ────────────────
    print(f"[5/5] Writing outputs to partitioned Parquet at: {output_dir}")
    out_path = Path(output_dir)

    # Write monthly summary partitioned by year
    monthly_out = str(out_path / "monthly_sales_summary")
    (
        monthly_summary
        .write
        .mode("overwrite")
        .partitionBy("year")
        .parquet(monthly_out)
    )

    # Write customer RFM scores
    rfm_out = str(out_path / "customer_rfm_scores")
    (
        rfm_scored
        .write
        .mode("overwrite")
        .parquet(rfm_out)
    )

    elapsed = time.time() - t0
    print(f"[✓] PySpark Job finished successfully in {elapsed:.2f}s!")
    print(f"    - Output: {monthly_out}")
    print(f"    - Output: {rfm_out}")


def main():
    parser = argparse.ArgumentParser(description="PySpark Retail Analytics Batch Job")
    parser.add_argument("--data-dir", default="data/raw", help="Path to raw CSV dataset")
    parser.add_argument("--output-dir", default="data/processed_parquet", help="Path to output Parquet")
    parser.add_argument("--master", default="local[*]", help="Spark master URL (e.g. local[*], yarn)")
    args = parser.parse_args()

    spark = create_spark_session(master=args.master)
    try:
        process_sales_and_metrics(spark, args.data_dir, args.output_dir)
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
