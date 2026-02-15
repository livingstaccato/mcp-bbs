# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

from pathlib import Path


def _dashboard_js() -> str:
    return Path("src/bbsbot/web/static/dashboard.js").read_text(encoding="utf-8")


def _dashboard_html() -> str:
    return Path("src/bbsbot/web/dashboard.html").read_text(encoding="utf-8")


def test_table_interaction_guard_exists() -> None:
    js = _dashboard_js()
    assert "tablePointerActive" in js
    assert "renderOrDeferTable" in js
    assert "flushDeferredTableRender" in js
    assert "installTableInteractionGuards" in js
    assert "pointerdown" in js
    assert "pointerup" in js


def test_terminal_hijack_heartbeat_exists() -> None:
    js = _dashboard_js()
    assert "termHeartbeatTimer" in js
    assert 'type: "heartbeat"' in js
    assert "heartbeat_ack" in js


def test_spawn_presets_and_pool_panel_present() -> None:
    html = _dashboard_html()
    js = _dashboard_js()
    assert 'id="spawn-preset"' in html
    assert "Mix" in html
    assert "Count" in html
    assert "Config" in html
    assert "mix_5_ai_35_dynamic" in html
    assert "tw2002_mix_5_ai_35_dynamic" in html
    assert "tw2002_dynamic" in html
    assert "tw2002_ai" in html
    assert 'id="filter-layout"' in html
    assert 'id="pool-summary"' in html
    assert 'id="pool-table"' in html
    assert "buildSpawnConfigs" in js
    assert "refreshAccountPool" in js
    assert "TABLE_VIEW_STORAGE_KEY" in js
    assert "applyTableView" in js


def test_strategy_cpt_filters_small_samples_and_outliers() -> None:
    js = _dashboard_js()
    assert "MIN_TURNS_FOR_CPT" in js
    assert "MIN_TRADES_FOR_CPT" in js
    assert "MAX_ABS_CPT_PER_BOT" in js
    assert "samplesSkipped" in js


def test_dashboard_shows_threat_and_attack_signals() -> None:
    js = _dashboard_js()
    assert "hostile_fighters" in js
    assert "under_attack" in js
    assert "BATTLING" in js


def test_dashboard_run_resource_timeseries_is_labeled() -> None:
    html = _dashboard_html()
    js = _dashboard_js()
    assert "Run Resources (1m)" in html
    assert "strategy-panel-cpt" in html
    assert "strategy-panel-trend" in html
    assert ("runBaselineNetWorth" in js) or ("runBaselineCredits" in js)
    assert "computeRunDeltas" in js
    assert "parseStrategyKey" in js
    assert "strategyLabelFull" in js
    assert "<th>Turns</th>" in js
    assert "run-credits-chart-svg" in html
    assert "run-resources-chart-svg" in html
    assert "renderRunChart" in js
    assert "run-chart-line-credits" in js
    assert "run-chart-line-ore" in js
    assert "run-chart-line-org" in js
    assert "run-chart-line-equip" in js


def test_dashboard_binds_diagnostics_telemetry_signals() -> None:
    html = _dashboard_html()
    js = _dashboard_js()
    assert "Opp Seen" in html
    assert "Combat Seen" in html
    assert "Under Attack" in html
    assert "Unknown Delta" in html
    assert "Attrition (Cr)" in html
    assert "Opp Exec Rate" in html
    assert "combat_telemetry" in js
    assert "attrition_telemetry" in js
    assert "opportunity_telemetry" in js
    assert "delta_attribution_telemetry" in js


def test_account_pool_renders_hijack_column_and_state() -> None:
    html = _dashboard_html()
    js = _dashboard_js()
    assert "<th>Status</th>" in html
    assert "lease_seconds_remaining" in js
    assert "pool-status-pill" in js
    assert "latestBotsById" in js
