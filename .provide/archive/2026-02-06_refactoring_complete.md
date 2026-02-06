# Complete Refactoring: Logging, Imports, and Module Organization

## Summary of Changes

### 1. Centralized Logging with Settings Integration ✅

**Problem**: Logging configuration was duplicated and using raw `os.getenv()` instead of the existing `pydantic-settings` pattern.

**Solution**:
- Created `src/bbsbot/logging/config.py` with centralized logging configuration
- Logging now uses `Settings` class for configuration (single source of truth)
- Respects `BBSBOT_LOG_LEVEL` environment variable via pydantic-settings
- All logs write to stderr (MCP JSON-RPC uses stdout)

**Files Modified**:
- `src/bbsbot/logging/config.py` - NEW centralized logging with Settings integration
- `src/bbsbot/logging/__init__.py` - Exports only (no logic)
- `src/bbsbot/settings.py` - Restored `log_level` field (default: WARNING)
- `src/bbsbot/core/session.py` - Uses `get_logger(__name__)`
- `src/bbsbot/mcp/server.py` - Calls `configure_logging()` at startup
- `src/bbsbot/games/tw2002/logging_utils.py` - Uses centralized logger
- `src/bbsbot/games/tw2002/errors.py` - Replaced print() with logger

**Pattern**:
```python
from bbsbot.logging import configure_logging, get_logger

# At application startup
configure_logging()  # Auto-reads Settings which reads BBSBOT_LOG_LEVEL

# In modules
logger = get_logger(__name__)
logger.debug("event", key=value)
```

### 2. Module Reorganization: bbsbot.tw2002 → bbsbot.games.tw2002 ✅

**Problem**: Game-specific code mixed with core framework code. No clear namespace for games.

**Solution**:
- Created `src/bbsbot/games/` namespace
- Moved `src/bbsbot/tw2002/` → `src/bbsbot/games/tw2002/`
- Merged `src/bbsbot/game/tw2002/verification/` → `src/bbsbot/games/tw2002/verification/`
- Removed old `src/bbsbot/game/` directory
- Updated ALL imports across 47 files

**Migration**:
```bash
# Old imports
from bbsbot.tw2002 import TradingBot
from bbsbot.game.tw2002.verification import login_main

# New imports
from bbsbot.games.tw2002 import TradingBot
from bbsbot.games.tw2002.verification import login_main
```

### 3. Absolute Imports Throughout Codebase ✅

**Problem**: Relative imports (`from .module`) scattered throughout codebase.

**Solution**: Converted ALL relative imports to absolute imports.

**Files Updated** (complete conversion):
- `src/bbsbot/games/tw2002/*.py` - All 26 modules
- `src/bbsbot/games/tw2002/verification/*.py` - All verification modules
- `src/bbsbot/games/tw2002/strategies/*.py` - All strategy modules
- `src/bbsbot/core/session.py`
- All command scripts

**Pattern**:
```python
# ❌ Old (relative)
from .io import wait_and_respond
from . import connection
from ..utils import helper

# ✅ New (absolute)
from bbsbot.games.tw2002.io import wait_and_respond
from bbsbot.games.tw2002 import connection
from bbsbot.utils import helper
```

### 4. No Logic in __init__ Files ✅

**Problem**: Configuration and business logic in `__init__.py` files.

**Solution**:
- Moved logging configuration from `logging/__init__.py` to `logging/config.py`
- `__init__.py` files now only contain imports and `__all__` exports
- No function definitions, no configuration, no side effects

**Pattern**:
```python
# __init__.py - exports only
"""Module description."""

from bbsbot.module.implementation import function, Class

__all__ = ["function", "Class"]
```

### 5. Removed Print Statements from Core Code ✅

**Locations Fixed**:
- `src/bbsbot/core/session.py` - Lines 113-115, 137-139 (send/read status)
- `src/bbsbot/games/tw2002/errors.py` - Lines 26, 30 (loop detection warnings)

**Note**: CLI tools (`cli_impl.py`, `cli.py`) still use `print()` for user-facing output - this is appropriate for CLI interfaces.

## Architecture Benefits

### Clean MCP Protocol
- ✅ stdout is ONLY JSON-RPC (no pollution)
- ✅ stderr contains structured logs (configurable)
- ✅ Session logs (JSONL) remain comprehensive

### Consistent Configuration Pattern
- ✅ All config via `pydantic-settings` (Settings class)
- ✅ Environment variables use `BBSBOT_` prefix
- ✅ No raw `os.getenv()` scattered around
- ✅ Single source of truth

### Clear Module Organization
```
bbsbot/
├── core/           # Core framework (sessions, managers)
├── logging/        # Centralized logging
├── mcp/            # MCP server implementation
├── games/          # Game-specific code
│   └── tw2002/     # Trade Wars 2002
│       ├── verification/
│       └── strategies/
├── learning/       # AI learning engine
├── transport/      # Connection transports
└── terminal/       # Terminal emulation
```

### Maintainability
- ✅ Absolute imports are grep-friendly
- ✅ Centralized configuration is easy to find/modify
- ✅ No hidden side effects in imports
- ✅ Clear separation of concerns

## Usage Examples

