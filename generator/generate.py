"""
Synthetic Retail Data Generator
================================
Creates reproducible messy datasets with injected defects per PRD §6.
Usage:
    python -m generator.generate [--config pipeline/config.yaml] [--output-dir data/raw]
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from faker import Faker

# ─────────────────────────────────────────────
# Config helpers
# ─────────────────────────────────────────────

DEFAULT_SEED = 42
START_DATE = date(2023, 1, 1)
END_DATE = date(2026, 9, 30)
DATE_RANGE_DAYS = (END_DATE - START_DATE).days

REGIONS = ["North", "South", "East", "West", "Central"]
CHANNELS = ["Online", "In-Store", "Marketplace"]
PAYMENT_METHODS = ["Credit Card", "Debit Card", "PayPal", "Cash", "Gift Card"]
CATEGORIES = ["Electronics", "Clothing", "Home & Garden", "Sports", "Food & Beverage", "Books", "Toys", "Health & Beauty"]
SUBCATEGORIES = {
    "Electronics": ["Phones", "Laptops", "Tablets", "Accessories", "Audio"],
    "Clothing": ["Men", "Women", "Kids", "Footwear", "Accessories"],
    "Home & Garden": ["Furniture", "Decor", "Kitchen", "Garden", "Lighting"],
    "Sports": ["Fitness", "Outdoor", "Team Sports", "Water Sports", "Winter Sports"],
    "Food & Beverage": ["Snacks", "Beverages", "Organic", "Frozen", "Pantry"],
    "Books": ["Fiction", "Non-Fiction", "Academic", "Children", "Comics"],
    "Toys": ["Action Figures", "Puzzles", "Board Games", "Educational", "Outdoor"],
    "Health & Beauty": ["Skincare", "Haircare", "Vitamins", "Personal Care", "Fitness"],
}
BRANDS = ["AlphaGear", "NovaTech", "PrimeLine", "UrbanEdge", "NaturePlus", "SwiftCo", "BoldBrand", "EcoVerde"]
SUPPLIERS = ["SupplierA", "SupplierB", "SupplierC", "SupplierD", "SupplierE"]
ORDER_STATUSES = ["completed", "pending", "cancelled", "refunded"]
RETURN_REASONS = ["Defective", "Wrong Item", "Changed Mind", "Damaged in Transit", "Not as Described", "Better Price Found"]
CUSTOMER_SEGMENTS = ["Premium", "Regular", "Occasional", "New"]

# Intentionally messy variants (for defect injection)
REGION_VARIANTS = {
    "North": ["North", "north", "NORTH", "N", "Nth"],
    "South": ["South", "south", "SOUTH", "S", "Sth", "Southern"],
    "East": ["East", "east", "EAST", "E"],
    "West": ["West", "west", "WEST", "W", "Western"],
    "Central": ["Central", "central", "CENTRAL", "Cntrl", "CTR"],
}
DATE_FORMAT_VARIANTS = ["%Y-%m-%d", "%d/%m/%Y", "%m-%d-%Y", "%d-%b-%Y", "%B %d, %Y"]


# ─────────────────────────────────────────────
# Seasonal & regional multipliers
# ─────────────────────────────────────────────

def seasonal_weight(d: date) -> float:
    """Higher sales in Nov-Dec holiday season."""
    month = d.month
    weights = {11: 2.0, 12: 2.5, 1: 1.3, 7: 1.2, 8: 1.1}
    return weights.get(month, 1.0)


REGION_WEIGHT = {"North": 0.9, "South": 1.1, "East": 1.0, "West": 1.15, "Central": 0.85}


# ─────────────────────────────────────────────
# Core generators
# ─────────────────────────────────────────────

class RetailDataGenerator:
    def __init__(self, seed: int = DEFAULT_SEED, defect_rate: float = 0.05):
        self.seed = seed
        self.defect_rate = defect_rate
        random.seed(seed)
        np.random.seed(seed)
        self.fake = Faker()
        Faker.seed(seed)

    # ── Stores ────────────────────────────────
    def generate_stores(self, n: int = 100) -> pd.DataFrame:
        records = []
        for i in range(1, n + 1):
            region = random.choice(REGIONS)
            records.append({
                "store_id": f"STR{i:04d}",
                "store_name": f"{self.fake.city()} {random.choice(['Outlet','Mall','Express','Hub'])}",
                "city": self.fake.city(),
                "region": region,
                "country": "USA",
            })
        return pd.DataFrame(records)

    # ── Products ──────────────────────────────
    def generate_products(self, n: int = 5000) -> pd.DataFrame:
        records = []
        for i in range(1, n + 1):
            cat = random.choice(CATEGORIES)
            subcat = random.choice(SUBCATEGORIES[cat])
            cost = round(random.uniform(2, 800), 2)
            list_price = round(cost * random.uniform(1.15, 2.5), 2)
            records.append({
                "product_id": f"PRD{i:05d}",
                "sku": f"SKU-{self.fake.bothify('??###')}",
                "name": f"{random.choice(BRANDS)} {subcat} {self.fake.color_name()} {random.choice(['Pro','Plus','Max','Lite','X'])}",
                "category": cat,
                "subcategory": subcat,
                "brand": random.choice(BRANDS),
                "cost": cost,
                "list_price": list_price,
                "supplier": random.choice(SUPPLIERS),
            })
        df = pd.DataFrame(records)
        df = self._inject_product_defects(df)
        return df

    def _inject_product_defects(self, df: pd.DataFrame) -> pd.DataFrame:
        mask = np.random.random(len(df)) < self.defect_rate
        # Inject zero/negative prices
        neg_mask = mask & (np.random.random(len(df)) < 0.3)
        df.loc[neg_mask, "list_price"] = np.random.choice([-1, 0, -99], neg_mask.sum())
        # Null costs
        null_mask = mask & ~neg_mask & (np.random.random(len(df)) < 0.5)
        df.loc[null_mask, "cost"] = np.nan
        return df

    # ── Customers ─────────────────────────────
    def generate_customers(self, n: int = 80000) -> pd.DataFrame:
        records = []
        for i in range(1, n + 1):
            region = random.choice(REGIONS)
            signup = START_DATE + timedelta(days=random.randint(0, DATE_RANGE_DAYS - 30))
            records.append({
                "customer_id": f"CUST{i:06d}",
                "name": self.fake.name(),
                "email": self.fake.email(),
                "phone": self.fake.phone_number(),
                "city": self.fake.city(),
                "region": region,
                "signup_date": signup.strftime("%Y-%m-%d"),
                "segment": random.choice(CUSTOMER_SEGMENTS),
            })
        df = pd.DataFrame(records)
        df = self._inject_customer_defects(df)
        return df

    def _inject_customer_defects(self, df: pd.DataFrame) -> pd.DataFrame:
        n = len(df)
        mask = np.random.random(n) < self.defect_rate

        # Null emails
        null_email = mask & (np.random.random(n) < 0.4)
        df.loc[null_email, "email"] = np.nan

        # Inconsistent region format
        region_format = mask & ~null_email & (np.random.random(n) < 0.5)
        df.loc[region_format, "region"] = df.loc[region_format, "region"].apply(
            lambda r: random.choice(REGION_VARIANTS.get(r, [r]))
        )

        # Duplicate customers (same email, different ID)
        dupe_count = max(1, int(n * self.defect_rate * 0.2))
        dupe_rows = df.sample(dupe_count, random_state=self.seed).copy()
        dupe_rows["customer_id"] = [f"CUST{n + j + 1:06d}" for j in range(dupe_count)]
        df = pd.concat([df, dupe_rows], ignore_index=True)

        # Null phones
        null_phone = np.random.random(len(df)) < (self.defect_rate * 0.3)
        df.loc[null_phone, "phone"] = np.nan

        return df

    # ── Orders ────────────────────────────────
    def generate_orders(
        self,
        n: int = 500000,
        customer_ids: list[str] | None = None,
        store_ids: list[str] | None = None,
    ) -> pd.DataFrame:
        all_dates = [START_DATE + timedelta(days=d) for d in range(DATE_RANGE_DAYS)]
        # Build weighted date pool
        weights = np.array([seasonal_weight(d) for d in all_dates], dtype=float)
        weights /= weights.sum()

        chosen_dates = np.random.choice(len(all_dates), size=n, p=weights)
        order_dates = [all_dates[i] for i in chosen_dates]

        cids = customer_ids or [f"CUST{i:06d}" for i in range(1, 80001)]
        sids = store_ids or [f"STR{i:04d}" for i in range(1, 101)]

        records = []
        for i in range(n):
            od = order_dates[i]
            region = random.choice(REGIONS)
            records.append({
                "order_id": f"ORD{i + 1:07d}",
                "customer_id": random.choice(cids),
                "order_date": od.strftime("%Y-%m-%d"),
                "store_id": random.choice(sids),
                "channel": random.choice(CHANNELS),
                "status": random.choices(ORDER_STATUSES, weights=[0.8, 0.1, 0.06, 0.04])[0],
                "payment_method": random.choice(PAYMENT_METHODS),
                "discount": round(random.choices([0, random.uniform(0.05, 0.30)], weights=[0.6, 0.4])[0], 2),
            })

        df = pd.DataFrame(records)
        df = self._inject_order_defects(df, cids)
        return df

    def _inject_order_defects(self, df: pd.DataFrame, valid_cids: list[str]) -> pd.DataFrame:
        n = len(df)
        mask = np.random.random(n) < self.defect_rate

        # Future dates
        future = mask & (np.random.random(n) < 0.3)
        future_dates = [
            (END_DATE + timedelta(days=random.randint(1, 180))).strftime("%Y-%m-%d")
            for _ in range(future.sum())
        ]
        df.loc[future, "order_date"] = future_dates

        # Unknown customer IDs
        unk_cust = mask & ~future & (np.random.random(n) < 0.4)
        df.loc[unk_cust, "customer_id"] = [f"CUST_UNKNOWN_{j}" for j in range(unk_cust.sum())]

        # Inconsistent date formats
        fmt_mask = mask & ~future & ~unk_cust & (np.random.random(n) < 0.5)
        df.loc[fmt_mask, "order_date"] = df.loc[fmt_mask, "order_date"].apply(
            lambda d: _reformat_date(d, random.choice(DATE_FORMAT_VARIANTS[1:]))
        )

        return df

    # ── Order Items ───────────────────────────
    def generate_order_items(
        self,
        order_ids: list[str],
        product_df: pd.DataFrame,
        n: int = 1_500_000,
    ) -> pd.DataFrame:
        product_ids = product_df["product_id"].tolist()
        prices = dict(zip(product_df["product_id"], product_df["list_price"]))
        costs = dict(zip(product_df["product_id"], product_df["cost"]))

        records = []
        for i in range(n):
            oid = random.choice(order_ids)
            pid = random.choice(product_ids)
            qty = random.choices([1, 2, 3, 4, 5, random.randint(6, 20)], weights=[0.4, 0.25, 0.15, 0.08, 0.07, 0.05])[0]
            unit_price = round(float(prices.get(pid, 10)), 2)
            unit_cost = round(float(costs.get(pid, 5)), 2)
            discount = round(random.choices([0, random.uniform(0.05, 0.3)], weights=[0.65, 0.35])[0], 2)
            records.append({
                "line_id": f"LN{i + 1:08d}",
                "order_id": oid,
                "product_id": pid,
                "quantity": qty,
                "unit_price": unit_price,
                "discount": discount,
                "unit_cost": unit_cost,
            })

        df = pd.DataFrame(records)
        df = self._inject_item_defects(df, order_ids)
        return df

    def _inject_item_defects(self, df: pd.DataFrame, valid_order_ids: list[str]) -> pd.DataFrame:
        n = len(df)
        mask = np.random.random(n) < self.defect_rate

        # Negative quantities
        neg_qty = mask & (np.random.random(n) < 0.3)
        df.loc[neg_qty, "quantity"] = np.random.randint(-5, 0, neg_qty.sum())

        # Outlier quantities
        outlier_qty = mask & ~neg_qty & (np.random.random(n) < 0.2)
        df.loc[outlier_qty, "quantity"] = np.random.randint(500, 10000, outlier_qty.sum())

        # Zero/negative unit_price
        neg_price = mask & ~neg_qty & ~outlier_qty & (np.random.random(n) < 0.3)
        df.loc[neg_price, "unit_price"] = 0

        # Outlier unit_price (100x)
        outlier_price = mask & ~neg_qty & ~outlier_qty & ~neg_price & (np.random.random(n) < 0.2)
        df.loc[outlier_price, "unit_price"] = df.loc[outlier_price, "unit_price"] * 100

        # Currency symbols in price (as string – test parsing)
        currency_mask = mask & ~neg_qty & ~outlier_qty & ~neg_price & ~outlier_price & (np.random.random(n) < 0.2)
        df.loc[currency_mask, "unit_price"] = df.loc[currency_mask, "unit_price"].apply(lambda p: f"${p:.2f}")

        # Duplicate lines
        dupe_n = max(1, int(n * self.defect_rate * 0.15))
        dupes = df.sample(dupe_n, random_state=self.seed).copy()
        dupes["line_id"] = [f"LN_DUP{j:07d}" for j in range(dupe_n)]
        df = pd.concat([df, dupes], ignore_index=True)

        return df

    # ── Inventory ─────────────────────────────
    def generate_inventory(
        self,
        product_ids: list[str],
        store_ids: list[str],
        n: int = 2_000_000,
    ) -> pd.DataFrame:
        # Sample snapshots: random product x store x date combos
        records = []
        sample_dates = [START_DATE + timedelta(days=i) for i in range(0, DATE_RANGE_DAYS, 7)]  # weekly
        combos = [(pid, sid) for pid in random.sample(product_ids, min(len(product_ids), 500))
                  for sid in store_ids]
        for j in range(n):
            pid, sid = combos[j % len(combos)]
            snap_date = random.choice(sample_dates)
            on_hand = max(0, int(np.random.exponential(100)))
            reserved = min(on_hand, random.randint(0, 20))
            reorder_level = random.randint(10, 50)
            lead_time = random.randint(1, 21)
            records.append({
                "snapshot_date": snap_date.strftime("%Y-%m-%d"),
                "product_id": pid,
                "store_id": sid,
                "on_hand": on_hand,
                "reserved": reserved,
                "reorder_level": reorder_level,
                "lead_time_days": lead_time,
            })
        df = pd.DataFrame(records)
        # Inject defect: negative on_hand
        bad = np.random.random(len(df)) < (self.defect_rate * 0.5)
        df.loc[bad, "on_hand"] = np.random.randint(-50, -1, bad.sum())
        return df

    # ── Returns ───────────────────────────────
    def generate_returns(
        self,
        order_df: pd.DataFrame,
        item_df: pd.DataFrame,
        n: int = 60000,
    ) -> pd.DataFrame:
        # Only return from completed orders
        completed = order_df[order_df["status"] == "completed"]
        if len(completed) == 0:
            completed = order_df
        sample_orders = completed.sample(min(n, len(completed)), random_state=self.seed)

        records = []
        for j, (_, row) in enumerate(sample_orders.iterrows()):
            try:
                order_date = pd.to_datetime(row["order_date"], errors="coerce")
                if pd.isna(order_date):
                    order_date = pd.Timestamp(END_DATE)
                return_date = order_date + timedelta(days=random.randint(1, 60))
            except Exception:
                return_date = pd.Timestamp(END_DATE)

            records.append({
                "return_id": f"RET{j + 1:06d}",
                "order_id": row["order_id"],
                "product_id": f"PRD{random.randint(1, 5000):05d}",
                "return_date": return_date.strftime("%Y-%m-%d"),
                "reason": random.choice(RETURN_REASONS),
                "refund_amount": round(random.uniform(5, 500), 2),
            })

        df = pd.DataFrame(records)
        df = self._inject_return_defects(df, order_df)
        return df

    def _inject_return_defects(self, df: pd.DataFrame, order_df: pd.DataFrame) -> pd.DataFrame:
        n = len(df)
        mask = np.random.random(n) < self.defect_rate

        # Return date before order date (invalid)
        early_return = mask & (np.random.random(n) < 0.4)
        df.loc[early_return, "return_date"] = (
            pd.to_datetime(START_DATE) - timedelta(days=30)
        ).strftime("%Y-%m-%d")

        # Returns for non-existent orders
        orphan = mask & ~early_return & (np.random.random(n) < 0.5)
        df.loc[orphan, "order_id"] = [f"ORD_FAKE_{j}" for j in range(orphan.sum())]

        return df


# ─────────────────────────────────────────────
# Utility helpers
# ─────────────────────────────────────────────

def _reformat_date(date_str: str, fmt: str) -> str:
    try:
        d = pd.to_datetime(date_str)
        return d.strftime(fmt)
    except Exception:
        return date_str


def save_csv(df: pd.DataFrame, path: Path, name: str) -> None:
    path.mkdir(parents=True, exist_ok=True)
    out = path / f"{name}.csv"
    df.to_csv(out, index=False)
    print(f"  ✓ Saved {name}.csv ({len(df):,} rows) → {out}")


# ─────────────────────────────────────────────
# Main entrypoint
# ─────────────────────────────────────────────

def main(
    output_dir: str = "data/raw",
    config_path: str | None = None,
    scale: float | None = None,
    num_orders: int | None = None,
    num_customers: int | None = None,
    num_products: int | None = None,
    num_stores: int | None = None,
    num_returns: int | None = None,
) -> None:
    import yaml

    cfg: dict[str, Any] = {}
    if config_path and Path(config_path).exists():
        with open(config_path) as f:
            cfg = yaml.safe_load(f) or {}

    gen_cfg = cfg.get("generator", {})
    scale = scale or gen_cfg.get("scale", 1.0)
    seed = gen_cfg.get("seed", DEFAULT_SEED)
    defect_rate = gen_cfg.get("defect_rate", 0.05)
    n_orders = num_orders or max(100, int(gen_cfg.get("num_orders", 500_000) * scale))
    n_customers = num_customers or max(50, int(gen_cfg.get("num_customers", 80_000) * scale))
    n_products = num_products or max(50, int(gen_cfg.get("num_products", 5_000) * scale))
    n_stores = num_stores or max(10, int(gen_cfg.get("num_stores", 100) * min(scale * 5, 1.0)))
    n_returns = num_returns or max(20, int(gen_cfg.get("num_returns", 60_000) * scale))

    print("\n🏭 Retail Data Generator")
    print(f"   seed={seed}, defect_rate={defect_rate*100:.0f}%, scale={scale}")
    print(f"   orders={n_orders:,}, customers={n_customers:,}, products={n_products:,}, stores={n_stores:,}\n")

    out = Path(output_dir)
    g = RetailDataGenerator(seed=seed, defect_rate=defect_rate)

    print("→ Generating stores…")
    stores_df = g.generate_stores(n_stores)
    save_csv(stores_df, out, "stores")

    print("→ Generating products…")
    products_df = g.generate_products(n_products)
    save_csv(products_df, out, "products")

    print("→ Generating customers…")
    customers_df = g.generate_customers(n_customers)
    save_csv(customers_df, out, "customers")

    print("→ Generating orders…")
    orders_df = g.generate_orders(
        n_orders,
        customer_ids=customers_df["customer_id"].tolist(),
        store_ids=stores_df["store_id"].tolist(),
    )
    save_csv(orders_df, out, "orders")

    print("→ Generating order items (this may take a minute)…")
    n_items = min(n_orders * 3, 1_500_000)
    items_df = g.generate_order_items(
        order_ids=orders_df["order_id"].tolist(),
        product_df=products_df,
        n=n_items,
    )
    save_csv(items_df, out, "order_items")

    print("→ Generating inventory snapshots…")
    n_inv = min(n_products * n_stores * 2, 2_000_000)
    inv_df = g.generate_inventory(
        product_ids=products_df["product_id"].tolist(),
        store_ids=stores_df["store_id"].tolist(),
        n=n_inv,
    )
    save_csv(inv_df, out, "inventory")

    print("→ Generating returns…")
    returns_df = g.generate_returns(orders_df, items_df, n_returns)
    save_csv(returns_df, out, "returns")

    print("\n✅ Data generation complete!\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate synthetic retail data")
    parser.add_argument("--config", default="pipeline/config.yaml")
    parser.add_argument("--output-dir", default="data/raw")
    parser.add_argument("--scale", type=float, default=1.0, help="Scale factor (e.g. 0.05 for 5%% volume dev run)")
    parser.add_argument("--orders", type=int, default=None, help="Explicit order count")
    parser.add_argument("--customers", type=int, default=None, help="Explicit customer count")
    parser.add_argument("--products", type=int, default=None, help="Explicit product count")
    args = parser.parse_args()
    main(args.output_dir, args.config, scale=args.scale, num_orders=args.orders,
         num_customers=args.customers, num_products=args.products)
