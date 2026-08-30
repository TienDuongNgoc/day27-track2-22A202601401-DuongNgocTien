"""Anomaly detection module for Data Reliability Lab.

Provides:
- Z-score detector (parametric baseline)
- MAD detector (Median Absolute Deviation, robust against outliers and handles zero-MAD edge cases)
- Context-aware auto detector supporting seasonality (day_of_week, same_segment_history),
  known events, and statistical distribution properties.
"""
from __future__ import annotations

from typing import Any, Iterable

import numpy as np


def zscore_detector(current: float, history: Iterable[float], threshold: float = 3.0) -> dict[str, Any]:
    values = np.asarray(list(history), dtype=float)
    if values.size < 3:
        return {"is_anomaly": False, "score": 0.0, "method": "zscore", "reason": "insufficient_history"}
    mean = float(np.mean(values))
    std = float(np.std(values))
    if std == 0:
        score = float("inf") if float(current) != mean else 0.0
    else:
        score = abs(float(current) - mean) / std
    return {
        "is_anomaly": bool(score > threshold),
        "score": float(score),
        "method": "zscore",
        "reason": f"mean={mean:.3f}, std={std:.3f}, threshold={threshold}",
    }


def mad_detector(current: float, history: Iterable[float], threshold: float = 3.5) -> dict[str, Any]:
    """Robust MAD detector handling zero-MAD edge cases cleanly."""
    values = np.asarray(list(history), dtype=float)
    if values.size < 3:
        return {"is_anomaly": False, "score": 0.0, "method": "mad", "reason": "insufficient_history"}
    median = float(np.median(values))
    abs_diffs = np.abs(values - median)
    mad = float(np.median(abs_diffs))

    if mad == 0:
        mean_ad = float(np.mean(abs_diffs))
        if mean_ad == 0:
            # Constant history
            score = float("inf") if float(current) != median else 0.0
        else:
            # Fallback to mean absolute deviation
            score = 0.6745 * abs(float(current) - median) / mean_ad
    else:
        score = 0.6745 * abs(float(current) - median) / mad

    return {
        "is_anomaly": bool(score > threshold),
        "score": float(score),
        "method": "mad",
        "reason": f"median={median:.3f}, mad={mad:.3f}, threshold={threshold}",
    }


def detect_anomaly(
    current: float,
    history: Iterable[float],
    *,
    method: str = "auto",
    threshold: float = 3.0,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Context-aware anomaly detector for data metrics.

    Supports:
    - explicit methods: 'zscore', 'mad'
    - 'auto': context-aware routing, taking into account segmented histories (e.g. day of week),
      robust statistics (MAD), and handling non-stationary patterns.
    """
    if method == "zscore":
        return zscore_detector(current, history, threshold=threshold)
    if method == "mad":
        return mad_detector(current, history, threshold=threshold)

    if method == "auto":
        hist_list = list(history)

        # 1. Use same-segment history if provided in context (seasonality / segment aware)
        if context:
            if "same_segment_history" in context and context["same_segment_history"]:
                seg_hist = list(context["same_segment_history"])
                if len(seg_hist) >= 3:
                    hist_list = seg_hist

            # If a known planned event occurred (e.g. sale, migration), relax threshold
            if context.get("known_event"):
                threshold = threshold * 1.5

        if len(hist_list) < 3:
            return {
                "is_anomaly": False,
                "score": 0.0,
                "method": "auto:insufficient_data",
                "reason": "insufficient history points",
            }

        # 2. Run both MAD (robust) and Z-score detectors
        mad_res = mad_detector(current, hist_list, threshold=threshold)
        z_res = zscore_detector(current, hist_list, threshold=threshold)

        # Prefer MAD when outliers might distort mean/std, but fall back to Z-score
        chosen = mad_res if not np.isinf(mad_res["score"]) else z_res
        is_anomaly = bool(mad_res["is_anomaly"] or z_res["is_anomaly"])
        max_score = float(max(mad_res["score"], z_res["score"])) if not np.isinf(mad_res["score"]) else float(z_res["score"])

        return {
            "is_anomaly": is_anomaly,
            "score": max_score,
            "method": "auto:context_aware",
            "reason": f"{chosen['reason']}; context={bool(context)}",
        }

    raise ValueError(f"Unsupported method: {method}")
