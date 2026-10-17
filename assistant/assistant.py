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


# ── LLM client ──────────────────────────────────────────────

def _call_llm(prompt: str, system: str = "") -> str:
    """
    Call the configured LLM API. Supports OpenAI-compatible APIs.
    Falls back to a stub if OPENAI_API_KEY is not set.
    """
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        logger.warning("OPENAI_API_KEY not set. Returning stub response.")
        return "-- STUB: Set OPENAI_API_KEY to enable AI responses.\nSELECT 'No API key configured' AS message LIMIT 1;"

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
        raise


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
    sql_prompt = f"""
{SCHEMA_DESCRIPTION}

{FEW_SHOT_EXAMPLES}

Now answer this question with a SQL query:
Q: {question}

Return ONLY the SQL query, no explanation, no markdown fences.
"""
    try:
        raw_sql = _call_llm(sql_prompt)
        # Strip markdown code fences if present
        raw_sql = re.sub(r"```(?:sql)?", "", raw_sql, flags=re.IGNORECASE).strip()
        validated_sql = validate_sql(raw_sql)
        resp.sql = validated_sql
    except SQLValidationError as e:
        resp.error = f"SQL validation failed: {e}"
        resp.answer = f"I cannot answer that question safely. {resp.error}"
        resp.latency_seconds = time.time() - t0
        return resp
    except Exception as e:
        resp.error = f"SQL generation failed: {e}"
        resp.answer = "I was unable to generate a valid SQL query for this question."
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
        resp.answer = f"The query ran into a database error. {resp.error}"
        resp.latency_seconds = time.time() - t0
        return resp

    # Step 3: Generate narrative answer
    if len(resp.data) == 0:
        resp.answer = "No data was found matching your query. The result set was empty."
    else:
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
        try:
            resp.answer = _call_llm(
                narrative_prompt,
                system="You are a concise retail analytics expert writing plain-English summaries."
            )
        except Exception as e:
            resp.answer = f"Data retrieved successfully ({len(resp.data)} rows). Unable to generate narrative: {e}"

    resp.latency_seconds = time.time() - t0
    _set_cache(question, resp)
    logger.info("Question answered in %.1fs", resp.latency_seconds)
    return resp


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
        return f"Weekly summary unavailable: {e}\n\nRaw metrics:\n{json.dumps(metrics, indent=2, default=str)}"
