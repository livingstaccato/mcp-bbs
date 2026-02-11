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
