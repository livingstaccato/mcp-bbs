# bbsbot Constitution

## Core Principles

### I. Protocol Correctness

All transport implementations MUST comply with their governing RFCs. Telnet MUST follow RFC 854: IAC bytes (0xFF) in data MUST be escaped by doubling, negotiation MUST use WILL/WONT/DO/DONT sequences (never raw DO), and option negotiation MUST handle BINARY, ECHO, SGA, TTYPE, and NAWS. Terminal emulation MUST support CP437 natively for authentic BBS rendering. Protocol violations are bugs, not edge cases.

### II. Pattern-Driven Design

Prompt recognition and screen parsing MUST flow through the rules pipeline: JSON rules (`games/{namespace}/rules.json`) → `RuleSet` → `to_prompt_patterns()` → `PromptDetector`. More specific patterns MUST appear before generic ones—ordering determines match priority. Negative matches (`negative_match`) MUST be used to disambiguate multi-stage flows (e.g., character creation vs. login). Ad-hoc string matching outside the pipeline SHOULD be avoided in core logic.

### III. Always-On Observability

Every `bbs_read()` call MUST log the raw byte payload (Base64-encoded) to the session's JSONL log with timestamp, event type, and session context. All application logging MUST use `structlog` configured to write to stderr (stdout is reserved for MCP JSON-RPC). Session logs MUST capture send/read events, screen snapshots (text, cursor position, terminal dimensions), and context transitions. Print statements MUST NOT be used—use `pout`/`perr` for debugging, `structlog` for production.

### IV. Layered Architecture

The system is organized into five layers with strict dependency direction:

```
Transport → Terminal → Core → Learning → MCP
```

- **Transport**: async send/receive, protocol compliance (telnet.py, ssh.py)
- **Terminal**: pyte-based emulation, CP437 decoding, screen extraction
- **Core**: session lifecycle, session management, resource isolation
- **Learning**: rules loading, prompt detection, auto-discovery, KV extraction, buffer management
- **MCP**: FastMCP tool exposure, structlog-to-stderr configuration

Each layer MUST depend only on layers below it. Circular dependencies between layers MUST NOT exist. Cross-layer communication MUST pass through defined interfaces.

### V. Simplicity / YAGNI

The simplest correct solution MUST be chosen first. Abstractions MUST NOT be introduced until a pattern repeats. Three similar lines of code SHOULD be preferred over a premature helper. Feature flags, backwards-compatibility shims, and speculative extension points MUST NOT be added for hypothetical future requirements. Error handling SHOULD only validate at system boundaries (user input, external APIs, transport bytes)—internal code SHOULD trust framework guarantees.

### VI. Test-First (NON-NEGOTIABLE)

TDD is mandatory. The Red-Green-Refactor cycle MUST be followed: write a failing test, make it pass with minimal code, then refactor. Tests MUST be written before implementation for all new functionality. pytest 8.0+ with `asyncio_mode = "auto"` is the test framework. Property-based testing via Hypothesis SHOULD be used for protocol and parsing logic. Coverage reports MUST be generated (term-missing + HTML). Test modules MUST follow `test_*.py` or `*_test.py` naming.

### VII. Addon Extensibility

Game-specific logic MUST live in `src/bbsbot/addons/` as implementations of the `Addon` protocol (`process(snapshot) → list[AddonEvent]`). Game rules MUST live in `games/{namespace}/rules.json`. The `AddonManager` aggregates events from all registered addons—addons MUST NOT manage shared state directly. Adding support for a new BBS game SHOULD require only a new addon module and a new rules file, with no changes to core layers.

## Technical Constraints

- **Python**: >=3.11 required (supports 3.11, 3.12, 3.13)
- **Type checking**: mypy strict mode (`strict = true`, `disallow_untyped_defs`, `disallow_any_generics`, `check_untyped_defs`)
- **Linting**: ruff with rules E, W, F, I, N, UP, B, C4, SIM, TCH, PTH; line length 120; target py311
- **No hardcoded URLs or ports**: Connection parameters MUST be configurable; defaults MUST live in constants or config, never inline
- **No print statements**: Use structlog for logging, pout/perr for debugging only
- **PTH109**: Use `Path.cwd()` instead of `os.getcwd()`
- **Async-first**: All I/O operations MUST be async with proper locking for concurrent access
- **Dependencies**: fastmcp, pydantic >=2.6, pyte, structlog, click, pexpect, platformdirs, hypothesis
- **Constants**: Shared values (timeouts, dimensions, limits) MUST live in `src/bbsbot/constants.py`

## Development Workflow

- **Auto-learning**: The `LearningEngine` loads rules on initialization based on namespace. New prompts discovered during sessions are candidates for rules.json updates.
- **Single session model**: Each session maintains isolated state. Max concurrent sessions governed by `DEFAULT_MAX_SESSIONS`.
- **Pattern validation**: When adding new prompts to rules.json, place specific patterns before generic ones. Use `negative_match` for multi-stage flows. Verify against existing test suites (`test_login_prompts.py`, `test_orientation.py`).
- **Docker workflow (TW2002)**: The TW2002 server runs in container `tw2002-dev`. Code changes require image rebuild (`docker build -t tw2002:dev .`), then container recreation. Ports: 3003 (telnet), 3223 (SSH), 3443 (admin).
- **Git workflow**: Changes are auto-committed. Do not attempt git rollbacks. Do not mention AI assistance in commit messages.
- **Screen logging**: Session JSONL logs persist for replay and debugging. Screen saver writes snapshots to disk with namespace isolation.

## Governance

1. This constitution supersedes all ad-hoc practices. When a convention conflicts with a principle above, the principle wins.
2. All PRs MUST verify compliance with these principles. Reviewers SHOULD check:
   - [ ] Protocol changes maintain RFC compliance (Principle I)
   - [ ] New prompts follow the rules pipeline with correct ordering (Principle II)
   - [ ] Logging is present for new I/O paths (Principle III)
   - [ ] No circular cross-layer dependencies introduced (Principle IV)
   - [ ] No speculative abstractions or unused code added (Principle V)
   - [ ] Tests written before implementation, all passing (Principle VI)
   - [ ] Game logic stays in addons/rules, not core (Principle VII)
3. Amendments to this constitution require: documentation of the change rationale, approval, and a migration plan for existing code that conflicts with the amendment.

**Version**: 1.0.0 | **Ratified**: 2026-02-05 | **Last Amended**: 2026-02-05
