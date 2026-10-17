# Raw Data Profiling & Defect Analysis Report

> Generated automatically by the Retail Analytics Platform Data Profiler.

## Summary Overview

| Table | Rows | Columns | Exact Duplicate Rows |
|-------|------|---------|-----------------------|
| **stores** | 25 | 5 | 0 |
| **products** | 250 | 9 | 0 |
| **customers** | 4,040 | 8 | 0 |
| **orders** | 25,000 | 8 | 0 |
| **order_items** | 75,562 | 7 | 0 |
| **inventory** | 12,500 | 7 | 0 |
| **returns** | 3,000 | 6 | 0 |

## Detailed Table Profiles

### Table: `stores` (25 rows, 5 columns)

| Column | Type | Distinct | Nulls | Null % | Sample Values |
|--------|------|----------|-------|--------|---------------|
| `store_id` | object | 25 | 0 | 0.0% | STR0001, STR0002, STR0003 |
| `store_name` | object | 25 | 0 | 0.0% | North Judithbury Outlet, New Roberttown  |
| `city` | object | 25 | 0 | 0.0% | East Jill, East Jessetown, Robinsonshire |
| `region` | object | 5 | 0 | 0.0% | North, East, South |
| `country` | object | 1 | 0 | 0.0% | USA |

### Table: `products` (250 rows, 9 columns)

| Column | Type | Distinct | Nulls | Null % | Sample Values |
|--------|------|----------|-------|--------|---------------|
| `product_id` | object | 250 | 0 | 0.0% | PRD00001, PRD00002, PRD00003 |
| `sku` | object | 250 | 0 | 0.0% | SKU-LJ150, SKU-eT930, SKU-ve310 |
| `name` | object | 250 | 0 | 0.0% | NaturePlus Fitness Khaki Pro, PrimeLine  |
| `category` | object | 8 | 0 | 0.0% | Sports, Toys, Food & Beverage |
| `subcategory` | object | 37 | 0 | 0.0% | Fitness, Board Games, Snacks |
| `brand` | object | 8 | 0 | 0.0% | UrbanEdge, SwiftCo, EcoVerde |
| `cost` | object | 244 | 7 | 2.8% | 38.57, 363.82, 488.09 |
| `list_price` | object | 250 | 0 | 0.0% | 56.22, 828.07, 674.07 |
| `supplier` | object | 5 | 0 | 0.0% | SupplierA, SupplierB, SupplierD |

### Table: `customers` (4,040 rows, 8 columns)

| Column | Type | Distinct | Nulls | Null % | Sample Values |
|--------|------|----------|-------|--------|---------------|
| `customer_id` | object | 4,040 | 0 | 0.0% | CUST000001, CUST000002, CUST000003 |
| `name` | object | 3,904 | 0 | 0.0% | James Conner, Katie Fernandez, Lisa Good |
| `email` | object | 3,897 | 76 | 1.9% | elizabethcalderon@example.net, stanleyna |
| `phone` | object | 3,945 | 56 | 1.4% | +1-581-468-5054x23573, (296)822-2927, 43 |
| `city` | object | 3,498 | 0 | 0.0% | North Kenneth, Ericabury, Lake Timothyst |
| `region` | object | 21 | 0 | 0.0% | Central, South, North |
| `signup_date` | object | 1,268 | 0 | 0.0% | 2025-08-22, 2026-05-05, 2025-07-03 |
| `segment` | object | 4 | 0 | 0.0% | Regular, Premium, Occasional |

### Table: `orders` (25,000 rows, 8 columns)

| Column | Type | Distinct | Nulls | Null % | Sample Values |
|--------|------|----------|-------|--------|---------------|
| `order_id` | object | 25,000 | 0 | 0.0% | ORD0000001, ORD0000002, ORD0000003 |
| `customer_id` | object | 4,354 | 0 | 0.0% | CUST000250, CUST000052, CUST003520 |
| `order_date` | object | 1,775 | 0 | 0.0% | 2023-03-03, 2026-08-11, 2025-08-29 |
| `store_id` | object | 25 | 0 | 0.0% | STR0018, STR0001, STR0003 |
| `channel` | object | 3 | 0 | 0.0% | Online, In-Store, Marketplace |
| `status` | object | 4 | 0 | 0.0% | completed, cancelled, refunded |
| `payment_method` | object | 5 | 0 | 0.0% | Credit Card, Gift Card, Debit Card |
| `discount` | object | 27 | 0 | 0.0% | 0.09, 0.0, 0.28 |

### Table: `order_items` (75,562 rows, 7 columns)

| Column | Type | Distinct | Nulls | Null % | Sample Values |
|--------|------|----------|-------|--------|---------------|
| `line_id` | object | 75,562 | 0 | 0.0% | LN00000001, LN00000002, LN00000003 |
| `order_id` | object | 23,748 | 0 | 0.0% | ORD0004832, ORD0018425, ORD0008401 |
| `product_id` | object | 250 | 0 | 0.0% | PRD00051, PRD00228, PRD00011 |
| `quantity` | object | 545 | 0 | 0.0% | -4, 2, 1 |
| `unit_price` | object | 550 | 0 | 0.0% | 1417.66, 1238.86, 1236.38 |
| `discount` | object | 27 | 0 | 0.0% | 0.21, 0.27, 0.0 |
| `unit_cost` | object | 244 | 2,160 | 2.9% | 655.1, 662.97, 164.47 |

### Table: `inventory` (12,500 rows, 7 columns)

| Column | Type | Distinct | Nulls | Null % | Sample Values |
|--------|------|----------|-------|--------|---------------|
| `snapshot_date` | object | 196 | 0 | 0.0% | 2024-04-14, 2024-07-28, 2026-02-22 |
| `product_id` | object | 250 | 0 | 0.0% | PRD00175, PRD00041, PRD00095 |
| `store_id` | object | 25 | 0 | 0.0% | STR0001, STR0002, STR0003 |
| `on_hand` | object | 576 | 0 | 0.0% | 51, 130, 26 |
| `reserved` | object | 21 | 0 | 0.0% | 2, 7, 3 |
| `reorder_level` | object | 41 | 0 | 0.0% | 41, 38, 25 |
| `lead_time_days` | object | 21 | 0 | 0.0% | 12, 1, 2 |

### Table: `returns` (3,000 rows, 6 columns)

| Column | Type | Distinct | Nulls | Null % | Sample Values |
|--------|------|----------|-------|--------|---------------|
| `return_id` | object | 3,000 | 0 | 0.0% | RET000001, RET000002, RET000003 |
| `order_id` | object | 3,000 | 0 | 0.0% | ORD0009160, ORD0020738, ORD0017958 |
| `product_id` | object | 2,300 | 0 | 0.0% | PRD03665, PRD03221, PRD04778 |
| `return_date` | object | 1,219 | 0 | 0.0% | 2025-12-24, 2023-04-24, 2026-06-27 |
| `reason` | object | 6 | 0 | 0.0% | Not as Described, Wrong Item, Better Pri |
| `refund_amount` | object | 2,907 | 0 | 0.0% | 61.11, 281.63, 472.8 |
