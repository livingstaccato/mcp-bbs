# Handoff - MCP-BBS / bbsbot

## Current Status
- MCP server works when launched as `bbsbot serve` from `/Users/tim/code/gh/livingstaccato/bbsbot`.
- Screen content validation system is complete and tested (see `IMPLEMENTATION_COMPLETE.md`).
- TW2002 rules include K/V extraction + validation for key prompts.

## Current Strategy
- Route execution uses twerk paths when available; fallback to sector knowledge or direct warp.

## Pitfalls
- MCP server must be launched as `bbsbot serve` from `/Users/tim/code/gh/livingstaccato/bbsbot`.
- `test_trading_integration.py` expects a local TW2002 server at `localhost:2002`.
- `test_trading_integration.py` expects `/tmp/tw2002-data` to be populated from the Docker container.

## How to Run
- `docker cp tw2002-dev:/opt/tw2002/data/tw*.dat /tmp/tw2002-data/`
- `python /Users/tim/code/gh/livingstaccato/mcp-bbs/src/bbsbot/commands/scripts/test_trading_integration.py`

## Key Context
- MCP server must be launched with `serve` or the client will see `Connection closed`.
- The validation system surfaces `kv_data` into snapshots and bot I/O now returns a 4-tuple.

## Important Files
- `/Users/tim/code/gh/livingstaccato/mcp-bbs/IMPLEMENTATION_COMPLETE.md`
- `/Users/tim/code/gh/livingstaccato/mcp-bbs/IMPLEMENTATION_PLAN.md`
- `/Users/tim/code/gh/livingstaccato/mcp-bbs/specs/002-game-mcp-helpers/spec.md`
- `/Users/tim/code/gh/livingstaccato/mcp-bbs/specs/002-game-mcp-helpers/plan.md` (template only)

## Open TODOs (Code)
- `/Users/tim/code/gh/livingstaccato/mcp-bbs/src/bbsbot/tw2002/colonization.py`: implement planet discovery
- `/Users/tim/code/gh/livingstaccato/mcp-bbs/src/bbsbot/commands/scripts/test_trading_integration.py`: implement `execute_route()` following twerk path

## Next Steps (From Implementation Complete)
1. Extend validation rules to more prompts in `games/tw2002/rules.json`.
2. Improve bot logic to use validation errors for recovery and better decisioning.
3. Add validation success/failure metrics or logs.
4. Consider deeper addon integration to reduce duplicate regex.
5. Add colonization flow (deferred).

## MCP Self-Check (Verified)
- Running a local MCP client against `bbsbot serve` returns ~32 tools.
- Example tool list begins with: `bbs_connect`, `bbs_read`, `bbs_read_until_nonblank`, `bbs_read_until_pattern`, `bbs_wait_for_prompt`.