### Configure Logging
```python
from bbsbot.settings import Settings
from bbsbot.logging import configure_logging, get_logger

# Option 1: Use environment variable
# BBSBOT_LOG_LEVEL=DEBUG python script.py

# Option 2: Programmatic
settings = Settings(log_level="DEBUG")
configure_logging(settings)

# In modules
logger = get_logger(__name__)
logger.info("event", key="value")
```

### Import Game Code
```python
from bbsbot.games.tw2002 import TradingBot, BotConfig
from bbsbot.games.tw2002.strategies import ProfitablePairsStrategy
from bbsbot.games.tw2002.verification import login_main
```

### Run with Debug Logging
```bash
# Default: WARNING level (clean, quiet)
bbsbot serve

# Debug: See all activity
BBSBOT_LOG_LEVEL=DEBUG bbsbot serve

# Info: See key events
BBSBOT_LOG_LEVEL=INFO bbsbot serve
```

## Duplicate Code Analysis

### Analyzed Patterns
- ✅ **Parsing functions**: Not duplicated - bot.py delegates to parsing.py (good design)
- ✅ **Manager classes**: Domain-specific, not duplicates
- ✅ **Config classes**: Type-safe configuration models, appropriate
- ✅ **Error handling**: Centralized in errors.py module

### Remaining Opportunities
1. **Regex patterns**: Could be compiled once and reused (minor optimization)
2. **Common validation logic**: Some validation repeated across modules
3. **Testing utilities**: Test helpers could be centralized

**Recommendation**: Current code structure is good. The remaining "duplication" is mostly domain-specific implementations that should stay separate.

## Files Changed

### Created
- `src/bbsbot/games/__init__.py`
- `src/bbsbot/logging/config.py`

### Modified (Core)
- `src/bbsbot/settings.py` - Added log_level back
- `src/bbsbot/logging/__init__.py` - Removed logic
- `src/bbsbot/core/session.py` - Removed print(), uses get_logger()
- `src/bbsbot/mcp/server.py` - Uses configure_logging()

### Moved
- `src/bbsbot/tw2002/*` → `src/bbsbot/games/tw2002/*`
- `src/bbsbot/game/tw2002/*` → `src/bbsbot/games/tw2002/*` (merged)

### Updated Imports (47 files)
- All `bbsbot.tw2002` → `bbsbot.games.tw2002`
- All `bbsbot.game.tw2002` → `bbsbot.games.tw2002`
- All relative imports → absolute imports (including TYPE_CHECKING blocks and lazy imports)

## Verification

### Test Imports
```python
# Verify new structure works
python -c "from bbsbot.games.tw2002 import TradingBot; print('✓ Import successful')"

# Verify logging works
python -c "from bbsbot.logging import configure_logging, get_logger; configure_logging(); logger = get_logger('test'); logger.info('test'); print('✓ Logging works')"
```

### Test Log Levels
```bash
# Should be quiet (WARNING default)
python -c "from bbsbot.logging import configure_logging, get_logger; configure_logging(); logger = get_logger('test'); logger.debug('hidden'); logger.warning('visible')"

# Should show debug
BBSBOT_LOG_LEVEL=DEBUG python -c "from bbsbot.logging import configure_logging, get_logger; configure_logging(); logger = get_logger('test'); logger.debug('visible')"
```

### Check No Print Pollution
```bash
# MCP server stdout should be clean
bbsbot serve 2>/dev/null | head -5  # Should only see JSON-RPC
```

## Next Steps

### Recommended Improvements
1. **Add type stubs** for better IDE support
2. **Create logging best practices** document
3. **Add metrics/telemetry** hooks to logging
4. **Implement log rotation** for long-running servers
5. **Add structured error types** instead of string error codes

### Additional Games
When adding new games, follow this pattern:
```
src/bbsbot/games/
├── tw2002/          # Existing
├── new_game/        # New game
│   ├── __init__.py  # Exports only
│   ├── bot.py       # Main bot class
│   ├── config.py    # pydantic models
│   ├── parsing.py   # Game-specific parsing
│   └── strategies/  # Game strategies
```

## Design Principles Established

1. **Single Source of Truth**: Settings class for all configuration
2. **Absolute Imports**: Always use full module paths
3. **No Init Logic**: `__init__.py` files only export
4. **Centralized Logging**: One configuration point, many consumers
5. **Structured Logs**: Always use key=value format, never string interpolation
6. **Clean Interfaces**: stdout for protocol, stderr for logs, files for data
7. **Type Safety**: pydantic for configuration, type hints throughout

## Breaking Changes

### Import Changes Required
All code importing `bbsbot.tw2002` must update to `bbsbot.games.tw2002`:

```python
# Old
from bbsbot.tw2002 import TradingBot

# New
from bbsbot.games.tw2002 import TradingBot
```

### No Behavior Changes
- All functionality preserved
- API signatures unchanged
- Configuration still via BBSBOT_* environment variables
- Session logging still writes JSONL files
- MCP tools unchanged

## Summary

This refactoring establishes a solid architectural foundation:
- ✅ Clean separation of concerns
- ✅ Consistent patterns throughout
- ✅ Type-safe configuration
- ✅ Maintainable module structure
- ✅ Production-ready logging
- ✅ Server architecture preserved

The codebase is now ready for multi-game expansion and easier to maintain.
