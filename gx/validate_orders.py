#!/usr/bin/env python3
"""Great Expectations Core 1.21.0 Expectation Suite, Validation Definition, and Checkpoint.

Packages expectations into a reusable Expectation Suite, connects it to a BatchDefinition
via ValidationDefinition, and runs a Checkpoint with severity evaluation.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    import great_expectations as gx
except ImportError as exc:
    raise SystemExit("great_expectations is not installed. Run: pip install -r requirements.txt") from exc


def build_and_run_gx_suite(df: pd.DataFrame | None = None) -> bool:
    if df is None:
        orders_path = ROOT / "data" / "incoming" / "orders.csv"
        if not orders_path.exists():
            orders_path = ROOT / "data" / "baseline" / "orders.csv"
        df = pd.read_csv(orders_path)

    context = gx.get_context(mode="ephemeral")

    # 1. Data Source and Asset setup
    data_source = context.data_sources.add_pandas("orders_data_source")
    asset = data_source.add_dataframe_asset(name="orders_asset")
    batch_definition = asset.add_batch_definition_whole_dataframe("whole_dataframe_batch")

    # 2. Expectation Suite setup
    suite = gx.ExpectationSuite(name="orders_expectation_suite")
    suite.add_expectation(
        gx.expectations.ExpectColumnValuesToNotBeNull(
            column="order_id",
            notes="Order ID must not be null (Critical)",
        )
    )
    suite.add_expectation(
        gx.expectations.ExpectColumnValuesToBeUnique(
            column="order_id",
            notes="Order ID must be unique (Critical)",
        )
    )
    suite.add_expectation(
        gx.expectations.ExpectColumnValuesToNotBeNull(
            column="customer_id",
            notes="Customer ID is required",
        )
    )
    suite.add_expectation(
        gx.expectations.ExpectColumnValuesToBeBetween(
            column="amount",
            min_value=0,
            notes="Order amount cannot be negative (Critical)",
        )
    )
    suite.add_expectation(
        gx.expectations.ExpectColumnValuesToBeInSet(
            column="currency",
            value_set=["USD", "VND"],
            notes="Currency must be USD or VND",
        )
    )
    suite.add_expectation(
        gx.expectations.ExpectColumnValuesToBeInSet(
            column="status",
            value_set=["pending", "completed", "refunded", "cancelled"],
            notes="Valid order statuses",
        )
    )
    context.suites.add(suite)

    # 3. Validation Definition setup
    validation_definition = gx.ValidationDefinition(
        name="orders_validation_definition",
        data=batch_definition,
        suite=suite,
    )
    context.validation_definitions.add(validation_definition)

    # 4. Checkpoint setup
    checkpoint = gx.Checkpoint(
        name="orders_checkpoint",
        validation_definitions=[validation_definition],
        result_format={"result_format": "SUMMARY"},
    )
    context.checkpoints.add(checkpoint)

    # 5. Run Checkpoint
    checkpoint_result = checkpoint.run(
        batch_parameters={"dataframe": df}
    )

    all_passed = bool(checkpoint_result.success)
    print("\n=== GREAT EXPECTATIONS SUITE & CHECKPOINT RESULTS ===")
    print(f"Suite: {suite.name}")
    print(f"Checkpoint Success: {all_passed}")

    # Inspect individual expectation results
    for val_result in checkpoint_result.run_results.values():
        for res in val_result.results:
            exp_type = res.expectation_config.type
            kwargs = res.expectation_config.kwargs
            success = res.success
            status_icon = "PASS" if success else "FAIL"
            print(f"  [{status_icon:<4}] {exp_type:<35} kwargs={kwargs}")

    action = "PROCEED" if all_passed else "BLOCK_OR_QUARANTINE"
    print(f"\nAction recommendation: {action}")
    return all_passed


def main() -> None:
    success = build_and_run_gx_suite()
    print("\nFinal GX Result:", "PASS" if success else "FAIL")


if __name__ == "__main__":
    main()
