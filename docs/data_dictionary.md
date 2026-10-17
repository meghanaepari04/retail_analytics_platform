# Data Dictionary – Retail Analytics Platform

## Source Datasets

### orders
| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| order_id | TEXT | No | Primary key. Format: ORD0000001 |
| customer_id | TEXT | No | FK → customers.customer_id |
| order_date | DATE | No | ISO 8601. Future dates = reject |
| store_id | TEXT | No | FK → stores.store_id |
| channel | TEXT | No | Canonical: Online, In-Store, Marketplace |
| status | TEXT | No | completed, pending, cancelled, refunded |
| payment_method | TEXT | No | Credit Card, Debit Card, PayPal, Cash, Gift Card |
| discount | NUMERIC | Yes | 0.0–1.0 (order-level discount rate) |

**Known defects injected:**
- `order_date` in multiple formats (DD/MM/YYYY, MM-DD-YYYY, etc.)
- `order_date` set to future dates (~1.5% of rows)
- `customer_id` referencing non-existent customers (~2% of rows)

---

### order_items
| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| line_id | TEXT | No | Primary key |
| order_id | TEXT | No | FK → orders.order_id |
| product_id | TEXT | No | FK → products.product_id |
| quantity | INT | No | Must be > 0 |
| unit_price | NUMERIC | No | List price at time of order. Must be > 0 |
| discount | NUMERIC | Yes | 0.0–1.0 (line-level discount) |
| unit_cost | NUMERIC | Yes | COGS per unit |

**Known defects injected:**
- Negative quantities (~1% of rows)
- Outlier quantities (500–10,000) (~0.5% of rows, quarantined)
- Zero/negative unit_price (~1% of rows)
- unit_price with `$` prefix (~0.5% of rows)
- Duplicate line IDs (~0.75% of rows)
- Outlier unit_price (100× normal) – quarantined

---

### customers
| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| customer_id | TEXT | No | Primary key. Format: CUST000001 |
| name | TEXT | Yes | Full name |
| email | TEXT | Yes | Unique per customer (after dedup) |
| phone | TEXT | Yes | May be null |
| city | TEXT | Yes | |
| region | TEXT | No | Canonical: North, South, East, West, Central |
| signup_date | DATE | Yes | |
| segment | TEXT | Yes | Premium, Regular, Occasional, New |

**Known defects injected:**
- Null emails (~2% of rows)
- Null phones (~1.5% of rows)
- Inconsistent region formats: "north", "N", "NORTH", "Nth" → normalized to "North"
- Duplicate customers with same email, different ID (~1% extra rows)

---

### products
| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| product_id | TEXT | No | Primary key. Format: PRD00001 |
| sku | TEXT | Yes | Internal SKU |
| name | TEXT | No | Product display name |
| category | TEXT | No | Electronics, Clothing, Home & Garden, etc. |
| subcategory | TEXT | Yes | Sub-classification |
| brand | TEXT | Yes | |
| cost | NUMERIC | Yes | Unit COGS. Must be ≥ 0 |
| list_price | NUMERIC | No | Must be > 0 |
| supplier | TEXT | Yes | Supplier name |

**Known defects injected:**
- Zero/negative `list_price` (~1.5% of rows) → rejected
- Null `cost` (~1.5% of rows) → imputed with NULL (allowed)
- Outlier prices (IQR method) → quarantined

---

### inventory
| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| snapshot_date | DATE | No | Date of inventory count |
| product_id | TEXT | No | FK → products.product_id |
| store_id | TEXT | No | FK → stores.store_id |
| on_hand | INT | No | Must be ≥ 0 |
| reserved | INT | No | Allocated but not shipped |
| reorder_level | INT | Yes | Units below which reorder is triggered |
| lead_time_days | INT | Yes | Days from order to receipt |

**Derived:** `available = on_hand − reserved`

**Known defects injected:**
- Negative `on_hand` (~2.5% of rows) → rejected

---

### returns
| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| return_id | TEXT | No | Primary key. Format: RET000001 |
| order_id | TEXT | No | FK → orders.order_id |
| product_id | TEXT | No | FK → products.product_id |
| return_date | DATE | No | Must be ≥ order_date |
| reason | TEXT | No | Canonical reason |
| refund_amount | NUMERIC | Yes | USD amount refunded |

**Known defects injected:**
- `return_date` before `order_date` (~2% of rows) → rejected
- `order_id` referencing non-existent orders (~2.5% of rows) → rejected

---

### stores
| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| store_id | TEXT | No | Primary key. Format: STR0001 |
| store_name | TEXT | No | |
| city | TEXT | Yes | |
| region | TEXT | No | Canonical region |
| country | TEXT | No | Default: USA |

---

## Data Quality Rules

| Rule ID | Table | Column | Rule | Action on Fail |
|---------|-------|--------|------|----------------|
| DQ-01 | order_items | quantity | quantity > 0 | Reject |
| DQ-02 | order_items | unit_price | unit_price > 0 | Reject |
| DQ-03 | orders | order_date | order_date ≤ today | Reject |
| DQ-04 | orders | customer_id | Must exist in customers | Reject |
| DQ-05 | returns | return_date | return_date ≥ order_date | Reject |
| DQ-06 | returns | order_id | Must exist in orders | Reject |
| DQ-07 | products | list_price | list_price > 0 | Reject |
| DQ-08 | inventory | on_hand | on_hand ≥ 0 | Reject |
| DQ-09 | customers | customer_id | Not null | Reject |
| DQ-10 | order_items | quantity | IQR outlier (> 3×IQR) | Quarantine |
| DQ-11 | order_items | unit_price | IQR outlier (> 3×IQR) | Quarantine |
| DQ-12 | products | list_price | IQR outlier (> 3×IQR) | Quarantine |

---

## Missing Value Handling

| Table.Column | Strategy | Reason |
|-------------|----------|--------|
| customers.email | Allow NULL | Not required for analytics |
| customers.phone | Allow NULL | Not required for analytics |
| products.cost | Allow NULL | Margin calculated as NULL when cost missing |
| order_items.discount | Default 0 | No discount if not specified |
| inventory.reorder_level | Allow NULL | Not all products have reorder policy |
| returns.refund_amount | Allow NULL | Exchanges may have $0 refund |

---

## Defect Rate Summary

| Table | Target Defect Rate | Defect Types |
|-------|--------------------|--------------|
| orders | ~3–5% | Future dates, orphan customer IDs, format inconsistency |
| order_items | ~5–8% | Negative qty, zero price, outliers, duplicates, $ prefix |
| customers | ~4–6% | Null email, inconsistent region, duplicate emails |
| products | ~3–5% | Zero/negative price, null cost, outlier prices |
| returns | ~4–6% | Return before order, orphan order IDs |
| inventory | ~2–3% | Negative on_hand |
