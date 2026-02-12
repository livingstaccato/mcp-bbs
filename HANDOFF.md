# Handoff - BBSBot

## Documentation

**📚 Complete System Documentation**:
- **[System Architecture](.provide/SYSTEM_ARCHITECTURE.md)** - Complete overview of all layers, components, LLM integration, game loops
- **[Architecture Diagrams](.provide/ARCHITECTURE_DIAGRAM.md)** - Visual diagrams for data flow, LLM decisions, multi-character management
- **[Themed Names](.provide/HANDOFF_themed_names.md)** - Character and ship name generation system
- **[Main README](README.md)** - MCP server installation and usage

## Session Snapshot (2026-02-06)
- **Server**: TWGS on `localhost:2002` (this is the only allowed target).
- **Active character**: `Cdx9E2B7` / `Codex2026!` (Game: `B` = “The AI Apocalypse”).
- **Last known location**: Sector `117` (Rylos, Special port). Warps: `146, 352, 757, 1457, 1530, 1807`.
- **Ship state (from prior manual play)**: holds `33`, fighters `47`, shields `1` (credits not reliably parsed in last run).
- **Semantic logging**: `semantic` one‑liners emit on reads; logs written under
  `/Users/tim/Library/Application Support/bbsbot/tw2002/semantic/<character>_semantic.jsonl`.

## Current Status
- MCP server works when launched as `bbsbot serve` from `/Users/tim/code/gh/livingstaccato/bbsbot`.
- Screen content validation system is complete and tested (see `IMPLEMENTATION_COMPLETE.md`).
- TW2002 rules include K/V extraction + validation for key prompts.
- **Semantic extraction** is live (prints `semantic k=v` during reads and writes JSONL).
- **CLI parser** added: `bbsbot tw2002 parse-semantic` can parse stdin/file into a one‑line `semantic ...` output.

## Current Strategy
- Route execution uses twerk paths when available; fallback to sector knowledge or direct warp.
- Session play should log a **one-line K/V status** between send/read.
- Use semantic extraction to **guard against anomalies** (stale sector, wrong prompt, special port).

## Known Pitfalls & Anomalies
- **Trade route analysis returns 0 routes** even with `/tmp/tw2002-data`; `find_trade_routes(...)` produced 0 routes for hops 5/10/20/30.
  - This means `analyze_trade_routes()` currently cannot drive live trading on this dataset.
- **Single trading cycle is unsafe from a Special port**:
  - The bot tried `BUY` immediately without warping and stayed in sector `117`.
  - Warp flow mistakenly accepted `prompt.pause_simple` as a warp prompt, then sent **space** instead of the sector number.
  - Result: stuck in `prompt.pause_simple` / `prompt.yes_no` loops and aborted.
- **Do not assume port class**: Special ports (Rylos) are not valid for normal buy/sell.
- **Only target port 2002**. Any other host/port should be treated as misconfiguration.
- MCP server must be launched as `bbsbot serve` from `/Users/tim/code/gh/livingstaccato/bbsbot`.
- `test_trading_integration.py` expects `/tmp/tw2002-data` to be populated from the Docker container.

## How to Run (Quick)
- `docker cp tw2002-dev:/opt/tw2002/data/tw*.dat /tmp/tw2002-data/`
- `python /Users/tim/code/gh/livingstaccato/bbsbot/src/bbsbot/commands/scripts/test_trading_integration.py`
- Pipe a live screen into the semantic parser:
  - `uv run bbsbot watch --host localhost --port 2002 --once --no-clear --no-prompt | uv run bbsbot tw2002 parse-semantic --format kv`

## Key Context
- MCP server must be launched with `serve` or the client will see `Connection closed`.
- The validation system surfaces `kv_data` into snapshots and bot I/O now returns a 4-tuple.
- Semantic extraction lives in:
  - `/Users/tim/code/gh/livingstaccato/bbsbot/src/bbsbot/tw2002/parsing.py`
  - `/Users/tim/code/gh/livingstaccato/bbsbot/src/bbsbot/tw2002/io.py`
  - `/Users/tim/code/gh/livingstaccato/bbsbot/src/bbsbot/tw2002/connection.py`

## Important Files
- `/Users/tim/code/gh/livingstaccato/bbsbot/IMPLEMENTATION_COMPLETE.md`
- `/Users/tim/code/gh/livingstaccato/bbsbot/IMPLEMENTATION_PLAN.md`
- `/Users/tim/code/gh/livingstaccato/bbsbot/specs/002-game-mcp-helpers/spec.md`
- `/Users/tim/code/gh/livingstaccato/bbsbot/specs/002-game-mcp-helpers/plan.md` (template only)
- `/Users/tim/code/gh/livingstaccato/bbsbot/src/bbsbot/game/tw2002/verification/trading_integration.py`

## Open TODOs (Code)
- `/Users/tim/code/gh/livingstaccato/bbsbot/src/bbsbot/tw2002/colonization.py`: implement planet discovery (minimal done; verify).
- `/Users/tim/code/gh/livingstaccato/bbsbot/src/bbsbot/tw2002/trading.py`: fix warp prompt handling and post‑warp anomaly checks.
- `/Users/tim/code/gh/livingstaccato/bbsbot/src/bbsbot/tw2002/trading.py`: avoid docking at Special ports.
- `/Users/tim/code/gh/livingstaccato/bbsbot/src/bbsbot/game/tw2002/verification/trading_integration.py`: reconcile routes = 0 issue.

