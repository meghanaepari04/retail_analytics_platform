"""
AI Insight Assistant – Text-to-SQL engine (PRD §10)
====================================================
Flow:
  1. User question → LLM generates SQL (restricted to rpt schema views)
  2. SQL validator: SELECT-only, allow-listed views, LIMIT enforced, timeout 10s
  3. SQL executed against PostgreSQL with ai_reader role
  4. Result rows → LLM generates plain-English answer
  5. Response includes: answer + SQL used + result table
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import text

from pipeline.db import get_engine, load_config

logger = logging.getLogger(__name__)

# ── Schema description sent to the LLM ──────────────────────

SCHEMA_DESCRIPTION = """
You have access to the following PostgreSQL views in the 'rpt' schema.
Only SELECT queries on these views are allowed.

VIEWS:
1. rpt.rpt_sales_daily
   Columns: sale_date, year, month, month_name, quarter, week_of_year,
            region, store_name, channel_name, orders, units_sold,
            gross_revenue, total_discount, net_revenue, total_cost,
            gross_profit, margin_pct, aov

2. rpt.rpt_sales_monthly_region_category
   Columns: year, month, month_name, quarter, region, category,
            subcategory, orders, units_sold, gross_revenue, net_revenue,
            gross_profit, margin_pct

3. rpt.rpt_profitability_product
   Columns: product_id, product_name, category, subcategory, brand,
            gross_revenue, net_revenue, total_cost, gross_profit,
            margin_pct, units_sold, profit_rank

4. rpt.rpt_inventory_health
   Columns: product_id, product_name, category, store_id, store_name,
            region, on_hand, reserved, available, reorder_level,
            lead_time_days, days_of_cover, is_stockout, is_overstock,
            is_dead_stock

5. rpt.rpt_customer_rfm
   Columns: customer_key, customer_id, customer_name, region, segment,
            last_order_date, frequency, monetary, recency_days,
            r_score, f_score, m_score, rfm_segment, clv_simple

6. rpt.rpt_customer_cohorts
   Columns: cohort_month, months_since, cohort_size, active_customers,
            retention_pct

7. rpt.rpt_returns_analysis
   Columns: product_id, product_name, category, region, return_reason,
            reason_group, return_count, total_refund, units_sold,
            return_rate_pct

8. rpt.rpt_opportunities
   Columns: opportunity_type, entity_name, customer_id, product_id,
            store_id, value, metric_label, region

9. rpt.rpt_executive_summary
   Columns: year, month, quarter, gross_revenue, net_revenue, gross_profit,
            total_cost, total_discount, units_sold, total_orders,
            active_customers, margin_pct, aov, returned_units, return_rate_pct

10. rpt.rpt_discount_impact
    Columns: discount_band, category, orders, units_sold, gross_revenue,
             total_discount, net_revenue, gross_profit, margin_pct

11. rpt.rpt_inventory_turnover
    Columns: category, total_cogs, avg_inventory_value, inventory_turnover_ratio,
             days_to_sell

12. rpt.rpt_new_vs_returning
    Columns: year, month, quarter, customer_type, customers

13. rpt.rpt_dq_scorecard
    Columns: run_id, run_started, run_status, rows_read, rows_loaded,
             rows_rejected, reject_rate_pct, table_name, rule_name,
             failed_count, total_count, fail_pct, severity

METRIC DEFINITIONS:
- gross_revenue = SUM(quantity × unit_price)
- net_revenue   = gross_revenue − discounts
- gross_profit  = net_revenue − total_cost
- margin_pct    = gross_profit / net_revenue × 100
- aov           = net_revenue / distinct orders
- return_rate_pct = return_count / units_sold × 100
- days_of_cover = available / avg_daily_units (last 30 days)
- rfm_segment: Champions, Loyal, Recent, At Risk, Lost, Potential

RULES:
- Write only a single SELECT statement.
- Always add LIMIT 500 unless the user asks for a specific count.
- Do not reference any table outside the rpt schema.
- Do not use subqueries that reference dw or stg schemas.
- Return results ordered meaningfully.
"""

FEW_SHOT_EXAMPLES = """
Q: Top 5 loss-making products this year?
SQL:
SELECT product_name, category, net_revenue, gross_profit, margin_pct, units_sold
FROM rpt.rpt_profitability_product
WHERE gross_profit < 0
ORDER BY gross_profit ASC
LIMIT 5;

