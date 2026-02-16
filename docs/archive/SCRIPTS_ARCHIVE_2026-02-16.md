# Script Archive Notes (2026-02-16)

## Why

The repo had a large set of legacy debug/test scripts that were no longer part of the supported command surface.

## What stayed active

Active script modules under `src/bbsbot/commands/scripts/`:

- `play_tw2002_full.py`
- `play_tw2002_intelligent.py`
- `play_tw2002_trading.py`
- `play_tw2002_1000turns.py`
- `play_tw2002_multibot.py`
- `play_tw2002.py`
- `play_to_win.py`
- `test_all_patterns.py`
- `test_orientation_recovery.py`
- `test_trading_integration.py`
- `test_twgs_commands.py`
- `capture_screen.py`
- `expect_runner.py`

## What was archived

- Legacy top-level utility scripts moved to `scripts/archive/`
- Legacy debug/test command modules moved to `src/bbsbot/commands/scripts/archive/`

## Supported usage

- `bbsbot tw2002 bot ...`
- `bbsbot tw2002 play --mode <full|intelligent|trading|1000turns>`
- `bbsbot script <active_script_name> [args...]`
