# BBSBot Documentation Index

**Complete documentation for the Trade Wars 2002 autonomous trading system.**

---

## Getting Started

- **[Quick Start Guide](guides/QUICK_START.md)** - Get running in 5 minutes
- **[Multi-Character Guide](guides/MULTI_CHARACTER.md)** - Run multiple bots
- **[Intelligent Bot Guide](guides/INTELLIGENT_BOT.md)** - AI-driven trading
- **[Examples](../examples/configs/)** - Example configurations

---

## Architecture

- **[System Architecture](SYSTEM_ARCHITECTURE.md)** - Complete technical overview
- **[Architecture Diagrams](ARCHITECTURE_DIAGRAM.md)** - Visual system diagrams

Topics covered:
- 7-layer architecture breakdown
- Component interaction and data flow
- Multi-character management system
- LLM integration and decision-making
- Game loop architecture
- Trading strategies (4 different modes)
- Configuration system
- Example bot session walkthrough

**Start here** for a complete understanding of how everything works together.

---

## Guides

- **[Quick Start](guides/QUICK_START.md)** - Get started in 5 minutes
- **[Multi-Character Management](guides/MULTI_CHARACTER.md)** - Managing multiple bots
- **[Intelligent Bot](guides/INTELLIGENT_BOT.md)** - Using AI strategies
- **[TW2002 MCP Operations](TW2002_MCP_OPERATIONS.md)** - Local MCP server aliasing, hijack flow, troubleshooting
- **[Swarm Operations + Telemetry](guides/SWARM_OPERATIONS_TELEMETRY.md)** - ROI interpretation, anti-collapse controls, degradation triage
- **[Release Checklist](RELEASE_CHECKLIST.md)** - Pre-release validation checklist
- **[Configuration](../README.md#configuration)** - Config + environment settings
- **[Spying / Watch Socket](../README.md#spy--watch-socket)** - Attach to a running session output

---

## Game-Specific Documentation

- **[TW2002 Documentation](../games/tw2002/docs/)** - Trade Wars 2002 specifics
  - [LLM Hints](../games/tw2002/docs/LLM_HINTS.md) - AI prompt guidance
  - [TEDIT Reference](../games/tw2002/docs/TEDIT_REFERENCE.md) - Port editor
  - [TWGS Login Flow](../games/tw2002/docs/TWGS_LOGIN_FLOW.md) - Login sequence
  - [BBS Login Solution](../games/tw2002/docs/bbs-login-solution.md) - Login troubleshooting

---

## Component Architecture

### Layer 1: Core MCP Server
- [README.md](../README.md) - Installation, MCP tools, usage
- Core components in `src/bbsbot/core/`
- Telnet transport in `src/bbsbot/transport/`
- Terminal emulation in `src/bbsbot/terminal/`

### Layer 2: Pattern Detection
- Rules: `src/bbsbot/games/tw2002/rules.json`
- Detection: `src/bbsbot/learning/detector.py`
- I/O: `src/bbsbot/games/tw2002/io.py`

### Layer 3: Game Mechanics
- Game state/orientation: `src/bbsbot/games/tw2002/orientation/`
- Navigation: `src/bbsbot/games/tw2002/bot_navigation.py`
- Trading execution/parsing: `src/bbsbot/games/tw2002/trading/`
- Combat: `src/bbsbot/games/tw2002/combat.py`

### Layer 4: LLM Integration
- LLM manager: `src/bbsbot/llm/manager.py`
- Providers: `src/bbsbot/llm/providers/`
- AI strategy: `src/bbsbot/games/tw2002/strategies/ai_strategy.py`
- Prompt generation: `src/bbsbot/games/tw2002/strategies/ai/prompts.py`

### Layer 5: Trading Strategies
- All strategies: `src/bbsbot/games/tw2002/strategies/`
- AI strategy: `src/bbsbot/games/tw2002/strategies/ai_strategy.py`
- Twerk optimized: `src/bbsbot/games/tw2002/strategies/twerk_optimized.py`

### Layer 6: Game Loop
- Main bot: `src/bbsbot/games/tw2002/bot.py`
- Connection: `src/bbsbot/games/tw2002/connection.py`

### Layer 7: Multi-Character
- Manager: `src/bbsbot/games/tw2002/multi_character.py`
- Name generator: `src/bbsbot/games/tw2002/name_generator.py`
- Character state: `src/bbsbot/games/tw2002/character.py`

---

## Quick Start Examples

### Run a simple bot
```bash
# 1. Create config
cat > config.yml <<EOF
connection:
  host: localhost
  port: 2002

character:
  name_complexity: medium
  generate_ship_names: true

trading:
  strategy: opportunistic

session:
  max_turns_per_session: 100
EOF

# 2. Run bot
bbsbot script play_tw2002_trading --config config.yml
```

### Use AI strategy
```bash
# Use example config
bbsbot script play_tw2002_trading --config examples/configs/ai_strategy_ollama.yml
```

See [examples/configs/](../examples/configs/) for more configurations.

Legacy one-off scripts were moved to archive folders during cleanup:
- `scripts/archive/`
- `src/bbsbot/commands/scripts/archive/`
- details: [archive notes](archive/SCRIPTS_ARCHIVE_2026-02-16.md)

---

## Developer API

See the top-level [README.md](../README.md) for MCP tool usage and code pointers.

Quick example:
```python
from bbsbot.games.tw2002.multi_character import MultiCharacterManager
from bbsbot.games.tw2002.config import BotConfig

# Create manager
config = BotConfig.from_yaml("config.yml")
manager = MultiCharacterManager(config, data_dir)

# Generate character
char = manager.create_character()
print(f"{char.name} - Ship: {char.ship_name}")
```

---

## Development

- **[Development](../README.md#development)** - Project workflow and local setup
- **[Testing](../README.md#testing)** - Running tests
- **[Known warnings](../README.md#known-warnings)** - Non-fatal warnings you may see at startup
- **[Release Checklist](RELEASE_CHECKLIST.md)** - Pre-release gate and sign-off

---

## Release Metadata

- Project package version: `0.2.1` (from `pyproject.toml`)
- Documentation state reflects pre-release work through 2026-02-16

---

## License

GNU Affero General Public License v3 or later (AGPL-3.0-or-later)

See [LICENSE](../LICENSE) for details.

---

**Last Updated**: 2026-02-16
**Documentation Version**: pre-release
**System Version**: 0.2.1