Q: Which stores are at risk of stockouts next week?
SQL:
SELECT store_name, region, product_name, category, available,
       reorder_level, lead_time_days, days_of_cover
FROM rpt.rpt_inventory_health
WHERE is_stockout = FALSE
  AND available <= reorder_level
ORDER BY days_of_cover ASC
LIMIT 50;

Q: Monthly revenue by region for 2025?
SQL:
SELECT year, month, month_name, region,
       SUM(net_revenue) AS net_revenue,
       SUM(gross_profit) AS gross_profit,
       AVG(margin_pct) AS avg_margin_pct
FROM rpt.rpt_sales_monthly_region_category
WHERE year = 2025
GROUP BY year, month, month_name, region
ORDER BY year, month, region
LIMIT 500;
"""

ALLOWED_VIEWS = {
    "rpt.rpt_sales_daily",
    "rpt.rpt_sales_monthly_region_category",
    "rpt.rpt_profitability_product",
    "rpt.rpt_inventory_health",
    "rpt.rpt_customer_rfm",
    "rpt.rpt_customer_cohorts",
    "rpt.rpt_returns_analysis",
    "rpt.rpt_opportunities",
    "rpt.rpt_executive_summary",
    "rpt.rpt_discount_impact",
    "rpt.rpt_inventory_turnover",
    "rpt.rpt_new_vs_returning",
    "rpt.rpt_dq_scorecard",
}


# ── SQL Validator ────────────────────────────────────────────

class SQLValidationError(Exception):
    pass


def validate_sql(sql: str) -> str:
    """
    Enforce guardrails (PRD §10.2):
    - Single SELECT statement only
    - Only allowed views (rpt schema)
    - Must have LIMIT
    - No DML / DDL
    """
    sql = sql.strip().rstrip(";") + ";"
    lower = sql.lower()

    # No DML/DDL – check first, before anything else
    for forbidden in ("insert", "update", "delete", "drop", "create", "alter", "truncate", "grant", "revoke"):
        if re.search(rf"\b{forbidden}\b", lower):
            raise SQLValidationError(f"Forbidden keyword: {forbidden.upper()}")

    # Single statement – split on semicolons
    statements = [s.strip() for s in sql.split(";") if s.strip()]
    if len(statements) > 1:
        raise SQLValidationError("Only a single SQL statement is allowed.")

    # Must start with SELECT
    if not lower.lstrip().startswith("select"):
        raise SQLValidationError("Only SELECT statements are allowed.")

    # Reject any non-rpt schema references (dw, stg, ops, public, pg_catalog, etc.)
    non_rpt = re.findall(r"(?:from|join)\s+((?!rpt\.)\w+\.\w+)", lower)
    if non_rpt:
        raise SQLValidationError(f"References to disallowed tables/views: {set(non_rpt)}")

    # Among rpt.* references, only allow the allow-listed views
    referenced = set(re.findall(r"(?:from|join)\s+(rpt\.\w+)", lower))
    disallowed = referenced - {v.lower() for v in ALLOWED_VIEWS}
    if disallowed:
        raise SQLValidationError(f"References to disallowed tables/views: {disallowed}")

    # Enforce LIMIT
    if "limit" not in lower:
        sql = sql.rstrip(";") + "\nLIMIT 500;"

    return sql


# ── Simple in-memory cache ───────────────────────────────────

_cache: dict[str, tuple[float, Any]] = {}
_CACHE_TTL = 300  # seconds


def _cache_key(question: str) -> str:
    return hashlib.md5(question.lower().strip().encode()).hexdigest()


def _get_cached(question: str) -> Any | None:
    key = _cache_key(question)
    if key in _cache:
        ts, val = _cache[key]
        if time.time() - ts < _CACHE_TTL:
            return val
    return None


def _set_cache(question: str, value: Any) -> None:
    _cache[_cache_key(question)] = (time.time(), value)


# ── Heuristic Intent & Fallback SQL Generator ─────────────────

def _generate_heuristic_sql(question: str) -> str | None:
    """Pattern match common analytics questions to valid SQL when LLM is unavailable."""
    q = question.lower().strip()

    # 1. Loss-making products / negative profit
    if any(k in q for k in ["loss", "loss-making", "negative profit", "negative margin", "least profitable"]) or ("negative" in q and "profit" in q):
        return (
            "SELECT product_name, category, net_revenue, gross_profit, margin_pct, units_sold "
            "FROM rpt.rpt_profitability_product WHERE gross_profit < 0 ORDER BY gross_profit ASC LIMIT 10;"
        )

    # 2. High margin / most profitable products
    if any(k in q for k in ["highest margin", "top margin", "most profitable", "top profitable", "best margin"]):
        return (
            "SELECT product_name, category, net_revenue, gross_profit, margin_pct, profit_rank "
            "FROM rpt.rpt_profitability_product ORDER BY profit_rank ASC LIMIT 10;"
        )

    # 3. Stockout risk / low cover inventory
    if any(k in q for k in ["stockout", "out of stock", "run out", "risk of stockout", "low stock"]):
        return (
            "SELECT store_name, region, product_name, category, available, reorder_level, lead_time_days, days_of_cover "
            "FROM rpt.rpt_inventory_health WHERE is_stockout = TRUE OR available <= reorder_level ORDER BY days_of_cover ASC LIMIT 50;"
        )

    # 4. Overstock
    if any(k in q for k in ["overstock", "excess inventory"]):
        return (
            "SELECT store_name, region, product_name, category, available, days_of_cover "
            "FROM rpt.rpt_inventory_health WHERE is_overstock = TRUE ORDER BY days_of_cover DESC LIMIT 50;"
        )

    # 5. Dead stock
    if any(k in q for k in ["dead stock", "no sales"]):
        return (
            "SELECT store_name, region, product_name, category, on_hand "
            "FROM rpt.rpt_inventory_health WHERE is_dead_stock = TRUE ORDER BY on_hand DESC LIMIT 50;"
        )

    # 6. Inventory turnover
    if any(k in q for k in ["turnover", "inventory turnover", "days to sell"]):
        return (
            "SELECT category, total_cogs, avg_inventory_value, inventory_turnover_ratio, days_to_sell "
            "FROM rpt.rpt_inventory_turnover ORDER BY inventory_turnover_ratio DESC LIMIT 20;"
        )

    # 7. Discount impact
    if "discount" in q and any(k in q for k in ["impact", "margin", "band", "effect"]):
        return (
            "SELECT discount_band, category, orders, units_sold, net_revenue, gross_profit, margin_pct "
            "FROM rpt.rpt_discount_impact ORDER BY orders DESC LIMIT 50;"
        )

    # 8. Return rate / reasons
    if any(k in q for k in ["return rate", "returns", "refund", "return reason"]):
        return (
            "SELECT category, return_reason, reason_group, return_count, total_refund, units_sold, return_rate_pct "
            "FROM rpt.rpt_returns_analysis ORDER BY return_count DESC LIMIT 20;"
        )

    # 9. At-risk / churn-risk customers
    if any(k in q for k in ["at risk", "at-risk", "churn"]) and "customer" in q:
        return (
            "SELECT customer_id, customer_name, region, segment, monetary, recency_days, rfm_segment "
            "FROM rpt.rpt_customer_rfm WHERE rfm_segment = 'At Risk' OR (monetary > 1000 AND recency_days > 90) "
            "ORDER BY monetary DESC LIMIT 50;"
        )

    # 10. RFM segments
    if any(k in q for k in ["rfm", "segment"]) and "customer" in q:
        return (
            "SELECT rfm_segment, COUNT(*) AS customer_count, ROUND(AVG(monetary), 2) AS avg_spend, "
            "ROUND(AVG(recency_days), 1) AS avg_recency FROM rpt.rpt_customer_rfm "
            "GROUP BY rfm_segment ORDER BY customer_count DESC LIMIT 20;"
        )

    # 11. Customer cohorts
    if any(k in q for k in ["cohort", "retention rate", "customer retention"]):
        return (
            "SELECT cohort_month, months_since, cohort_size, active_customers, retention_pct "
            "FROM rpt.rpt_customer_cohorts ORDER BY cohort_month, months_since LIMIT 100;"
        )

    # 12. New vs returning
    if any(k in q for k in ["new vs returning", "returning customer", "new customer", "repeat purchase"]):
        return (
            "SELECT year, month, customer_type, customers "
            "FROM rpt.rpt_new_vs_returning ORDER BY year, month, customer_type LIMIT 50;"
        )

    # 13. Opportunities
    if any(k in q for k in ["opportunit", "growth", "focus on", "next quarter", "reorder candidate"]):
        return (
            "SELECT opportunity_type, entity_name, customer_id, product_id, value, metric_label, region "
            "FROM rpt.rpt_opportunities ORDER BY value DESC LIMIT 50;"
        )

    # 14. Data quality / DQ scorecard
    if any(k in q for k in ["data quality", "dq", "reject rate", "scorecard", "pipeline health"]):
        return (
            "SELECT table_name, rule_name, severity, failed_count, total_count, fail_pct "
            "FROM rpt.rpt_dq_scorecard ORDER BY severity DESC, fail_pct DESC LIMIT 50;"
        )

    # 15. Regional revenue / sales by region
    if "region" in q and any(k in q for k in ["revenue", "sales", "profit", "monthly"]):
        return (
            "SELECT year, month_name, region, SUM(net_revenue) AS net_revenue, SUM(gross_profit) AS gross_profit, "
            "ROUND(AVG(margin_pct), 2) AS avg_margin FROM rpt.rpt_sales_monthly_region_category "
            "GROUP BY year, month_name, region ORDER BY year DESC, net_revenue DESC LIMIT 50;"
        )

    # 16. Category sales
    if any(k in q for k in ["category", "categories"]) and any(k in q for k in ["revenue", "sales", "breakdown", "volume"]):
        return (
            "SELECT year, category, SUM(units_sold) AS units_sold, SUM(net_revenue) AS net_revenue, SUM(gross_profit) AS gross_profit "
            "FROM rpt.rpt_sales_monthly_region_category GROUP BY year, category ORDER BY net_revenue DESC LIMIT 20;"
        )

    # 17. Executive KPIs
    if any(k in q for k in ["executive", "kpi", "summary", "overall revenue", "total sales"]):
        return (
            "SELECT year, month, net_revenue, gross_profit, margin_pct, total_orders, aov, return_rate_pct "
            "FROM rpt.rpt_executive_summary ORDER BY year DESC, month DESC LIMIT 12;"
        )

    # 18. Channel breakdown
    if "channel" in q and any(k in q for k in ["sales", "revenue", "orders", "channel"]):
        return (
            "SELECT channel_name, SUM(orders) AS orders, SUM(units_sold) AS units_sold, SUM(net_revenue) AS net_revenue "
            "FROM rpt.rpt_sales_daily GROUP BY channel_name ORDER BY net_revenue DESC LIMIT 10;"
        )

    return None


def _narrate_data(question: str, df: pd.DataFrame) -> str:
    """Generate a clean narrative from the retrieved dataframe without calculating new numbers."""
    if df.empty:
        return "No records were found matching your criteria in the analytics warehouse."
    n = len(df)
    first_row = df.iloc[0].to_dict()
    cols = df.columns.tolist()
    insights = [f"Retrieved {n} records from the reporting warehouse."]

    if "gross_profit" in cols and "product_name" in cols:
        pname = first_row.get("product_name", "Unknown")
        gp = first_row.get("gross_profit", 0)
        mp = first_row.get("margin_pct", "N/A")
        insights.append(f"Top highlighted product is '{pname}' with gross profit of ${gp:,.2f} (margin: {mp}%).")
    elif "available" in cols and "store_name" in cols:
        sname = first_row.get("store_name", "Unknown")
        reg = first_row.get("region", "N/A")
        avail = first_row.get("available", 0)
        doc = first_row.get("days_of_cover", "N/A")
        insights.append(f"Store '{sname}' ({reg}) has {avail} available units remaining with {doc} days of cover.")
    elif "net_revenue" in cols and "region" in cols:
        total_rev = df["net_revenue"].sum()
        top_reg = first_row.get("region", "N/A")
        top_rev = first_row.get("net_revenue", 0)
        insights.append(f"Total net revenue in this selection is ${total_rev:,.2f}, led by {top_reg} at ${top_rev:,.2f}.")
    elif "return_count" in cols:
        tot_ret = df["return_count"].sum()
        cat = first_row.get("category", "General")
        reason = first_row.get("return_reason", "Various")
        insights.append(f"Total return count is {tot_ret:,}. Highest volume in category '{cat}' due to '{reason}'.")
    elif "customer_count" in cols or "rfm_segment" in cols:
        seg = first_row.get("rfm_segment", "N/A")
        cnt = first_row.get("customer_count", "N/A")
        insights.append(f"Largest segment in this view is '{seg}' with {cnt} customers.")
    else:
        metric = cols[-1]
        val = first_row.get(metric)
        insights.append(f"Leading record '{first_row.get(cols[0])}' has {metric} = {val}.")

    return " ".join(insights)


# ── LLM client ──────────────────────────────────────────────

def _call_llm(prompt: str, system: str = "") -> str:
    """
    Call the configured LLM API. Supports OpenAI-compatible APIs.
    Falls back to empty string if OPENAI_API_KEY is not set.
    """
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        return ""

    try:
        import openai
        client = openai.OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system or "You are a retail analytics SQL expert."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=1024,
            temperature=0,
        )
        return response.choices[0].message.content or ""
    except Exception as e:
        logger.error("LLM call failed: %s", e)
        return ""


# ── Main assistant function ──────────────────────────────────

class AssistantResponse:
    def __init__(self):
        self.question: str = ""
        self.sql: str = ""
        self.data: pd.DataFrame = pd.DataFrame()
        self.answer: str = ""
        self.error: str | None = None
        self.latency_seconds: float = 0.0


def ask(question: str) -> AssistantResponse:
    """
    Process a natural-language question and return an AssistantResponse.
    Uses LLM if OPENAI_API_KEY is present; otherwise falls back to heuristic matching.
    """
    t0 = time.time()
    resp = AssistantResponse()
    resp.question = question

    # Check cache
    cached = _get_cached(question)
    if cached:
        logger.info("Cache hit for question")
        return cached

    # Step 1: Generate SQL
    api_key = os.environ.get("OPENAI_API_KEY", "")
    raw_sql = None

    if api_key:
        sql_prompt = f"""
{SCHEMA_DESCRIPTION}

