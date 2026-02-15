# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Anti-collapse control resolution helpers."""

from __future__ import annotations

from dataclasses import dataclass

from bbsbot.games.tw2002.config import AntiCollapseOverrideConfig, BotConfig


@dataclass(frozen=True)
class EffectiveAntiCollapseControls:
    enabled: bool
    throughput_degraded_min_samples: int
    throughput_degraded_success_rate_lt: float
    structural_storm_min_samples: int
    structural_storm_structural_ratio_gte: float
    lane_backoff_enabled: bool
    lane_backoff_base_seconds: int
    lane_backoff_max_seconds: int
    sector_backoff_enabled: bool
    sector_backoff_base_seconds: int
    sector_backoff_max_seconds: int
    forced_probe_disable_enabled: bool
    forced_probe_disable_attempts_low: int
    forced_probe_disable_success_rate_low: float
    forced_probe_disable_attempts_high: int
    forced_probe_disable_success_rate_high: float


def _clamp_int(value: int, low: int, high: int) -> int:
    return max(low, min(high, int(value)))


def _clamp_ratio(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def resolve_anti_collapse_controls(
    config: BotConfig,
    override: AntiCollapseOverrideConfig | None = None,
) -> EffectiveAntiCollapseControls:
    """Resolve effective anti-collapse controls with optional strategy override."""
    base = config.trading.anti_collapse
    ov = override or AntiCollapseOverrideConfig()
    ov_map = ov.model_dump(exclude_none=True)
    merged = {
        "enabled": bool(base.enabled),
        "throughput_degraded_min_samples": int(base.throughput_degraded_min_samples),
        "throughput_degraded_success_rate_lt": float(base.throughput_degraded_success_rate_lt),
        "structural_storm_min_samples": int(base.structural_storm_min_samples),
        "structural_storm_structural_ratio_gte": float(base.structural_storm_structural_ratio_gte),
        "lane_backoff_enabled": bool(base.lane_backoff_enabled),
        "lane_backoff_base_seconds": int(base.lane_backoff_base_seconds),
        "lane_backoff_max_seconds": int(base.lane_backoff_max_seconds),
        "sector_backoff_enabled": bool(base.sector_backoff_enabled),
        "sector_backoff_base_seconds": int(base.sector_backoff_base_seconds),
        "sector_backoff_max_seconds": int(base.sector_backoff_max_seconds),
        "forced_probe_disable_enabled": bool(base.forced_probe_disable_enabled),
        "forced_probe_disable_attempts_low": int(base.forced_probe_disable_attempts_low),
        "forced_probe_disable_success_rate_low": float(base.forced_probe_disable_success_rate_low),
        "forced_probe_disable_attempts_high": int(base.forced_probe_disable_attempts_high),
        "forced_probe_disable_success_rate_high": float(base.forced_probe_disable_success_rate_high),
    }
    merged.update(ov_map)

    low_attempts = _clamp_int(int(merged["forced_probe_disable_attempts_low"]), 1, 10_000)
    high_attempts = _clamp_int(int(merged["forced_probe_disable_attempts_high"]), 1, 10_000)
    if high_attempts < low_attempts:
        high_attempts = low_attempts

    lane_base = _clamp_int(int(merged["lane_backoff_base_seconds"]), 1, 86_400)
    lane_max = _clamp_int(int(merged["lane_backoff_max_seconds"]), 1, 86_400)
    if lane_max < lane_base:
        lane_max = lane_base
    sector_base = _clamp_int(int(merged["sector_backoff_base_seconds"]), 1, 86_400)
    sector_max = _clamp_int(int(merged["sector_backoff_max_seconds"]), 1, 86_400)
    if sector_max < sector_base:
        sector_max = sector_base

    return EffectiveAntiCollapseControls(
        enabled=bool(merged["enabled"]),
        throughput_degraded_min_samples=_clamp_int(int(merged["throughput_degraded_min_samples"]), 1, 10_000),
        throughput_degraded_success_rate_lt=_clamp_ratio(float(merged["throughput_degraded_success_rate_lt"])),
        structural_storm_min_samples=_clamp_int(int(merged["structural_storm_min_samples"]), 1, 10_000),
        structural_storm_structural_ratio_gte=_clamp_ratio(float(merged["structural_storm_structural_ratio_gte"])),
        lane_backoff_enabled=bool(merged["lane_backoff_enabled"]),
        lane_backoff_base_seconds=lane_base,
        lane_backoff_max_seconds=lane_max,
        sector_backoff_enabled=bool(merged["sector_backoff_enabled"]),
        sector_backoff_base_seconds=sector_base,
        sector_backoff_max_seconds=sector_max,
        forced_probe_disable_enabled=bool(merged["forced_probe_disable_enabled"]),
        forced_probe_disable_attempts_low=low_attempts,
        forced_probe_disable_success_rate_low=_clamp_ratio(float(merged["forced_probe_disable_success_rate_low"])),
        forced_probe_disable_attempts_high=high_attempts,
        forced_probe_disable_success_rate_high=_clamp_ratio(float(merged["forced_probe_disable_success_rate_high"])),
    )


def controls_to_runtime_map(
    controls: EffectiveAntiCollapseControls,
    *,
    throughput_degraded_active: bool = False,
    structural_storm_active: bool = False,
    forced_probe_disable_active: bool = False,
    lane_cooldowns_active: int = 0,
    sector_cooldowns_active: int = 0,
    trigger_throughput_degraded: int = 0,
    trigger_structural_storm: int = 0,
    trigger_forced_probe_disable: int = 0,
) -> dict[str, int | bool]:
    return {
        "controls_enabled": bool(controls.enabled),
        "throughput_degraded_active": bool(throughput_degraded_active),
        "structural_storm_active": bool(structural_storm_active),
        "forced_probe_disable_active": bool(forced_probe_disable_active),
        "lane_cooldowns_active": int(max(0, lane_cooldowns_active)),
        "sector_cooldowns_active": int(max(0, sector_cooldowns_active)),
        "trigger_throughput_degraded": int(max(0, trigger_throughput_degraded)),
        "trigger_structural_storm": int(max(0, trigger_structural_storm)),
        "trigger_forced_probe_disable": int(max(0, trigger_forced_probe_disable)),
    }
