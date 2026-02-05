# Feature Specification: Game-Specific MCP Helper Tools

**Feature Branch**: `002-game-mcp-helpers`
**Created**: 2026-02-05
**Status**: Draft
**Input**: User description: "Game-specific MCP helper tools that extend bbsbot with high-level commands for specific BBS games, used instead of raw bbs_ commands"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - AI Agent Navigates and Trades in TW2002 (Priority: P1)

An AI agent connected to a TW2002 game wants to move between sectors, trade at ports, and check its status. Instead of manually sequencing `bbs_send("M")`, `bbs_read()`, `bbs_send("123\r")`, `bbs_wait_for_prompt("prompt.command")` — the agent calls a single `tw_warp(sector=123)` tool that handles the entire multi-step flow and returns structured results.

**Why this priority**: This is the core value proposition — collapsing multi-step BBS interactions into single tool calls that return structured data. Without this, AI agents spend most of their turns on low-level screen navigation.

**Independent Test**: Can be tested by connecting to a TW2002 server, calling `tw_warp(sector=5)`, and verifying the agent arrives at sector 5 with structured sector data returned.

**Acceptance Scenarios**:

1. **Given** a connected TW2002 session at the command prompt, **When** the agent calls `tw_warp(sector=5)`, **Then** the tool sends the move command, waits for the command prompt to reappear, and returns the new sector number, warps, ports, and any events encountered during transit.
2. **Given** a connected TW2002 session at the command prompt, **When** the agent calls `tw_port_trade(item="fuel_ore", quantity=100)`, **Then** the tool docks at the port, initiates trading, handles the haggle sequence, and returns the final price, quantity traded, and credit balance.
3. **Given** a connected TW2002 session at the command prompt, **When** the agent calls `tw_status()`, **Then** the tool returns the current sector, credits, holds, alignment, and ship info as structured data without the agent needing to parse screen text.

---

### User Story 2 - AI Agent Logs Into TW2002 End-to-End (Priority: P1)

An AI agent wants to connect to a TWGS server and get to the TW2002 command prompt ready to play. This involves TWGS login, game selection, character creation/selection, and handling pause screens — a complex multi-stage flow. A single `tw_login(host, port, username, password, game_letter)` tool handles the entire sequence.

**Why this priority**: Login is a prerequisite for all gameplay. The TWGS login flow is notoriously complex with multiple branches (new player vs. returning, private games, description mode). Getting this wrong blocks everything.

**Independent Test**: Can be tested by calling `tw_login()` against a running TW2002 Docker instance and verifying the session arrives at the command prompt.

**Acceptance Scenarios**:

1. **Given** no active BBS connection and a stored credential profile, **When** the agent calls `tw_login(profile="mychar")`, **Then** the tool loads credentials from the config file, connects via telnet, navigates TWGS login, selects the game, handles pauses, and returns success with the initial sector data.
2. **Given** the TWGS server prompts for a new character name, **When** `tw_login` encounters character creation, **Then** the tool handles the creation flow and returns success with the new character's starting state.
3. **Given** invalid credentials, **When** `tw_login` encounters an auth failure, **Then** the tool returns a clear error indicating the failure reason without leaving the session in a broken state.

---

### User Story 3 - Game Helper Registration Framework (Priority: P2)

A developer wants to add MCP helper tools for a new BBS game (e.g., Legend of the Red Dragon, Barren Realms Elite). They create a new helper module following a standard pattern, register it with a namespace, and the tools appear automatically in the MCP server — no changes to core bbsbot required.

**Why this priority**: The addon system already separates game logic from core. Extending this to MCP tools ensures bbsbot scales to multiple games without core modifications.

**Independent Test**: Can be tested by creating a minimal game helper module with one tool, registering it, and verifying the tool appears in the MCP server's tool list.

**Acceptance Scenarios**:

1. **Given** a new game helper module following the registration pattern, **When** the MCP server starts with that game's namespace configured, **Then** the game-specific tools appear alongside the core `bbs_*` tools.
2. **Given** no game namespace is configured, **When** the MCP server starts, **Then** only the core `bbs_*` tools are available and no game-specific tools appear.
3. **Given** a game helper tool fails mid-execution, **When** the error occurs, **Then** the session is left in a recoverable state and the error is returned with enough context for the agent to retry or fall back to raw `bbs_*` commands.

---

### User Story 4 - AI Agent Queries Accumulated Game State (Priority: P2)

An AI agent wants to query TW2002 game state that has been accumulated by the addon's event processing — port data, sector maps, trade history — without re-reading screens. Tools like `tw_get_ports()`, `tw_get_sector_info(sector)`, and `tw_get_trade_history()` return accumulated knowledge.

**Why this priority**: The Tw2002Addon already tracks state (ports, sectors, trades). Exposing this via MCP tools lets agents make decisions based on accumulated knowledge without re-scanning screens.

**Independent Test**: Can be tested by running a session, visiting several sectors, then calling `tw_get_sector_info()` and verifying it returns previously observed data.