{FEW_SHOT_EXAMPLES}

Now answer this question with a SQL query:
Q: {question}

Return ONLY the SQL query, no explanation, no markdown fences.
"""
        raw_sql = _call_llm(sql_prompt)
        raw_sql = re.sub(r"```(?:sql)?", "", raw_sql, flags=re.IGNORECASE).strip()

    # If no LLM or LLM returned empty, use heuristic intent matcher
    if not raw_sql:
        raw_sql = _generate_heuristic_sql(question)

    if not raw_sql:
        resp.error = "Could not map question to available reporting views."
        resp.answer = "I was unable to find relevant data in the reporting views to answer that question."
        resp.latency_seconds = time.time() - t0
        return resp

    try:
        validated_sql = validate_sql(raw_sql)
        resp.sql = validated_sql
    except SQLValidationError as e:
        resp.error = f"SQL validation failed: {e}"
        resp.answer = f"I cannot answer that question safely. {resp.error}"
        resp.latency_seconds = time.time() - t0
        return resp

    # Step 2: Execute SQL
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SET statement_timeout = '10s'"))
            result = conn.execute(text(validated_sql))
            rows = result.fetchall()
            cols = result.keys()
        resp.data = pd.DataFrame(rows, columns=cols)
    except Exception as e:
        resp.error = f"Query execution failed: {e}"
        resp.answer = f"The query ran into a database error: {resp.error}"
        resp.latency_seconds = time.time() - t0
        return resp

    # Step 3: Generate narrative answer
    if len(resp.data) == 0:
        resp.answer = "No data was found matching your query in the warehouse."
    else:
        if api_key:
            data_summary = resp.data.head(20).to_string(index=False)
            narrative_prompt = f"""
