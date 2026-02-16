# TW2002 MCP Operations

This runbook clarifies how to run and target TW2002 MCP tools in environments
with multiple MCP connectors.

## What This Solves

- `tw2002_*` tools not showing up in an MCP client
- Confusion between local `bbsbot` tools and external connector tools
- Unclear hijack/assume workflow for swarm operations

## Canonical MCP Server Alias

Use an explicit alias in MCP client config:

- `bbsbot_local_tw2002`

Example:

```json
{
  "mcpServers": {
    "bbsbot_local_tw2002": {
      "command": "bbsbot",
      "args": ["serve", "--tools", "tw2002"]
    }
  }
}
```

## Start Local TW2002 MCP Server

From repo root:

```bash
cd /path/to/bbsbot
uv run bbsbot serve --tools tw2002
```

## Expected Tool Families

When correctly configured, tool names should include:

- `tw2002_assume_bot`
- `tw2002_hijack_begin`
- `tw2002_hijack_read`
- `tw2002_hijack_send`
- `tw2002_hijack_heartbeat`
- `tw2002_hijack_release`
- `tw2002_get_bot_health`
- `tw2002_recover_bot`
- `tw2002_force_action`

## Swarm Hijack Flow

1. `tw2002_assume_bot(bot_id)`
2. `tw2002_hijack_begin(lease_s=90, owner="...")`
3. loop:
   - `tw2002_hijack_heartbeat(...)`
   - `tw2002_hijack_read(mode="snapshot"|"events")`
   - `tw2002_hijack_send(...)`
4. `tw2002_hijack_release(...)` on exit

## Troubleshooting

- No `tw2002_*` tools visible:
  - Confirm client config points to `bbsbot` command in this environment
  - Confirm args include `serve --tools tw2002`
  - Restart MCP client session after config changes
- Wrong tools visible:
  - You are connected to another MCP server/connector; switch to
    `bbsbot_local_tw2002`
- Manager/hijack calls failing:
  - Ensure swarm manager is reachable at `http://localhost:2272`
