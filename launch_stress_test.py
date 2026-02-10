#!/usr/bin/env python3
"""Launch all bot configurations for 65000-turn stress testing."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import yaml


def launch_all_bots():
    """Launch all bot configurations in background."""
    config_dir = Path("config/test_matrix")
    log_dir = Path.home() / "bbsbot_stress_logs"
    log_dir.mkdir(exist_ok=True)

    configs = sorted(config_dir.glob("*.yaml"))
    print(f"🚀 Launching {len(configs)} bots with 65000 turns each")
    print()

    pids = []
    for i, config_path in enumerate(configs):
        config_name = config_path.stem
        log_file = log_dir / f"{i:03d}_{config_name}.log"

        # Read config and update max turns
        with open(config_path) as f:
            config = yaml.safe_load(f)

        config["session"]["max_turns_per_session"] = 65000

        # Write temporary config
        temp_config = Path(f"/tmp/stress_{i}.yaml")
        with open(temp_config, "w") as f:
            yaml.dump(config, f)

        # Launch bot
        env = os.environ.copy()
        env["PYTHONPATH"] = "src"

        with open(log_file, "w") as logf:
            proc = subprocess.Popen(
                ["python", "-m", "bbsbot", "tw2002", "bot", "--config", str(temp_config)],
                stdout=logf,
                stderr=subprocess.STDOUT,
                env=env,
            )
            pids.append((proc.pid, config_name))

        if (i + 1) % 10 == 0:
            print(f"  [{i + 1:3d}/{len(configs)}] Launched {len(pids)} bots...")

    print(f"\n✓ All {len(configs)} bots launched!")
    print()
    print("Monitor logs with:")
    print("  ls -lrt ~/bbsbot_stress_logs/")
    print("  tail -f ~/bbsbot_stress_logs/bot_*.log")
    print()
    print("Active processes:")
    subprocess.run(["ps", "aux", "|", "grep", "bbsbot tw2002", "|", "grep", "-v", "grep", "|", "wc", "-l"], shell=True)


if __name__ == "__main__":
    launch_all_bots()