You are a retail analytics assistant. Based on the following query result,
write a clear, concise plain-English answer to the user's question.

Question: {question}

Query result (first 20 rows of {len(resp.data)} total):
{data_summary}

Rules:
- Reference specific numbers from the data.
- Do NOT calculate new numbers; only describe what the data shows.
- Keep the answer under 150 words.
- If data indicates a problem (e.g., stockout, negative margin), flag it.
- Do not mention the SQL query in your answer.
"""
            llm_narrative = _call_llm(
                narrative_prompt,
                system="You are a concise retail analytics expert writing plain-English summaries."
            )
            resp.answer = llm_narrative or _narrate_data(question, resp.data)
        else:
            resp.answer = _narrate_data(question, resp.data)

    resp.latency_seconds = time.time() - t0
    _set_cache(question, resp)
    logger.info("Question answered in %.1fs", resp.latency_seconds)
    return resp


# ── Driver Analysis: Explain Revenue Changes (PRD §10.1 capability 2) ─────────

def explain_revenue_change(
    year1: int,
    month1: int,
    year2: int,
    month2: int,
    dimension: str = "region"
) -> dict[str, Any]:
    """
    Driver analysis explaining revenue changes between two months (PRD §10.1).
    Decomposes variance into Volume effect, Price effect, and Dimensional contribution.
    """
    if dimension not in ["region", "category"]:
        dimension = "region"

    engine = get_engine()
    sql = f"""
    SELECT
        {dimension} AS dim,
        SUM(CASE WHEN year = :y1 AND month = :m1 THEN net_revenue ELSE 0 END) AS rev1,
        SUM(CASE WHEN year = :y2 AND month = :m2 THEN net_revenue ELSE 0 END) AS rev2,
        SUM(CASE WHEN year = :y1 AND month = :m1 THEN units_sold ELSE 0 END)  AS units1,
        SUM(CASE WHEN year = :y2 AND month = :m2 THEN units_sold ELSE 0 END)  AS units2
    FROM rpt.rpt_sales_monthly_region_category
    WHERE (year = :y1 AND month = :m1) OR (year = :y2 AND month = :m2)
    GROUP BY {dimension}
    ORDER BY rev2 DESC;
    """

    with engine.connect() as conn:
        df = pd.read_sql(text(sql), conn, params={
            "y1": year1, "m1": month1, "y2": year2, "m2": month2
        })

    total_rev1 = float(df["rev1"].sum())
    total_rev2 = float(df["rev2"].sum())
    delta_rev = total_rev2 - total_rev1
    pct_change = (delta_rev / total_rev1 * 100) if total_rev1 else 0.0

    total_units1 = float(df["units1"].sum())
    total_units2 = float(df["units2"].sum())

    avg_p1 = (total_rev1 / total_units1) if total_units1 else 0.0
    avg_p2 = (total_rev2 / total_units2) if total_units2 else 0.0

    # Variance decomposition
    volume_effect = (total_units2 - total_units1) * avg_p1
    price_effect = total_units2 * (avg_p2 - avg_p1)

    # Dimensional contributions
    df["delta_rev"] = df["rev2"] - df["rev1"]
    df["pct_contrib"] = (df["delta_rev"] / abs(delta_rev) * 100) if delta_rev else 0.0
    top_driver = df.sort_values(by="delta_rev", ascending=(delta_rev > 0)).iloc[0].to_dict()

    narrative = (
        f"Revenue shifted from ${total_rev1:,.2f} ({year1}-{month1:02d}) to ${total_rev2:,.2f} ({year2}-{month2:02d}), "
        f"a change of ${delta_rev:+,.2f} ({pct_change:+.1f}%). "
        f"Volume effect contributed ${volume_effect:+,.2f} ({total_units2 - total_units1:+,.0f} units sold). "
        f"Price/realization effect contributed ${price_effect:+,.2f} (avg realized price moved from ${avg_p1:.2f} to ${avg_p2:.2f}). "
        f"The primary driver was {dimension} '{top_driver['dim']}' with a revenue delta of ${top_driver['delta_rev']:+,.2f}."
    )

    return {
        "period1": f"{year1}-{month1:02d}",
        "period2": f"{year2}-{month2:02d}",
        "revenue_period1": total_rev1,
        "revenue_period2": total_rev2,
        "delta_revenue": delta_rev,
        "pct_change": pct_change,
        "volume_effect": volume_effect,
        "price_effect": price_effect,
        "top_driver": top_driver["dim"],
        "top_driver_delta": top_driver["delta_rev"],
        "breakdown": df.to_dict(orient="records"),
        "narrative": narrative,
    }


# ── Narrative report generator ───────────────────────────────

def generate_weekly_summary() -> str:
    """
    Compute key metrics in SQL first, then have LLM write the narrative.
    The LLM never calculates; it only narrates.
    """
    engine = get_engine()
    metrics: dict[str, Any] = {}

    with engine.connect() as conn:
        # Revenue this week vs last week
        row = conn.execute(text("""
            SELECT
                SUM(CASE WHEN sale_date >= CURRENT_DATE - 7 THEN net_revenue END)  AS this_week,
                SUM(CASE WHEN sale_date >= CURRENT_DATE - 14
                          AND sale_date < CURRENT_DATE - 7  THEN net_revenue END)  AS last_week,
                SUM(CASE WHEN sale_date >= CURRENT_DATE - 7 THEN gross_profit END) AS this_week_profit,
                SUM(CASE WHEN sale_date >= CURRENT_DATE - 7 THEN orders END)       AS this_week_orders
            FROM rpt.rpt_sales_daily
            WHERE sale_date >= CURRENT_DATE - 14
        """)).fetchone()
        if row:
            metrics["this_week_revenue"] = row[0] or 0
            metrics["last_week_revenue"] = row[1] or 0
            metrics["this_week_profit"] = row[2] or 0
            metrics["this_week_orders"] = row[3] or 0

        # Top region this week
        top_region = conn.execute(text("""
            SELECT region, SUM(net_revenue) AS rev
            FROM rpt.rpt_sales_daily
            WHERE sale_date >= CURRENT_DATE - 7
            GROUP BY region ORDER BY rev DESC LIMIT 1
        """)).fetchone()
        if top_region:
            metrics["top_region"] = top_region[0]
            metrics["top_region_revenue"] = top_region[1]

        # Stockout count
        stockouts = conn.execute(text("""
            SELECT COUNT(*) FROM rpt.rpt_inventory_health WHERE is_stockout = TRUE
        """)).scalar()
        metrics["stockout_count"] = stockouts or 0

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if api_key:
        prompt = f"""