**Acceptance Scenarios**:

1. **Given** a session that has visited sectors 1, 5, and 10, **When** the agent calls `tw_get_sector_info(sector=5)`, **Then** the tool returns the last-known warps, ports, and planets for sector 5.
2. **Given** a session with no prior trading activity, **When** the agent calls `tw_get_trade_history()`, **Then** the tool returns an empty list rather than an error.

---

### Edge Cases

- What happens when a game helper tool is called but no session is connected? Return a clear error stating a connection is required.
- What happens when a game helper tool is called but the session is connected to a different game? Return an error indicating namespace mismatch.
- What happens when a multi-step tool (like `tw_port_trade`) encounters an unexpected screen mid-flow? The tool attempts recovery to a known safe state (command prompt) and returns a partial result with an error flag.
- What happens when the BBS server disconnects mid-operation? The tool detects the disconnection, reports it, and does not hang indefinitely.
- What happens when two game helper tools are called concurrently on the same session? The second call waits or returns an error — session operations are inherently sequential.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST expose game-specific MCP tools that wrap multi-step BBS interactions into single tool calls returning structured data.
- **FR-002**: Each game helper tool MUST return structured results (not raw screen text) with clearly defined fields including success/failure status, structured data, and any error context.
- **FR-003**: Game helper tools MUST handle the complete interaction flow internally, including waiting for prompts, sending responses, and parsing results using the existing rules pipeline.
- **FR-004**: The system MUST provide a registration mechanism for game-specific tool sets, keyed by namespace (e.g., "tw2002").
- **FR-005**: Game helper tools MUST leave the session in a known, recoverable state on both success and failure.
- **FR-006**: Game helper tools MUST coexist with core `bbs_*` tools — agents can use both interchangeably within the same session.
- **FR-007**: Each game helper tool MUST log its operations through the existing session logger (JSONL) with appropriate context.
- **FR-008**: Game helper tools MUST respect the existing addon event system — events emitted during tool execution MUST be captured and optionally included in the tool's return value.
- **FR-009**: The system MUST provide helper tools covering all TW2002 game operations: login, navigation/warp, port trading, banking, combat, planet colonization, ship upgrades, CIM data queries, and status. Each game action available to a player MUST have a corresponding helper tool.
- **FR-011**: The system MUST support stored credential profiles saved to a config file within the knowledge root. Login tools MUST accept a profile name parameter that references stored credentials (host, port, username, password, game identifier).
- **FR-010**: Game helper tools MUST enforce single-operation-per-session semantics — concurrent calls on the same session MUST be serialized or rejected.

### Key Entities

- **GameHelper**: A registered set of MCP tools for a specific game namespace, with lifecycle tied to session state.
- **ToolResult**: Structured return value from a game helper tool containing success/failure status, structured data, addon events emitted, and any error context.
- **GameState**: Accumulated knowledge from addon event processing (sectors visited, ports discovered, trade history) queryable via read-only tools. Persisted to disk within the knowledge root so it survives across sessions and is reloaded on next login to the same game.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An AI agent can complete a full TW2002 trading loop (login, navigate to port, trade, return) using only game helper tools, with zero `bbs_send`/`bbs_read` calls.
- **SC-002**: The number of MCP tool calls required for a standard trade run is reduced by at least 60% compared to using raw `bbs_*` tools.
- **SC-003**: Game helper tool responses contain structured data that requires no additional screen parsing by the AI agent.
- **SC-004**: A new game's helper tools can be added by creating a single module and rules file, with no modifications to bbsbot core or the MCP server module. The registration framework is implemented from v1 with TW2002 as the first registered game.
- **SC-005**: All game helper tools return within a bounded time (default 30 seconds, configurable) and never leave the session in an unrecoverable state.

## Clarifications

### Session 2026-02-05

- Q: Should game helpers cover all TW2002 operations or only a curated high-value subset? → A: Cover all TW2002 operations — every game action gets a helper tool.
- Q: Should GameState persist across sessions or be in-memory only? → A: Persisted to disk — state survives across sessions, loaded on next login to same game.
- Q: How should credentials be handled for login tools? → A: Stored config — credentials saved in a config file within knowledge root, referenced by profile name.
- Q: What should the default timeout be for game helper operations? → A: 30 seconds default.
- Q: Should the initial release include the registration framework for other games beyond TW2002? → A: Include registration framework — TW2002 tools are the first registered game, framework ready for others.

## Assumptions

- The existing `Tw2002Addon` event tracking and `src/bbsbot/tw2002/` bot logic provide the foundation — game helpers wrap and expose this existing code, not rewrite it.
- The TW2002 Docker container is available for integration testing on ports 3003/3223/3443.
- The FastMCP framework supports dynamic tool registration or tool grouping by namespace.
- The existing rules.json prompt patterns are sufficient for the initial set of game helper tools.
- Game helper tools operate on the active session (single-session model) consistent with existing `bbs_*` tools.
