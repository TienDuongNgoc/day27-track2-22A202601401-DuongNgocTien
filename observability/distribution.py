"""Distribution shift detector.

Combines robust empirical Kolmogorov-Smirnov 2-sample statistic and central-tendency
ratio to detect both shape/variance shifts and magnitude drifts.
"""
from __future__ import annotations

from typing import Any, Iterable

import numpy as np


def _ks_statistic(cur: np.ndarray, base: np.ndarray) -> float:
    """Calculate 2-sample Kolmogorov-Smirnov distance."""
    if cur.size == 0 or base.size == 0:
        return 0.0
    cur_sorted = np.sort(cur)
    base_sorted = np.sort(base)
    all_vals = np.concatenate([cur_sorted, base_sorted])
    cdf_cur = np.searchsorted(cur_sorted, all_vals, side="right") / cur.size
    cdf_base = np.searchsorted(base_sorted, all_vals, side="right") / base.size
    return float(np.max(np.abs(cdf_cur - cdf_base)))


def detect_distribution_shift(
    current_values: Iterable[float],
    baseline_values: Iterable[float],
    *,
    ratio_threshold: float = 3.0,
    ks_threshold: float = 0.45,
) -> dict[str, Any]:
    cur = np.asarray(list(current_values), dtype=float)
    base = np.asarray(list(baseline_values), dtype=float)

    if cur.size == 0 or base.size == 0:
        return {"is_anomaly": False, "score": 0.0, "method": "ks_and_ratio", "reason": "empty_input"}

    cur_mean = float(np.mean(cur))
    base_mean = float(np.mean(base))

    # 1. Mean ratio calculation
    if base_mean == 0:
        ratio = float("inf") if cur_mean != 0 else 1.0
    else:
        ratio = max(abs(cur_mean / base_mean), abs(base_mean / cur_mean)) if cur_mean != 0 else float("inf")

    # 2. Kolmogorov-Smirnov shape distance
    ks_stat = _ks_statistic(cur, base)

    # 3. Overall anomaly decision
    ratio_anomaly = bool(ratio >= ratio_threshold)
    ks_anomaly = bool(ks_stat >= ks_threshold and cur.size >= 4 and base.size >= 4)
    is_anomaly = ratio_anomaly or ks_anomaly

    score = float(ratio) if not np.isinf(ratio) else (ks_stat * ratio_threshold if ks_anomaly else 10.0)

    return {
        "is_anomaly": is_anomaly,
        "score": score,
        "method": "ks_and_ratio",
        "ks_statistic": round(ks_stat, 4),
        "mean_ratio": round(ratio, 4) if not np.isinf(ratio) else float("inf"),
        "reason": f"ks_stat={ks_stat:.3f}, ratio={ratio:.2f}, baseline_mean={base_mean:.2f}, current_mean={cur_mean:.2f}",
    }
