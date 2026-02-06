# BBSBot Documentation Index

**Complete documentation for the Trade Wars 2002 autonomous trading system.**

---

## Core System Documentation

### 1. [System Architecture](SYSTEM_ARCHITECTURE.md)
**Complete technical overview of the entire system**

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

### 2. [Architecture Diagrams](ARCHITECTURE_DIAGRAM.md)
**Visual representations of system components**

Includes diagrams for:
- Complete system stack (7 layers)
- LLM decision pipeline
- Multi-character knowledge sharing (3 modes)
- Game loop turn cycle
- Data persistence structure
- Character naming system

**Use this** for visual learners or quick reference.

---

### 3. [Themed Name Generator](HANDOFF_themed_names.md)
**Implementation details for character/ship naming**

Features:
- AI/economic/data-themed character names
- Space-themed ship names
- 4 complexity levels (1,600 to 3.7M combinations)
- Collision avoidance
- Multi-character integration
- Configuration examples
- Unit tests

**Reference this** for name generation specifics.

---

## Quick Start Guides

### For Users

**Run a bot with themed names**:
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

### For Developers

**Create multi-character bot**:
```python
from bbsbot.games.tw2002.multi_character import MultiCharacterManager
from bbsbot.games.tw2002.config import BotConfig

config = BotConfig.from_yaml("config.yml")
manager = MultiCharacterManager(config, data_dir)

# Generate themed characters
for i in range(3):
    char = manager.create_character()
    print(f"{char.name} - Ship: {char.ship_name}")
```

---

## Component Guides

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

## Configuration Reference

### Character Naming
```yaml
character:
  name_complexity: medium  # simple | medium | complex | numbered
  generate_ship_names: true
  ship_names_with_numbers: false
  name_seed: null  # Optional: for reproducible names
```

**Name Complexity**:
- `simple`: 2-part (1,600 names) - "QuantumTrader"
- `medium`: 3-part (77,000 names) - "NeuralDataProfit" [DEFAULT]
- `complex`: 4-part (3.7M names) - "QuantumNeuralDataTrader"
- `numbered`: Unlimited - "QuantumTrader47"

### Trading Strategy
```yaml
trading:
  strategy: ai_strategy  # profitable_pairs | opportunistic | twerk_optimized | ai_strategy

  profitable_pairs:
    max_hop_distance: 2
    min_profit_per_turn: 100

  opportunistic:
    explore_chance: 0.3
    max_wander_without_trade: 5

  twerk_optimized:
    data_dir: "/tmp/tw2002-data"
    recalculate_interval: 50

  ai_strategy:
    enabled: true
    fallback_strategy: opportunistic
    fallback_threshold: 3
    fallback_duration_turns: 10
    context_mode: summary
    timeout_ms: 30000
```

### Multi-Character Management
```yaml
multi_character:
  enabled: true
  max_characters: 50
  knowledge_sharing: shared  # shared | independent | inherit_on_death
```

**Knowledge Sharing Modes**:
- `shared`: All characters share sector database (fastest universe mapping)
- `independent`: Each character has isolated knowledge (simulates separate players)
- `inherit_on_death`: New character inherits from predecessor (generational transfer)

### LLM Configuration
```yaml
llm:
  provider: ollama  # ollama | openai

  ollama:
    base_url: http://localhost:11434
    model: gemma3
    timeout_seconds: 30.0
    max_retries: 3

  openai:
    api_key: ${OPENAI_API_KEY}
    model: gpt-4
    timeout_seconds: 30.0
```

---

## Example Configurations

### 1. Simple Bot (Opportunistic Strategy)
```yaml
# examples/configs/opportunistic.yml
connection:
  host: localhost
  port: 2002

character:
  name_complexity: simple
  generate_ship_names: true

trading:
  strategy: opportunistic

session:
  max_turns_per_session: 200
```

### 2. AI-Driven Bot (LLM Strategy)
```yaml
# examples/configs/ai_strategy_ollama.yml
connection:
  host: localhost
  port: 2002

character:
  name_complexity: medium
  generate_ship_names: true

trading:
  strategy: ai_strategy
  ai_strategy:
    enabled: true
    fallback_strategy: opportunistic
    context_mode: summary

llm:
  provider: ollama
  ollama:
    base_url: http://localhost:11434
    model: gemma3

session:
  max_turns_per_session: 500
```

