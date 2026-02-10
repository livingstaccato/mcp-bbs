#!/usr/bin/env python3
"""Launch bot configurations in waves for stress testing with connection robustness."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import yaml


def launch_bots_in_waves(bots_per_wave: int = 10, delay_between_waves: float = 5.0):
    """Launch bots in waves to avoid overwhelming server."""
    config_dir = Path("config/test_matrix")
    log_dir = Path.home() / "bbsbot_stress_logs_v2"
    log_dir.mkdir(exist_ok=True)

    configs = sorted(config_dir.glob("*.yaml"))
    print(f"🚀 Launching {len(configs)} bots in waves")
    print(f"   Wave size: {bots_per_wave} bots")
    print(f"   Delay between waves: {delay_between_waves}s")
    print()

    wave_num = 0
    total_launched = 0

    for wave_start in range(0, len(configs), bots_per_wave):
        wave_num += 1
        wave_end = min(wave_start + bots_per_wave, len(configs))
        wave_configs = configs[wave_start:wave_end]

        print(f"Wave {wave_num}: Launching {len(wave_configs)} bots...")

        for i, config_path in enumerate(wave_configs):
            config_name = config_path.stem
            bot_index = wave_start + i
            log_file = log_dir / f"{bot_index:03d}_{config_name}.log"

            # Read config and update max turns
            with open(config_path) as f:
                config = yaml.safe_load(f)

            config["session"]["max_turns_per_session"] = 65000

            # Write temporary config
            temp_config = Path(f"/tmp/stress_wave{wave_num}_{i}.yaml")
            with open(temp_config, "w") as f:
                yaml.dump(config, f)

            # Launch bot with small delay to stagger connections
            delay = i * 0.5  # 500ms between each bot in wave
            time.sleep(delay)

            env = os.environ.copy()
            env["PYTHONPATH"] = "src"

            with open(log_file, "w") as logf:
                subprocess.Popen(
                    ["python", "-m", "bbsbot", "tw2002", "bot", "--config", str(temp_config)],
                    stdout=logf,
                    stderr=subprocess.STDOUT,
                    env=env,
                )
                total_launched += 1
                print(f"  [{total_launched:3d}] Launched {config_name}")

        print(f"Wave {wave_num} complete. Waiting {delay_between_waves}s before next wave...")
        if wave_end < len(configs):
            time.sleep(delay_between_waves)

    print()
    print(f"✓ All {total_launched} bots launched in waves!")
    print()
    print("Monitor logs with:")
    print(f"  ls -lrt {log_dir}/")
    print(f"  tail -f {log_dir}/bot_*.log")


if __name__ == "__main__":
    # Launch 10 bots per wave with 5 second delay between waves
    launch_bots_in_waves(bots_per_wave=10, delay_between_waves=5.0)
