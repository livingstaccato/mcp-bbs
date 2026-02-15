# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

from bbsbot.games.tw2002.config import BotConfig, TradeQualityOverrideConfig
from bbsbot.games.tw2002.trade_quality import resolve_trade_quality_controls


def test_trade_quality_controls_global_defaults() -> None:
    cfg = BotConfig()
    controls = resolve_trade_quality_controls(cfg, None)
    assert controls.strict_eligibility_enabled is True
    assert controls.bootstrap_turns == int(cfg.trading.trade_quality.bootstrap_turns)
    assert controls.attempt_budget_max_attempts == int(cfg.trading.trade_quality.attempt_budget_max_attempts)
    assert controls.non_verified_lane_score_penalty == float(cfg.trading.trade_quality.non_verified_lane_score_penalty)
    assert controls.wrong_side_storm_enabled is bool(cfg.trading.trade_quality.wrong_side_storm_enabled)


def test_trade_quality_controls_partial_override() -> None:
    cfg = BotConfig()
    override = TradeQualityOverrideConfig(
        bootstrap_turns=77,
        opportunity_score_min=0.71,
        non_verified_lane_score_penalty=0.2,
        reroute_no_port_ttl_s=1234,
    )
    controls = resolve_trade_quality_controls(cfg, override)
    assert controls.bootstrap_turns == 77
    assert controls.opportunity_score_min == 0.71
    assert controls.non_verified_lane_score_penalty == 0.2
    assert controls.reroute_no_port_ttl_s == 1234
    assert controls.attempt_budget_window_turns == int(cfg.trading.trade_quality.attempt_budget_window_turns)


def test_trade_quality_controls_full_override_and_normalization() -> None:
    cfg = BotConfig()
    override = TradeQualityOverrideConfig(
        strict_eligibility_enabled=False,
        strict_eligibility_require_known_side=False,
        strict_eligibility_require_port_presence=False,
        bootstrap_turns=0,
        bootstrap_min_verified_lanes=3,
        attempt_budget_window_turns=9,
        attempt_budget_max_attempts=2,
        opportunity_score_min=0.45,
        non_verified_lane_score_penalty=0.22,
        wrong_side_storm_enabled=True,
        wrong_side_storm_min_samples=9,
        wrong_side_storm_ratio_gte=0.67,
        wrong_side_storm_cooldown_turns=33,
        role_mode_enabled=True,
        role_scout_ratio=2.0,
        role_harvester_ratio=3.0,
        role_ai_ratio=1.0,
        reroute_wrong_side_ttl_s=50,
        reroute_no_port_ttl_s=500,
        reroute_no_interaction_ttl_s=75,
        autotune_enabled=True,
        autotune_apply_on_restart=False,
    )
    controls = resolve_trade_quality_controls(cfg, override)
    assert controls.strict_eligibility_enabled is False
    assert controls.strict_eligibility_require_known_side is False
    assert controls.strict_eligibility_require_port_presence is False
    assert controls.bootstrap_turns == 0
    assert controls.bootstrap_min_verified_lanes == 3
    assert controls.attempt_budget_window_turns == 9
    assert controls.attempt_budget_max_attempts == 2
    assert controls.opportunity_score_min == 0.45
    assert controls.non_verified_lane_score_penalty == 0.22
    assert controls.wrong_side_storm_enabled is True
    assert controls.wrong_side_storm_min_samples == 9
    assert controls.wrong_side_storm_ratio_gte == 0.67
    assert controls.wrong_side_storm_cooldown_turns == 33
    assert controls.reroute_wrong_side_ttl_s == 50
    assert controls.reroute_no_port_ttl_s == 500
    assert controls.reroute_no_interaction_ttl_s == 75
    assert controls.autotune_enabled is True
    assert controls.autotune_apply_on_restart is False
    # Role ratios are normalized to sum 1.
    total = controls.role_scout_ratio + controls.role_harvester_ratio + controls.role_ai_ratio
    assert round(total, 6) == 1.0