### 3. Multi-Character Fleet
```yaml
# examples/configs/themed_names.yml
connection:
  host: localhost
  port: 2002

character:
  name_complexity: complex  # 3.7M combinations
  generate_ship_names: true
  ship_names_with_numbers: true  # Roman numerals

trading:
  strategy: profitable_pairs

multi_character:
  enabled: true
  max_characters: 50
  knowledge_sharing: shared  # All bots share discoveries

session:
  target_credits: 5000000
  max_turns_per_session: 500
```

---

## API Reference

### Multi-Character Management
```python
from bbsbot.games.tw2002.multi_character import MultiCharacterManager
from bbsbot.games.tw2002.config import BotConfig

# Create manager
config = BotConfig.from_yaml("config.yml")
manager = MultiCharacterManager(config, data_dir)

# Generate character
char = manager.create_character()
print(f"{char.name} - Ship: {char.ship_name}")

# Get statistics
stats = manager.name_generator.get_stats()
print(f"Total generated: {stats['total_generated']}")
print(f"Remaining medium: {stats['estimated_remaining_medium']:,}")
```

### Name Generator
```python
from bbsbot.games.tw2002.name_generator import NameGenerator

# Create generator
gen = NameGenerator(seed=42)  # Optional seed for reproducibility

# Generate character names
simple = gen.generate_character_name(complexity="simple")
medium = gen.generate_character_name(complexity="medium")
complex = gen.generate_character_name(complexity="complex")

# Generate ship names
ship = gen.generate_ship_name(add_number=False)
ship_numbered = gen.generate_ship_name(add_number=True)

# Collision avoidance
gen.mark_used("QuantumTrader")
new_name = gen.generate_character_name()  # Won't be "QuantumTrader"
```

---

## Testing

### Unit Tests
```bash
# Test name generator
pytest tests/games/tw2002/test_name_generator.py -v

# Test multi-character management
pytest tests/games/tw2002/test_multi_character.py -v

# Test all
pytest tests/ -v
```

### Integration Test
```python
# Test themed name generation
python -c "
from bbsbot.games.tw2002.name_generator import NameGenerator

gen = NameGenerator(seed=42)
for i in range(5):
    char = gen.generate_character_name()
    ship = gen.generate_ship_name()
    print(f'{i+1}. {char:30s} - Ship: {ship}')
"
```

---

## Troubleshooting

### Common Issues

**1. Names not themed / still seeing bot001**
- Check `character.name_complexity` is NOT set to `legacy`
- Verify config loaded correctly: `BotConfig.from_yaml(path)`
- The old `name_prefix` field is removed; themed names are now the only option

**2. Duplicate names across sessions**
- Check `character_records.json` exists and is loaded
- Verify `MultiCharacterManager` is persisting records
- Used names are loaded automatically on initialization

**3. LLM not responding**
- Verify Ollama is running: `curl http://localhost:11434/api/tags`
- Check model is downloaded: `ollama list`
- Verify timeout settings in config
- Check fallback strategy is configured

**4. Bot gets stuck in loops**
- Review `rules.json` patterns for conflicts
- Check `negative_match` patterns are specific enough
- Enable debug logging: `BBSBOT_LOG_LEVEL=DEBUG`
- Review session logs: `~/.bbsbot/tw2002/semantic/`

---

## Contributing

### Adding New Trading Strategy
1. Create strategy class in `src/bbsbot/games/tw2002/`
2. Implement `decide()` method
3. Add to config: `TradingConfig.strategy` enum
4. Add tests in `tests/games/tw2002/`
5. Document in architecture docs

### Adding New LLM Provider
1. Create provider class in `src/bbsbot/llm/`
2. Inherit from `LLMProvider` base class
3. Implement `generate()` method
4. Add to `LLMConfig.provider` enum
5. Add configuration section
6. Add tests

### Extending Name Generator
1. Add word lists to `name_generator.py`
2. Create new complexity level or pattern
3. Update `NameGenerator.generate_*` methods
4. Add tests for new patterns
5. Update documentation

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
