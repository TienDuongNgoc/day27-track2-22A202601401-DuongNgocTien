from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports" / "latest_metrics.json"
HISTORY = ROOT / "data" / "history" / "metrics_history.csv"

st.set_page_config(
    page_title="Data Reliability Command Center",
    page_icon="🛡️",
    layout="wide",
)

st.title("🛡️ Data Reliability Command Center")
st.caption("Real-time Data Observability, Contracts, SLO Error Budgets & Incident Blast Radius")

if not REPORT.exists():
    st.warning("⚠️ Baseline report not found. Please run `make baseline` first.")
    st.stop()

report = json.loads(REPORT.read_text(encoding="utf-8"))

# Top KPI Summary Cards
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("📦 Orders Ingested", f"{report.get('orders_rows', 0):,}")
c2.metric("⏱️ Orders Freshness", f"{report.get('freshness_minutes', 0.0):.1f} min")
c3.metric("📑 KB Documents", f"{report.get('kb_documents_count', 5)}")
c4.metric("🚨 Contract Failures", report.get("failed_contract_checks", 0), delta=f"-{report.get('critical_contract_failures', 0)} critical", delta_color="inverse")

burn_eval = report.get("burn_evaluation", {})
page_alert = burn_eval.get("page", False)
sev = burn_eval.get("severity", "info").upper()
c5.metric("🔔 SRE Alert State", sev, delta="PAGING" if page_alert else "NORMAL", delta_color="inverse" if page_alert else "normal")

st.divider()

# Tab Layout
tab1, tab2, tab3, tab4 = st.tabs(["📊 Reliability Overview", "🎯 SLO & Error Budgets", "🔍 Lineage & Blast Radius", "📜 Active Runbooks & Log"])

with tab1:
    col_left, col_right = st.columns([1, 1])

    with col_left:
        st.subheader("⚡ Signal Health Matrix")
        
        row_anomaly = report.get("row_count_anomaly", {})
        is_row_anomaly = row_anomaly.get("is_anomaly", False)
        st.markdown(f"**Row-count Anomaly:** {'🔴 DETECTED' if is_row_anomaly else '🟢 NORMAL'} "
                    f"*(Method: `{row_anomaly.get('method')}`, Score: `{row_anomaly.get('score', 0):.2f}`)*")

        kb_anomaly = report.get("kb_text_length_signal", {}).get("is_anomaly", False)
        st.markdown(f"**KB Length Drift:** {'🔴 DETECTED' if kb_anomaly else '🟢 NORMAL'}")

        kb_fresh = report.get("kb_freshness_minutes", 0.0)
        st.markdown(f"**KB Freshness Delay:** `{kb_fresh:.1f} min` (SLA threshold: `60 min`)")

        st.json({
            "row_count_detector": row_anomaly,
            "kb_signal": report.get("kb_text_length_signal"),
        })

    with col_right:
        st.subheader("📈 Ingestion Volume History")
        if HISTORY.exists():
            history_df = pd.read_csv(HISTORY)
            st.line_chart(history_df.set_index("date")[["row_count", "avg_amount"]])

with tab2:
    st.subheader("🎯 Service Level Objectives (SLO) & Burn Rates")
    slo_col1, slo_col2 = st.columns(2)

    with slo_col1:
        st.markdown("### Orders Contract SLO (Target: 99.9%)")
        contract_slo = report.get("contract_slo", {})
        st.metric("Allowed Bad Rate", f"{contract_slo.get('allowed_bad_rate', 0.001) * 100:.3f}%")
        st.metric("Actual Bad Rate", f"{contract_slo.get('actual_bad_rate', 0.0) * 100:.3f}%")
        st.metric("Normalized Burn Rate", f"{contract_slo.get('burn_rate', 0.0):.2f}x")
        st.metric("Remaining Budget", f"{contract_slo.get('remaining_error_budget_fraction', 1.0) * 100:.1f}%")

    with slo_col2:
        st.markdown("### SRE Multi-Window Alert Policy")
        st.info(f"**Policy:** `{burn_eval.get('policy', 'sre_multiwindow')}`\n\n"
                f"- **Short-window Burn:** `{burn_eval.get('short_window_burn', 0.0):.2f}x`\n"
                f"- **Long-window Burn:** `{burn_eval.get('long_window_burn', 0.0):.2f}x`\n"
                f"- **On-Call Paging:** `{'YES 🚨' if page_alert else 'NO ✅'}`\n"
                f"- **Reason:** `{burn_eval.get('reason', 'healthy')}`")

with tab3:
    st.subheader("🕸️ Lineage Graph & Blast Radius Analysis")
    blast = report.get("sample_blast_radius_from_stg_orders", [])
    st.success(f"**Root Node:** `stg_orders` ➔ **Downstream Impact:** `{' ➔ '.join(blast)}`")
    
    st.markdown("""
    ```text
    orders.csv (Raw Ingestion)
      └── stg_orders (Staging View)
            ├── fct_daily_revenue (Marts Table)
            │     └── CEO Revenue Dashboard
            └── fct_orders (Downstream Analytics)
    ```
    """)

with tab4:
    st.subheader("📖 Quick Incident Remediation Runbook")
    st.markdown("""
    1. **Duplicate PK Detected:** Execute `quarantine_records()` to isolate bad records; check upstream webhook idempotency.
    2. **Volume Drop Detected:** Check ingestion source health; compare with same-weekday historical traffic before blocking.
    3. **Stale Knowledge Base:** Trigger CMS sync crawler and refresh RAG vector store.
    4. **SCD Duplication in Marts:** Use deduplicated dimensions (`distinct customer_id`) in `fct_daily_revenue.sql`.
    """)
