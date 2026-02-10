#!/usr/bin/env python3
"""Run the must-pass TW2002 verification flows in order."""

from __future__ import annotations

import asyncio

from bbsbot.game.tw2002.verification import (
    game_entry_main,
    login_main,
    new_character_main,
    orientation_recovery_main,
    trading_integration_main,
    twgs_commands_main,
    validation_and_menus_main,
)

FLOWS = [
    ("twgs_commands", twgs_commands_main),
    ("login", login_main),
    ("game_entry", game_entry_main),
    ("new_character", new_character_main),
    ("orientation_recovery", orientation_recovery_main),
    ("trading_integration", trading_integration_main),
    ("validation_and_menus", validation_and_menus_main),
]


async def run_flow(name: str, func) -> bool:
    print("=" * 80)
    print(f"RUN: {name}")
    print("=" * 80)
    try:
        result = await func()
    except Exception as exc:
        print(f"FAIL: {name} ({exc})\n")
        return False

    if isinstance(result, bool):
        ok = result
    elif result is None:
        ok = True
    elif isinstance(result, int):
        ok = result == 0
    else:
        ok = False
    status = "PASS" if ok else "FAIL"
    print(f"{status}: {name}\n")
    return ok


async def main() -> int:
    results: list[tuple[str, bool]] = []

    for name, func in FLOWS:
        ok = await run_flow(name, func)
        results.append((name, ok))
        if not ok:
            break

    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    for name, ok in results:
        status = "PASS" if ok else "FAIL"
        print(f"  {status}: {name}")

    if all(ok for _, ok in results):
        print("\nOVERALL: PASS")
        return 0

    print("\nOVERALL: FAIL")
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
