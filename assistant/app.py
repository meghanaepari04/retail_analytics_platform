"""
Streamlit chat interface for the Retail AI Insight Assistant (PRD §10.2)
Usage: streamlit run assistant/app.py
"""
from __future__ import annotations

import sys
import os

# Ensure package root is on path when run from project directory
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import streamlit as st
import pandas as pd
from assistant.assistant import ask, generate_weekly_summary

# ── Page config ─────────────────────────────────────────────
st.set_page_config(
    page_title="Retail AI Assistant",
    page_icon="🛍️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ───────────────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    .main { background: #0f1117; }
    .stChatMessage { border-radius: 12px; }
    .metric-card {
        background: linear-gradient(135deg, #1a1f36 0%, #2d3561 100%);
        border-radius: 12px; padding: 16px; margin: 8px 0;
        border: 1px solid rgba(255,255,255,0.08);
    }
    .sql-box {
        background: #1e1e2e; border-radius: 8px; padding: 12px;
        border-left: 3px solid #7c3aed; font-family: monospace;
        font-size: 0.85rem; white-space: pre-wrap;
    }
    .answer-box {
        background: linear-gradient(135deg, #064e3b 0%, #065f46 100%);
        border-radius: 8px; padding: 16px; margin: 12px 0;
        border-left: 3px solid #10b981;
    }
</style>
""", unsafe_allow_html=True)

# ── Sidebar ──────────────────────────────────────────────────
with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/shopping-cart.png", width=60)
    st.title("Retail AI Assistant")
    st.markdown("Ask questions in plain English about sales, inventory, customers, and more.")
    st.divider()

    st.subheader("📋 Example Questions")
    examples = [
        "Top 5 loss-making products this year?",
        "Which stores risk stockouts next week?",
        "Monthly revenue by region for 2025?",
        "Who are our at-risk high-value customers?",
        "What's our return rate by category?",
        "Which categories are growing fastest?",
    ]
    for ex in examples:
        if st.button(ex, use_container_width=True, key=f"ex_{ex[:20]}"):
            st.session_state.pending_question = ex

    st.divider()
    if st.button("📊 Generate Weekly Summary", use_container_width=True):
        with st.spinner("Generating executive summary…"):
            summary = generate_weekly_summary()
        st.session_state.weekly_summary = summary

    st.divider()
    st.caption("🔒 Read-only · rpt schema only · No PII")

# ── Main area ────────────────────────────────────────────────
st.markdown("# 🛍️ Retail Analytics AI Assistant")
st.markdown("Ask anything about sales, profitability, inventory, customers, or returns.")

if "messages" not in st.session_state:
    st.session_state.messages = []

if "weekly_summary" in st.session_state:
    with st.expander("📊 Weekly Executive Summary", expanded=True):
        st.markdown(st.session_state.weekly_summary)
    del st.session_state.weekly_summary

# Display chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if "sql" in msg:
            with st.expander("🔍 SQL Used"):
                st.code(msg["sql"], language="sql")
        if "data" in msg and not msg["data"].empty:
            with st.expander(f"📊 Data ({len(msg['data'])} rows)"):
                st.dataframe(msg["data"], use_container_width=True)

# Handle pending question from sidebar examples
if "pending_question" in st.session_state:
    question = st.session_state.pop("pending_question")
else:
    question = st.chat_input("Ask a question about your retail data…")

if question:
    # Show user message
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    # Get answer
    with st.chat_message("assistant"):
        with st.spinner("Analyzing data…"):
            resp = ask(question)

        if resp.error:
            st.error(f"❌ {resp.error}")
            msg = {"role": "assistant", "content": f"❌ {resp.error}"}
        else:
            # Answer
            st.markdown(f"""<div class="answer-box">{resp.answer}</div>""", unsafe_allow_html=True)

            # SQL
            with st.expander("🔍 SQL Used"):
                st.code(resp.sql, language="sql")

            # Data table
            if not resp.data.empty:
                with st.expander(f"📊 Data ({len(resp.data)} rows)"):
                    st.dataframe(resp.data, use_container_width=True)

            st.caption(f"⏱ {resp.latency_seconds:.1f}s")
            msg = {
                "role": "assistant",
                "content": resp.answer,
                "sql": resp.sql,
                "data": resp.data,
            }

        st.session_state.messages.append(msg)
