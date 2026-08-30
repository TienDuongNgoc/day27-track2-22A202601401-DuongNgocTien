#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from observability.anomaly import detect_anomaly
from observability.lineage import get_downstream_assets
from observability.rag_metrics import detect_text_length_shift
from observability.slo import calculate_slo, evaluate_multiwindow_burn
from src.contract_validator import failed_issues, load_contract, validate_dataframe
from src.io_utils import load_jsonl


def main() -> None:
    orders = pd.read_csv(ROOT / "data" / "incoming" / "orders.csv")
    history = pd.read_csv(ROOT / "data" / "history" / "metrics_history.csv")
    contract = load_contract(ROOT / "contracts" / "orders_contract.yaml")
    issues = validate_dataframe(orders, contract)
    failed = failed_issues(issues)
    critical_failed = failed_issues(issues, min_severity="critical")

    # Segment by weekday with context-aware anomaly detector
    current_dow = datetime.now().weekday()
    segment = history.loc[history["day_of_week"] == current_dow, "row_count"].tail(8).tolist()
    row_history = segment if len(segment) >= 3 else history["row_count"].tail(14).tolist()
    row_result = detect_anomaly(
        len(orders),
        row_history,
        method="auto",
        context={"metric_name": "row_count", "day_of_week": current_dow, "same_segment_history": segment},
    )

    updated = pd.to_datetime(orders["updated_at"], utc=True, errors="coerce")
    freshness_minutes = (
        pd.Timestamp(datetime.now(timezone.utc)) - updated.max()
    ).total_seconds() / 60.0

    # Knowledge Base Validation & Metrics
    docs = load_jsonl(ROOT / "data" / "incoming" / "kb_documents.jsonl")
    kb_df = pd.DataFrame(docs)
    kb_contract = load_contract(ROOT / "contracts" / "kb_contract.yaml")
    kb_issues = validate_dataframe(kb_df, kb_contract)
    kb_failed = failed_issues(kb_issues)
    kb_freshness_issue = [i for i in kb_issues if i["check"] == "freshness"]
    kb_freshness_delay = (
        float(kb_freshness_issue[0]["details"].split("delay_minutes=")[1].split(";")[0])
        if kb_freshness_issue
        else 0.0
    )

    text_result = detect_text_length_shift(
        [d["content"] for d in docs], history["mean_text_length"].tail(14).tolist()
    )

    # Demo SLO calculations
    bad_order_events = 1 if critical_failed else 0
    contract_slo = calculate_slo(0.999, bad_events=bad_order_events, total_events=1)

    bad_kb_events = 1 if any(not i.get("passed", True) for i in kb_issues) else 0
    rag_slo = calculate_slo(0.99, bad_events=bad_kb_events, total_events=1)

    burn_evaluation = evaluate_multiwindow_burn(
        short_window_burn=contract_slo["burn_rate"],
        long_window_burn=contract_slo["burn_rate"] * 0.8,
    )

    with open(ROOT / "data" / "baseline" / "lineage_graph.json", "r", encoding="utf-8") as f:
        lineage = json.load(f)["dataset_lineage"]
    blast_radius = get_downstream_assets(lineage, "stg_orders")

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "orders_rows": int(len(orders)),
        "failed_contract_checks": len(failed),
        "critical_contract_failures": len(critical_failed),
        "row_count_anomaly": row_result,
        "freshness_minutes": freshness_minutes,
        "kb_documents_count": len(docs),
        "kb_failed_contract_checks": len(kb_failed),
        "kb_freshness_minutes": kb_freshness_delay,
        "kb_text_length_signal": text_result,
        "contract_slo": contract_slo,
        "rag_slo": rag_slo,
        "burn_evaluation": burn_evaluation,
        "sample_blast_radius_from_stg_orders": blast_radius,
    }
    out = ROOT / "reports" / "latest_metrics.json"
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    print("=== DATA RELIABILITY BASELINE ===")
    print(f"orders rows              : {len(orders)}")
    print(f"orders failed checks     : {len(failed)} (critical: {len(critical_failed)})")
    print(f"row-count anomaly        : {row_result['is_anomaly']} ({row_result['method']}, score={row_result['score']:.2f})")
    print(f"orders freshness minutes : {freshness_minutes:.1f}")
    print(f"KB docs / failed checks  : {len(docs)} / {len(kb_failed)}")
    print(f"KB freshness delay min   : {kb_freshness_delay:.1f}")
    print(f"KB length anomaly        : {text_result['is_anomaly']}")
    print(f"contract SLO burn rate   : {contract_slo['burn_rate']:.2f} (breached: {contract_slo['breached']})")
    print(f"burn alert evaluation    : page={burn_evaluation['page']}, severity={burn_evaluation['severity']}")
    print(f"sample blast radius      : {', '.join(blast_radius)}")
    print(f"report                   : {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
