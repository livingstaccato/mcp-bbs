# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Trade-quality autotune recommendation helpers."""

from __future__ import annotations


def build_trade_quality_recommendations(delta: dict, last: dict) -> dict:
    """Build non-mutating restart-time recommendations from summary windows."""
    trade_attempts = int((delta or {}).get("trade_attempts") or 0)
    trade_success_rate = float((delta or {}).get("trade_success_rate") or 0.0)
    fail_reasons = dict((delta or {}).get("trade_failure_reasons") or {})
    wrong_side = int(fail_reasons.get("trade_fail_wrong_side", 0) or 0)
    no_port = int(fail_reasons.get("trade_fail_no_port", 0) or 0)
    structural_ratio = (
        float(wrong_side + no_port) / float(max(1, trade_attempts))
        if trade_attempts > 0
        else 0.0
    )

    reco: dict[str, int | float | bool] = {
        "enabled": False,
        "reason": "insufficient_signal",
        "opportunity_score_min": 0.62,
        "attempt_budget_max_attempts": 8,
        "reroute_no_port_ttl_s": 900,
    }
    if trade_attempts < 25:
        return reco

    reco["enabled"] = True
    if structural_ratio >= 0.6:
        reco["reason"] = "high_structural_failures"
        reco["opportunity_score_min"] = 0.72
        reco["attempt_budget_max_attempts"] = 6
        reco["reroute_no_port_ttl_s"] = 1200
        return reco
    if trade_success_rate < 0.06 and trade_attempts >= 60:
        reco["reason"] = "low_success_high_attempts"
        reco["opportunity_score_min"] = 0.70
        reco["attempt_budget_max_attempts"] = 6
        return reco
    if trade_success_rate >= 0.22 and trade_attempts < 60:
        reco["reason"] = "high_success_low_attempts"
        reco["opportunity_score_min"] = 0.55
        reco["attempt_budget_max_attempts"] = 10
        return reco

    reco["reason"] = "stable_hold"
    reco["opportunity_score_min"] = float((last or {}).get("trade_quality_runtime_total", {}).get("opportunity_score_avg_accepted", 0.62) or 0.62)
    reco["attempt_budget_max_attempts"] = 8
    return reco