Write a concise executive weekly summary for a retail company based on these pre-computed metrics:
{json.dumps(metrics, indent=2, default=str)}

Format:
- 3-4 bullet points
- Reference exact numbers
- Highlight anything that needs attention
- Tone: professional, brief
"""
        try:
            return _call_llm(prompt, system="You are a retail analytics expert writing executive summaries.")
        except Exception as e:
            pass

    # Heuristic fallback summary
    rev_this = metrics.get('this_week_revenue', 0)
    rev_last = metrics.get('last_week_revenue', 0)
    diff = rev_this - rev_last
    pct = (diff / rev_last * 100) if rev_last else 0.0
    return (
        f"### Executive Weekly Performance Summary\n\n"
        f"• **Revenue Performance**: Net revenue this week reached ${rev_this:,.2f} "
        f"({diff:+,.2f} / {pct:+.1f}% vs prior week).\n"
        f"• **Operational Activity**: Processed {metrics.get('this_week_orders', 0):,} orders "
        f"yielding ${metrics.get('this_week_profit', 0):,.2f} in gross profit.\n"
        f"• **Regional Driver**: Top performing region was **{metrics.get('top_region', 'N/A')}** "
        f"generating ${metrics.get('top_region_revenue', 0):,.2f}.\n"
        f"• **Inventory Health**: Currently monitoring **{metrics.get('stockout_count', 0)} active stockouts** "
        f"across store locations."
    )

