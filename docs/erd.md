# Entity Relationship Diagram (ERD)
**Retail Analytics Platform — Relational & Dimensional Architecture**

This document provides both the **Source Operational Model** (3NF Ingestion) and the **Dimensional Warehouse Star Schema** (Kimball Model) for the platform.

---

## 1. Dimensional Warehouse Architecture (Star Schema)

The analytical data warehouse in PostgreSQL is organized under the `dw` schema, optimized for sub-second analytical queries and Power BI DirectQuery / Import modes.

```mermaid
erDiagram
    dim_date ||--o{ fact_sales : "date_key"
    dim_customer ||--o{ fact_sales : "customer_key"
    dim_product ||--o{ fact_sales : "product_key"
    dim_store ||--o{ fact_sales : "store_key"
    dim_channel ||--o{ fact_sales : "channel_key"
    
    dim_date ||--o{ fact_inventory_snapshot : "date_key"
    dim_product ||--o{ fact_inventory_snapshot : "product_key"
    dim_store ||--o{ fact_inventory_snapshot : "store_key"
    
    dim_date ||--o{ fact_returns : "return_date_key"
    dim_product ||--o{ fact_returns : "product_key"
    dim_return_reason ||--o{ fact_returns : "reason_key"

    fact_sales {
        BIGINT sales_key PK
        TEXT line_id
        TEXT order_id
        INT date_key FK
        BIGINT customer_key FK
        BIGINT product_key FK
        BIGINT store_key FK
        BIGINT channel_key FK
        INT quantity
        NUMERIC unit_price
        NUMERIC unit_cost
        NUMERIC gross_amount
        NUMERIC discount_amount
        NUMERIC net_amount
        NUMERIC cost_amount
        NUMERIC profit_amount
    }

    fact_inventory_snapshot {
        BIGINT snapshot_key PK
        INT date_key FK
        BIGINT product_key FK
        BIGINT store_key FK
        INT on_hand
        INT reserved
        INT available
        INT reorder_level
        INT lead_time_days
    }

    fact_returns {
        BIGINT return_key PK
        TEXT return_id
        TEXT order_id
        INT return_date_key FK
        BIGINT product_key FK
        BIGINT reason_key FK
        INT returned_qty
        NUMERIC refund_amount
    }

    dim_date {
        INT date_key PK
        DATE date
        INT year
        INT month
        TEXT month_name
        INT quarter
        INT day_of_month
        BOOLEAN is_weekend
    }

    dim_customer {
        BIGINT customer_key PK
        TEXT customer_id
        TEXT name
        TEXT email
        TEXT region
        TEXT segment
        BOOLEAN is_current
        DATE valid_from
        DATE valid_to
    }

    dim_product {
        BIGINT product_key PK
        TEXT product_id
        TEXT name
        TEXT category
        TEXT subcategory
        TEXT brand
        NUMERIC price
        NUMERIC cost
        BOOLEAN is_current
    }

    dim_store {
        BIGINT store_key PK
        TEXT store_id
        TEXT store_name
        TEXT city
        TEXT region
        TEXT country
    }

    dim_channel {
        BIGINT channel_key PK
        TEXT channel_name
    }

    dim_return_reason {
        BIGINT reason_key PK
        TEXT reason_name
        TEXT reason_group
    }
```

---

## 2. Operational Source ERD (Staging / Raw)

Before ETL transformation, the operational transactions are structured across normalized relational tables:

```mermaid
erDiagram
    CUSTOMERS ||--o{ ORDERS : "places"
    STORES ||--o{ ORDERS : "fulfills"
    ORDERS ||--|{ ORDER_ITEMS : "contains"
    PRODUCTS ||--o{ ORDER_ITEMS : "ordered_in"
    ORDERS ||--o{ RETURNS : "originates"
    STORES ||--o{ INVENTORY : "stocks"
    PRODUCTS ||--o{ INVENTORY : "inventoried_at"

    CUSTOMERS {
        string customer_id PK
        string name
        string email
        string region
        date signup_date
    }

    ORDERS {
        string order_id PK
        string customer_id FK
        string store_id FK
        date order_date
        string channel
        string status
    }

    ORDER_ITEMS {
        string line_id PK
        string order_id FK
        string product_id FK
        int quantity
        decimal unit_price
        decimal discount
    }

    PRODUCTS {
        string product_id PK
        string name
        string category
        decimal price
        decimal cost
    }

    RETURNS {
        string return_id PK
        string order_id FK
        string product_id FK
        date return_date
        string reason
        decimal refund_amount
    }

    INVENTORY {
        string product_id FK
        string store_id FK
        int on_hand
        int reserved
        int reorder_level
    }
```

---

## 3. Dimensional Design Decisions

1. **Slowly Changing Dimensions (SCD Type 2)**:
   - `dim_customer` and `dim_product` track historical attribute changes (e.g. customer relocation across regions, product price or category revisions).
   - Columns `is_current`, `valid_from`, and `valid_to` enable point-in-time revenue attribution.
2. **Fact Table Partitioning**:
   - `fact_sales` is range-partitioned by monthly integer keys (`date_key`), ensuring PostgreSQL automatically prunes partitions during time-bounded queries.
3. **Surrogate Keys**:
   - Every dimension utilizes an auto-incrementing surrogate integer/bigint key (`product_key`, `customer_key`), decoupling analytics queries from changing upstream business keys.
