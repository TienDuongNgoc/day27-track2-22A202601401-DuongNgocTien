"""Comprehensive test suite verifying all upgraded modules:
- Contract type drift, freshness, quarantine
- Statistical MAD zero-edge cases & context-aware auto seasonality
- Distribution 2-sample KS drift
- Column transitive multi-hop lineage
- SRE Multi-window burn rate alert policies
- RAG embedding norm drift
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import pandas as pd
import pytest

from student_api import (
    column_downstream,
    detect_distribution,
    detect_metric,
    downstream_assets,
    multiwindow_burn,
    rag_embedding_shift,
    rag_length_shift,
    slo_status,
    validate_orders,
)
from src.contract_validator import quarantine_records

ROOT = Path(__file__).resolve().parents[1]
ORDERS_CONTRACT = ROOT / "contracts" / "orders_contract.yaml"
KB_CONTRACT = ROOT / "contracts" / "kb_contract.yaml"


def test_contract_type_drift_detection():
    """Verify that string in numeric amount or invalid dates are detected as type errors."""
    now = datetime.now(timezone.utc)
    df = pd.DataFrame([
        {
            "order_id": 101,
            "customer_id": "C001",
            "amount": "NOT_A_NUMBER",  # type drift
            "currency": "USD",
            "status": "completed",
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }
    ])
    issues = validate_orders(df, ORDERS_CONTRACT)
    failed = [i for i in issues if not i["passed"]]
    assert any(i["check"] == "type" and i["column"] == "amount" for i in failed)


def test_contract_quarantine_splitting():
    """Verify that quarantine_records cleanly splits clean from invalid rows."""
    now = datetime.now(timezone.utc)
    df = pd.DataFrame([
        {
            "order_id": 1,
            "customer_id": "C1",
            "amount": 100.0,
            "currency": "USD",
            "status": "completed",
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        },
        {
            "order_id": 2,
            "customer_id": "C2",
            "amount": -50.0,  # invalid negative range
            "currency": "USD",
            "status": "completed",
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        },
        {
            "order_id": 1,  # duplicate order_id
            "customer_id": "C3",
            "amount": 20.0,
            "currency": "USD",
            "status": "completed",
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }
    ])
    import yaml
    with open(ORDERS_CONTRACT, "r", encoding="utf-8") as f:
        contract = yaml.safe_load(f)
    clean, quarantined = quarantine_records(df, contract)
    assert len(quarantined) >= 2


def test_mad_zero_edge_case():
    """Test MAD detector when majority history is constant."""
    history = [100.0, 100.0, 100.0, 100.0, 100.0, 100.0]
    # Anomaly when current differs
    res1 = detect_metric(150.0, history, method="mad")
    assert res1["is_anomaly"] is True

    # Not anomaly when current is identical
    res2 = detect_metric(100.0, history, method="mad")
    assert res2["is_anomaly"] is False


def test_auto_context_seasonality():
    """Test auto detector using same_segment_history in context."""
    # Weekend row count is typically 200, weekday is 1000
    weekday_history = [1000, 1020, 990, 1010, 995, 1005]
    saturday_history = [200, 210, 195, 205, 202]

    # Saturday drop to 205 is normal if using saturday segment history
    res = detect_metric(
        205,
        weekday_history,
        method="auto",
        context={"day_of_week": 5, "same_segment_history": saturday_history},
    )
    assert res["is_anomaly"] is False


def test_distribution_ks_statistic():
    """Test distribution detector with identical vs shifted shape."""
    base = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    cur_same = [1.1, 1.9, 3.2, 4.1, 4.9, 6.0, 7.2, 7.9, 9.1, 10.0]
    cur_shifted = [50.0, 52.0, 49.0, 51.0, 53.0, 50.0, 48.0]

    assert detect_distribution(cur_same, base)["is_anomaly"] is False
    assert detect_distribution(cur_shifted, base)["is_anomaly"] is True


def test_transitive_column_lineage():
    """Test multi-hop column lineage traversal."""
    col_graph = {
        "raw_orders.order_id": ["stg_orders.order_id"],
        "stg_orders.order_id": ["fct_daily_revenue.completed_order_rows", "fct_orders.order_id"],
        "fct_daily_revenue.completed_order_rows": ["dashboard.total_orders"],
    }
    result = column_downstream(col_graph, "raw_orders.order_id")
    assert "stg_orders.order_id" in result
    assert "fct_daily_revenue.completed_order_rows" in result
    assert "dashboard.total_orders" in result


def test_sre_multiwindow_burn_rate():
    """Test SRE Multi-window Burn Rate Alert Policies."""
    # 1. Transient Spike (short burn high, long burn low) -> DO NOT PAGE
    spike = multiwindow_burn(short_window_burn=14.0, long_window_burn=1.2)
    assert spike["page"] is False
    assert spike["severity"] == "warning"

    # 2. Sustained Fast Burn (both short and long high) -> PAGE
    sustained = multiwindow_burn(short_window_burn=14.0, long_window_burn=12.0)
    assert sustained["page"] is True
    assert sustained["severity"] == "critical"

    # 3. Healthy (both low)
    healthy = multiwindow_burn(short_window_burn=0.5, long_window_burn=0.4)
    assert healthy["page"] is False
    assert healthy["severity"] == "info"


def test_rag_embedding_norm_shift():
    """Test RAG vector embedding norm shift detector."""
    baseline = [1.0, 1.02, 0.98, 1.01, 0.99, 1.0]
    current_shifted = [5.5, 5.8, 5.2]
    current_normal = [1.01, 0.99, 1.0]

    assert rag_embedding_shift(current_shifted, baseline)["is_anomaly"] is True
    assert rag_embedding_shift(current_normal, baseline)["is_anomaly"] is False
