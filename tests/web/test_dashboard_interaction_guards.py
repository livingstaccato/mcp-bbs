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
    assert "mix_5_ai_35_dynamic" in html
    assert 'id="pool-summary"' in html
    assert 'id="pool-table"' in html
    assert "buildSpawnConfigs" in js
    assert "refreshAccountPool" in js
