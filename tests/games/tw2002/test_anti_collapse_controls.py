# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

from bbsbot.games.tw2002.anti_collapse import resolve_anti_collapse_controls
from bbsbot.games.tw2002.config import AntiCollapseOverrideConfig, BotConfig


def test_anti_collapse_controls_global_defaults() -> None:
    cfg = BotConfig()
    controls = resolve_anti_collapse_controls(cfg, None)
    assert controls.enabled is True
    assert controls.throughput_degraded_min_samples == int(cfg.trading.anti_collapse.throughput_degraded_min_samples)
    assert controls.structural_storm_structural_ratio_gte == float(
        cfg.trading.anti_collapse.structural_storm_structural_ratio_gte
    )


def test_anti_collapse_controls_partial_override() -> None:
    cfg = BotConfig()
    override = AntiCollapseOverrideConfig(
        throughput_degraded_min_samples=33,
        lane_backoff_base_seconds=333,
    )
    controls = resolve_anti_collapse_controls(cfg, override)
    assert controls.throughput_degraded_min_samples == 33
    assert controls.lane_backoff_base_seconds == 333
    # Non-overridden values still inherit global defaults.
    assert controls.forced_probe_disable_attempts_low == int(cfg.trading.anti_collapse.forced_probe_disable_attempts_low)


def test_anti_collapse_controls_full_override() -> None:
    cfg = BotConfig()
    override = AntiCollapseOverrideConfig(
        enabled=False,
        throughput_degraded_min_samples=8,
        throughput_degraded_success_rate_lt=0.31,
        structural_storm_min_samples=9,
        structural_storm_structural_ratio_gte=0.66,
        lane_backoff_enabled=False,
        lane_backoff_base_seconds=30,
        lane_backoff_max_seconds=90,
        sector_backoff_enabled=False,
        sector_backoff_base_seconds=40,
        sector_backoff_max_seconds=80,
        forced_probe_disable_enabled=False,
        forced_probe_disable_attempts_low=10,
        forced_probe_disable_success_rate_low=0.05,
        forced_probe_disable_attempts_high=20,
        forced_probe_disable_success_rate_high=0.09,
    )
    controls = resolve_anti_collapse_controls(cfg, override)
    assert controls.enabled is False
    assert controls.throughput_degraded_min_samples == 8
    assert controls.throughput_degraded_success_rate_lt == 0.31
    assert controls.structural_storm_min_samples == 9
    assert controls.structural_storm_structural_ratio_gte == 0.66
    assert controls.lane_backoff_enabled is False
    assert controls.lane_backoff_base_seconds == 30
    assert controls.lane_backoff_max_seconds == 90
    assert controls.sector_backoff_enabled is False
    assert controls.sector_backoff_base_seconds == 40
    assert controls.sector_backoff_max_seconds == 80
    assert controls.forced_probe_disable_enabled is False
    assert controls.forced_probe_disable_attempts_low == 10
    assert controls.forced_probe_disable_success_rate_low == 0.05
    assert controls.forced_probe_disable_attempts_high == 20
    assert controls.forced_probe_disable_success_rate_high == 0.09
