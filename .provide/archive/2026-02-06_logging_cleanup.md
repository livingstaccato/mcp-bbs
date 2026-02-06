# Logging Cleanup for bbsbot Server Architecture

## Problem

**Too many logs polluting stdout** - Print statements in `session.py` were interfering with MCP JSON-RPC protocol by writing status messages to stdout.

## Solution Implemented

### 1. Centralized Logging Configuration

Created `src/bbsbot/logging/config.py` with:
- `configure_logging()` - Sets up structlog with BBSBOT_LOG_LEVEL environment variable (default: WARNING)
- `get_logger(name)` - Returns configured structlog logger instance
- All logs write to stderr (MCP uses stdout for JSON-RPC)
- ISO timestamps and console rendering

### 2. Removed Print Statements

**src/bbsbot/core/session.py:**
- Removed `print()` calls at lines 113-115 (send method)
- Removed `print()` calls at lines 137-139 (read method)
- Replaced with `logger.debug()` using centralized logger

### 3. Updated MCP Server

**src/bbsbot/mcp/server.py:**
- Removed inline structlog configuration
- Now calls `configure_logging()` at module import
- Uses `get_logger(__name__)` for structured logging

### 4. Consolidated tw2002 Logging

**src/bbsbot/tw2002/logging_utils.py:**
- Removed duplicate structlog configuration
- Now uses centralized `get_logger(__name__)`
- Kept domain-specific utilities (_log_trade, _save_trade_history, _print_session_summary)

### 5. Converted to Absolute Imports

Converted all relative imports to absolute imports in:
- `src/bbsbot/tw2002/*.py` (all modules)
- `src/bbsbot/game/tw2002/verification/__init__.py`
- `src/bbsbot/core/session.py`

### 6. Removed Unused Configuration

**src/bbsbot/settings.py:**
- Removed unused `log_level` field (now handled by logging config module)

## Files Modified

1. `src/bbsbot/logging/config.py` - **NEW** - Centralized logging configuration
2. `src/bbsbot/logging/__init__.py` - Updated exports (no logic in __init__)
3. `src/bbsbot/core/session.py` - Replaced print() with logger.debug()
4. `src/bbsbot/mcp/server.py` - Use centralized logging config
5. `src/bbsbot/tw2002/logging_utils.py` - Use centralized logger
6. `src/bbsbot/tw2002/*.py` - Converted all relative imports to absolute
7. `src/bbsbot/game/tw2002/verification/__init__.py` - Absolute imports
8. `src/bbsbot/settings.py` - Removed unused log_level field

## Benefits

### Clean MCP Protocol
- stdout is now clean (only JSON-RPC messages)
- stderr contains structured logs (when enabled)
- No more "status action=send/read" pollution

### Configurable Logging
```bash
# Default: WARNING (quiet, clean output)
bbsbot serve

# Debug mode: see all session activity
BBSBOT_LOG_LEVEL=DEBUG bbsbot serve

# Info mode: see key events
BBSBOT_LOG_LEVEL=INFO bbsbot serve
```

### Server Architecture Preserved
- ✅ MCP server with 25+ tools for connection/interaction
- ✅ Watch broker on TCP port 8765 for external observers
- ✅ SessionManager supporting multiple concurrent sessions
- ✅ Session logging writes structured JSONL to disk (unchanged)
- ✅ Clean logging that respects the server model

### Code Quality
- ✅ No logic in `__init__.py` files
- ✅ All imports are absolute (no relative imports)
- ✅ Centralized configuration (DRY principle)
- ✅ Proper separation of concerns

## Verification

### Test Clean Stdout
```bash
# Run MCP server - stdout should only have JSON-RPC
bbsbot serve
```

### Test Debug Logging
```bash
# Enable debug logging - should see session activity on stderr
BBSBOT_LOG_LEVEL=DEBUG bbsbot serve
```

### Test JSONL Preserved
```bash
# Check session logs still written
ls ~/.local/share/bbsbot/sessions/
```

### Test Import from Centralized Logging
```python
from bbsbot.logging import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)
logger.info("test message")
```

## Environment Variables

- `BBSBOT_LOG_LEVEL` - Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
  - Default: WARNING
  - Used by: bbsbot.logging.config.configure_logging()

## Architecture Notes

**Server Model Still Intact:**
- bbsbot runs as MCP server (FastMCP framework)
- External systems interact via MCP tools
- Watch broker for raw TCP observation
- JSONL session logs for comprehensive debugging
- Structured logs (stderr) for operational visibility

**Logging Layers:**
1. **Structured Logs** (stderr) - Operational events, configurable via BBSBOT_LOG_LEVEL
2. **Session Logs** (JSONL files) - Comprehensive session capture (unchanged)
3. **MCP Protocol** (stdout) - Clean JSON-RPC only

## Next Steps

Consider these enhancements:
1. Add --verbose flag to CLI scripts for easy DEBUG mode
2. Add log rotation for long-running servers
3. Add metrics/monitoring integration hooks
4. Create web dashboard for watching multiple bots

## Implementation Details

**Centralized Logging Pattern:**
```python
from bbsbot.logging import get_logger

logger = get_logger(__name__)  # Module-specific logger
logger.debug("session_send", host=self.host, port=self.port, keys=repr(keys))
```

**No Configuration in Application Code:**
- Logging is configured once at server startup
- Modules just import and use get_logger()
- Environment variable controls verbosity

**Absolute Import Pattern:**
```python
# ❌ Old (relative)
from .io import wait_and_respond
from . import connection

# ✅ New (absolute)
from bbsbot.tw2002.io import wait_and_respond
from bbsbot.tw2002 import connection
```