## Detailed Checklist / Handoff Plan (Extremely Detailed)

### Phase 0 — Preconditions
- Confirm TWGS is **running on port 2002**:
  - `lsof -nP -iTCP:2002 -sTCP:LISTEN`
  - Expected: process listening on `*:2002`.
- Confirm the **data files exist**:
  - `/tmp/tw2002-data/twsect.dat`
  - `/tmp/tw2002-data/twport.dat`
  - `/tmp/tw2002-data/twuser.dat`
  - `/tmp/tw2002-data/twcfig.dat`
- Confirm the **bot code path** is correct:
  - Run from `/Users/tim/code/gh/livingstaccato/bbsbot`.
  - MCP server must be launched from `/Users/tim/code/gh/livingstaccato/bbsbot` if used.

### Phase 1 — Sanity Check (Parser & Semantic Logs)
- Verify CLI parser exists:
  - `uv run bbsbot tw2002 parse-semantic --help`
- Verify parser with a known screen (paste or pipe):
  - Expect: `semantic sector=... warps=[...] port_class=...`.
- Verify live screen pipe:
  - `uv run bbsbot watch --host localhost --port 2002 --once --no-clear --no-prompt | uv run bbsbot tw2002 parse-semantic --format kv`
  - If output is empty: that snapshot did not include a sector screen; re-run or use a longer `--interval`.
- Verify JSONL log append:
  - After a real read, check:
    - `/Users/tim/Library/Application Support/bbsbot/tw2002/semantic/Cdx9E2B7_semantic.jsonl`
  - Expect new line(s) with sector/port data.

### Phase 2 — Controlled Login & Orientation
- Run a controlled login flow (port 2002 only).
- Confirm prompt flow:
  - `prompt.login_name` → send `Cdx9E2B7`
  - `prompt.menu_selection` → choose `B`
  - Game menu → `T`
  - Log prompt → `N`
  - Game password → `Codex2026!`
- Confirm you reach **sector command** prompt.
- Run `orient()` and ensure:
  - `GameState.sector` is set.
  - `GameState.has_port` is correct.
  - `semantic` line printed for the sector screen.

### Phase 3 — Trading Flow (Aggressive) — Required Fixes
+**Goal**: ensure the bot actually moves to a target sector before buy/sell.
- Add/verify these checks in `trading.py`:
  - **Warp prompt validation**: after sending `M`, only accept **sector number prompt** (not `pause_simple`).
  - **Post-warp sector check**: if `semantic.sector` did not change, **abort or retry** (do not buy/sell).
  - **Special port guard**: if `port_class` is Special/Class 0, skip docking and abort.
  - **Buy-before-warp fix**: trading cycle must warp to buy sector first.
- Re-run a single trading cycle and verify:
  - `semantic sector` changes when warping.
  - `prompt` transitions match the expected warp/port menus.
  - Loop detection **never** triggers on `prompt.pause_simple` or `prompt.yes_no`.

### Phase 4 — Twerk Route Analysis Validation
- Run route analysis from `/tmp/tw2002-data`.
  - Expect **non-zero routes**; currently returns 0.
- If routes remain 0:
  - Inspect `twerk.analysis.find_trade_routes` logic.
  - Confirm port classes and buy/sell flags in the parser.
  - Consider lower constraints (min profit, hops, or allowed classes).
- Ensure `execute_route()` is used for path-based trade.

### Phase 5 — MCP + Bot Integration
- If using MCP tools:
  - Start server with `bbsbot serve` from `/Users/tim/code/gh/livingstaccato/bbsbot`.
  - Ensure the client sees the tools, especially `bbs_connect` and `bbs_wait_for_prompt`.
- If not using MCP tools, run direct `uv run python` scripts.

### Phase 6 — Regression & Exit
- Confirm `semantic` and `status` logs emitted during play.
- Ensure session closes cleanly (`session_closed` log) and no stray processes linger.

## Learnings (Ready for New Session)
- **Warp logic bug**: it accepts `prompt.pause_simple` as a warp input prompt, causing it to send space instead of the sector number. This keeps the player in the same sector and triggers loop detection.
- **Single trading cycle flow order** is wrong from a Special port: it tries to buy before warping.
- **`find_trade_routes` currently returns 0** for `/tmp/tw2002-data`; this blocks route‑based trading.
- **Semantic parsing is effective**: sector/port/warps are captured and must be used to detect anomalies.
- **Only port 2002 is valid**. Any other port should be considered misconfiguration.

## Next Steps (Priority)
1. Fix warp prompt handling + post‑warp sector verification.
2. Add Special port guard and enforce warp-before-buy.
3. Resolve twerk route analysis returning 0 routes.
4. Re‑run live trading flow and confirm sector changes + profit.
5. Expand validation rules in `games/tw2002/rules.json`.

## MCP Self-Check (Verified)
- Running a local MCP client against `bbsbot serve` returns ~32 tools.
- Example tool list begins with: `bbs_connect`, `bbs_read`, `bbs_read_until_nonblank`, `bbs_read_until_pattern`, `bbs_wait_for_prompt`.
