# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

from fastapi.testclient import TestClient

from bbsbot.manager import SwarmManager


def test_root_redirects_to_dashboard(tmp_path) -> None:
    manager = SwarmManager(
        state_file=str(tmp_path / "swarm_state.json"),
        timeseries_dir=str(tmp_path / "metrics"),
        timeseries_interval_s=30,
    )
    with TestClient(manager.app) as client:
        resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 307
    assert resp.headers.get("location") == "/dashboard"


def test_dashboard_and_script_disable_cache(tmp_path) -> None:
    manager = SwarmManager(
        state_file=str(tmp_path / "swarm_state.json"),
        timeseries_dir=str(tmp_path / "metrics"),
        timeseries_interval_s=30,
    )
    with TestClient(manager.app) as client:
        dashboard = client.get("/dashboard")
        script = client.get("/static/dashboard.js")

    assert dashboard.status_code == 200
    assert script.status_code == 200
    assert dashboard.headers.get("cache-control") == "no-store, no-cache, must-revalidate, max-age=0"
    assert script.headers.get("cache-control") == "no-store, no-cache, must-revalidate, max-age=0"
