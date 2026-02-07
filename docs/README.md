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
- **[Configuration](../README.md#configuration)** - Config file reference
- **[Debugging](../README.md#troubleshooting)** - Troubleshooting guide

---

## Reference

- **[API Reference](reference/API.md)** - Python API documentation
- **[Configuration Reference](reference/CONFIGURATION_REFERENCE.md)** - All config options
- **[Troubleshooting](reference/TROUBLESHOOTING.md)** - Common issues

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
- Game state: `src/bbsbot/games/tw2002/orientation.py`
- Navigation: `src/bbsbot/games/tw2002/navigation.py`
- Trading: `src/bbsbot/games/tw2002/trading.py`
- Combat: `src/bbsbot/games/tw2002/combat.py`

### Layer 4: LLM Integration
- Providers: `src/bbsbot/llm/provider.py`, `ollama.py`
- AI strategy: `src/bbsbot/games/tw2002/ai_strategy.py`
- Prompt generation: `src/bbsbot/llm/prompt.py`

### Layer 5: Trading Strategies
- All strategies: `src/bbsbot/games/tw2002/trading.py`
- AI strategy: `src/bbsbot/games/tw2002/ai_strategy.py`
- Twerk analysis: `src/bbsbot/games/tw2002/twerk.py`

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
python scripts/play_tw2002_trading.py --config config.yml
```

### Use AI strategy
```bash
# Use example config
python scripts/play_tw2002_trading.py --config examples/configs/ai_strategy_ollama.yml
```

See [examples/configs/](../examples/configs/) for more configurations.

---

## Developer API

See [reference/API.md](reference/API.md) for complete API documentation.

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

- **[Contributing](../CONTRIBUTING.md)** - How to contribute
- **[Testing](../README.md#testing)** - Running tests
- **[Troubleshooting](reference/TROUBLESHOOTING.md)** - Common issues

---

## Version History

- **0.3.0** (2026-02-06): Themed name generator, comprehensive architecture docs
- **0.2.0** (2026-02-05): Multi-character management, knowledge sharing
- **0.1.0** (2026-02-04): Initial release with core MCP server and trading bot

---

## License

MIT License - Copyright (c) 2026 Tim Perkins

See [LICENSE](../LICENSE) for details.

---

**Last Updated**: 2026-02-06
**Documentation Version**: 1.0.0
**System Version**: 0.3.0
