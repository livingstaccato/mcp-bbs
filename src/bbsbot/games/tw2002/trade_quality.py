# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Trade-quality control resolution helpers."""

from __future__ import annotations

from dataclasses import dataclass

from bbsbot.games.tw2002.config import BotConfig, TradeQualityOverrideConfig


@dataclass(frozen=True)
class EffectiveTradeQualityControls:
    strict_eligibility_enabled: bool
    strict_eligibility_require_known_side: bool
    strict_eligibility_require_port_presence: bool
    bootstrap_turns: int
    bootstrap_min_verified_lanes: int
    attempt_budget_window_turns: int
    attempt_budget_max_attempts: int
    opportunity_score_min: float
    non_verified_lane_score_penalty: float
    wrong_side_storm_enabled: bool
    wrong_side_storm_min_samples: int
    wrong_side_storm_ratio_gte: float
    wrong_side_storm_cooldown_turns: int
    role_mode_enabled: bool
    role_scout_ratio: float
    role_harvester_ratio: float
    role_ai_ratio: float
    reroute_wrong_side_ttl_s: int
    reroute_no_port_ttl_s: int
    reroute_no_interaction_ttl_s: int
    autotune_enabled: bool
    autotune_apply_on_restart: bool


def _clamp_int(value: int, low: int, high: int) -> int:
    return max(low, min(high, int(value)))


