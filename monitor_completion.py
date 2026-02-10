#!/usr/bin/env python3
"""Monitor bot stress test completion and report when all tests are done."""

from __future__ import annotations

import time
from pathlib import Path


def monitor_tests():
    """Monitor all bot tests for completion."""
    log_dir = Path.home() / "bbsbot_stress_logs"
    log_dir.mkdir(exist_ok=True)

    expected_configs = 111
    print(f"Monitoring {expected_configs} bot tests...")
    print(f"Logs directory: {log_dir}")
    print()

    # Track progress
    previous_count = 0
    start_time = time.time()

    while True:
        # Count completed sessions
        logs = list(log_dir.glob("*.log"))
        if not logs:
            print("Waiting for logs to appear...")
            time.sleep(30)
            continue

        completed = sum(1 for log in logs if "SESSION COMPLETE" in log.read_text())
        total = len(logs)

        if completed > previous_count or completed % 10 == 0:
            elapsed = time.time() - start_time
            percentage = (completed / expected_configs) * 100
            print(
                f"[{time.strftime('%H:%M:%S')}] Sessions completed: {completed}/{expected_configs} ({percentage:.1f}%) - Elapsed: {elapsed / 3600:.1f}h"
            )
            previous_count = completed

        # Check if all completed
        if completed >= expected_configs and total >= expected_configs:
            print()
            print("=" * 70)
            print("✓ ALL BOT TESTS COMPLETED!")
            print("=" * 70)
            print(f"Total sessions: {total}")
            print(f"Completed: {completed}")
            print(f"Total time: {(time.time() - start_time) / 3600:.1f} hours")
            print()
            return True

        time.sleep(60)  # Check every minute


if __name__ == "__main__":
    if monitor_tests():
        print("<promise>ALL BOTS TESTED</promise>")
