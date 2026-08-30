"""SLO, Error Budget, and Multi-Window Burn Rate calculation module.

Follows SRE best practices for multi-window multi-burn-rate alerting policies
to distinguish sustained fast burn from transient spikes.
"""
from __future__ import annotations

from typing import Any


def calculate_slo(target: float, bad_events: int, total_events: int) -> dict[str, Any]:
    if not 0 < target < 1:
        raise ValueError("target must be between 0 and 1 (exclusive)")
    if bad_events < 0 or total_events < 0 or bad_events > total_events:
        raise ValueError("invalid event counts")
    allowed_bad_rate = 1.0 - target
    if total_events == 0:
        return {
            "target": target,
            "actual_bad_rate": 0.0,
            "allowed_bad_rate": allowed_bad_rate,
            "burn_rate": 0.0,
            "remaining_error_budget_fraction": 1.0,
            "breached": False,
        }
    actual_bad_rate = bad_events / total_events
    burn_rate = actual_bad_rate / allowed_bad_rate
    consumed_fraction = min(1.0, actual_bad_rate / allowed_bad_rate)
    return {
        "target": target,
        "actual_bad_rate": actual_bad_rate,
        "allowed_bad_rate": allowed_bad_rate,
        "burn_rate": burn_rate,
        "remaining_error_budget_fraction": max(0.0, 1.0 - consumed_fraction),
        "breached": bool(actual_bad_rate > allowed_bad_rate),
    }


def evaluate_multiwindow_burn(
    *,
    short_window_burn: float,
    long_window_burn: float,
    policy: str = "sre_multiwindow",
    page_burn_threshold: float = 3.0,
    short_spike_threshold: float = 5.0,
) -> dict[str, Any]:
    """Evaluate multi-window burn rate alert.

    - Sustained Fast Burn (both short & long >= threshold): Paged (Critical).
    - Transient Spike (short high, long low): No Page (Warning).
    - Slow Burn (long >= 1.0 or short >= 1.5): Ticket (Warning).
    - Normal (burn < 1.0): No Action (Info).
    """
    if short_window_burn >= page_burn_threshold and long_window_burn >= page_burn_threshold:
        return {
            "page": True,
            "severity": "critical",
            "reason": "sustained_fast_burn_budget_at_risk",
            "short_window_burn": short_window_burn,
            "long_window_burn": long_window_burn,
            "policy": policy,
        }

    if short_window_burn >= short_spike_threshold and long_window_burn < page_burn_threshold:
        return {
            "page": False,
            "severity": "warning",
            "reason": "transient_spike_no_page",
            "short_window_burn": short_window_burn,
            "long_window_burn": long_window_burn,
            "policy": policy,
        }

    if long_window_burn >= 1.0 or short_window_burn >= 1.5:
        return {
            "page": False,
            "severity": "warning",
            "reason": "elevated_burn_rate_create_ticket",
            "short_window_burn": short_window_burn,
            "long_window_burn": long_window_burn,
            "policy": policy,
        }

    return {
        "page": False,
        "severity": "info",
        "reason": "healthy_within_error_budget",
        "short_window_burn": short_window_burn,
        "long_window_burn": long_window_burn,
        "policy": policy,
    }