def _clamp_ratio(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def resolve_trade_quality_controls(
    config: BotConfig,
    override: TradeQualityOverrideConfig | None = None,
) -> EffectiveTradeQualityControls:
    """Resolve effective trade-quality controls with optional strategy override."""
    base = config.trading.trade_quality
    ov = override or TradeQualityOverrideConfig()
    ov_map = ov.model_dump(exclude_none=True)
    merged = {
        "strict_eligibility_enabled": bool(base.strict_eligibility_enabled),
        "strict_eligibility_require_known_side": bool(base.strict_eligibility_require_known_side),
        "strict_eligibility_require_port_presence": bool(base.strict_eligibility_require_port_presence),
        "bootstrap_turns": int(base.bootstrap_turns),
        "bootstrap_min_verified_lanes": int(base.bootstrap_min_verified_lanes),
        "attempt_budget_window_turns": int(base.attempt_budget_window_turns),
        "attempt_budget_max_attempts": int(base.attempt_budget_max_attempts),
        "opportunity_score_min": float(base.opportunity_score_min),
        "non_verified_lane_score_penalty": float(base.non_verified_lane_score_penalty),
        "wrong_side_storm_enabled": bool(base.wrong_side_storm_enabled),
        "wrong_side_storm_min_samples": int(base.wrong_side_storm_min_samples),
        "wrong_side_storm_ratio_gte": float(base.wrong_side_storm_ratio_gte),
        "wrong_side_storm_cooldown_turns": int(base.wrong_side_storm_cooldown_turns),
        "role_mode_enabled": bool(base.role_mode_enabled),
        "role_scout_ratio": float(base.role_scout_ratio),
        "role_harvester_ratio": float(base.role_harvester_ratio),
        "role_ai_ratio": float(base.role_ai_ratio),
        "reroute_wrong_side_ttl_s": int(base.reroute_wrong_side_ttl_s),
        "reroute_no_port_ttl_s": int(base.reroute_no_port_ttl_s),
        "reroute_no_interaction_ttl_s": int(base.reroute_no_interaction_ttl_s),
        "autotune_enabled": bool(base.autotune_enabled),
        "autotune_apply_on_restart": bool(base.autotune_apply_on_restart),
    }
    merged.update(ov_map)

    scout_ratio = _clamp_ratio(float(merged["role_scout_ratio"]))
    harvester_ratio = _clamp_ratio(float(merged["role_harvester_ratio"]))
    ai_ratio = _clamp_ratio(float(merged["role_ai_ratio"]))
    role_total = max(0.0001, scout_ratio + harvester_ratio + ai_ratio)
    scout_ratio = scout_ratio / role_total
    harvester_ratio = harvester_ratio / role_total
    ai_ratio = ai_ratio / role_total

    return EffectiveTradeQualityControls(
        strict_eligibility_enabled=bool(merged["strict_eligibility_enabled"]),
        strict_eligibility_require_known_side=bool(merged["strict_eligibility_require_known_side"]),
        strict_eligibility_require_port_presence=bool(merged["strict_eligibility_require_port_presence"]),
        bootstrap_turns=_clamp_int(int(merged["bootstrap_turns"]), 0, 20_000),
        bootstrap_min_verified_lanes=_clamp_int(int(merged["bootstrap_min_verified_lanes"]), 0, 5000),
        attempt_budget_window_turns=_clamp_int(int(merged["attempt_budget_window_turns"]), 1, 2000),
        attempt_budget_max_attempts=_clamp_int(int(merged["attempt_budget_max_attempts"]), 1, 1000),
        opportunity_score_min=_clamp_ratio(float(merged["opportunity_score_min"])),
        non_verified_lane_score_penalty=_clamp_ratio(float(merged["non_verified_lane_score_penalty"])),
        wrong_side_storm_enabled=bool(merged["wrong_side_storm_enabled"]),
        wrong_side_storm_min_samples=_clamp_int(int(merged["wrong_side_storm_min_samples"]), 1, 1000),
        wrong_side_storm_ratio_gte=_clamp_ratio(float(merged["wrong_side_storm_ratio_gte"])),
        wrong_side_storm_cooldown_turns=_clamp_int(int(merged["wrong_side_storm_cooldown_turns"]), 1, 10_000),
        role_mode_enabled=bool(merged["role_mode_enabled"]),
        role_scout_ratio=scout_ratio,
        role_harvester_ratio=harvester_ratio,
        role_ai_ratio=ai_ratio,
        reroute_wrong_side_ttl_s=_clamp_int(int(merged["reroute_wrong_side_ttl_s"]), 1, 86_400),
        reroute_no_port_ttl_s=_clamp_int(int(merged["reroute_no_port_ttl_s"]), 1, 86_400),
        reroute_no_interaction_ttl_s=_clamp_int(int(merged["reroute_no_interaction_ttl_s"]), 1, 86_400),
        autotune_enabled=bool(merged["autotune_enabled"]),
        autotune_apply_on_restart=bool(merged["autotune_apply_on_restart"]),
    )


def trade_quality_runtime_map(
    controls: EffectiveTradeQualityControls,
    *,
    strict_eligibility_active: bool = False,
    bootstrap_active: bool = False,
    attempt_budget_active: bool = False,
    role_mode_active: bool = False,
    blocked_unknown_side: int = 0,
    blocked_no_port: int = 0,
    blocked_low_score: int = 0,
    blocked_budget_exhausted: int = 0,
    blocked_wrong_side_storm: int = 0,
    reroute_wrong_side: int = 0,
    reroute_no_port: int = 0,
    reroute_no_interaction: int = 0,
    verified_lanes_count: int = 0,
    attempt_budget_used: int = 0,
    attempt_budget_window: int = 0,
    opportunity_score_avg_accepted: float = 0.0,
    opportunity_score_avg_rejected: float = 0.0,
    wrong_side_storm_active: bool = False,
    trigger_wrong_side_storm: int = 0,
) -> dict[str, int | float | bool]:
    return {
        "strict_eligibility_active": bool(strict_eligibility_active and controls.strict_eligibility_enabled),
        "bootstrap_active": bool(bootstrap_active),
        "attempt_budget_active": bool(attempt_budget_active),
        "role_mode_active": bool(role_mode_active and controls.role_mode_enabled),
        "blocked_unknown_side": int(max(0, blocked_unknown_side)),
        "blocked_no_port": int(max(0, blocked_no_port)),
        "blocked_low_score": int(max(0, blocked_low_score)),
        "blocked_budget_exhausted": int(max(0, blocked_budget_exhausted)),
        "blocked_wrong_side_storm": int(max(0, blocked_wrong_side_storm)),
        "reroute_wrong_side": int(max(0, reroute_wrong_side)),
        "reroute_no_port": int(max(0, reroute_no_port)),
        "reroute_no_interaction": int(max(0, reroute_no_interaction)),
        "verified_lanes_count": int(max(0, verified_lanes_count)),
        "attempt_budget_used": int(max(0, attempt_budget_used)),
        "attempt_budget_window": int(max(1, attempt_budget_window)),
        "opportunity_score_avg_accepted": float(max(0.0, opportunity_score_avg_accepted)),
        "opportunity_score_avg_rejected": float(max(0.0, opportunity_score_avg_rejected)),
        "wrong_side_storm_active": bool(wrong_side_storm_active and controls.wrong_side_storm_enabled),
        "trigger_wrong_side_storm": int(max(0, trigger_wrong_side_storm)),
    }
