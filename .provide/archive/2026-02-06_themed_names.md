# Themed Bot Name Generator - Implementation Complete

## Summary

Implemented scalable themed name generation for BBSBot characters and ships. Bots now have memorable AI/trading-themed names instead of `bot001`, `bot002`, etc.

## Changes Completed

### 1. Core Name Generator (`src/bbsbot/games/tw2002/name_generator.py`)
- **NEW FILE**: Complete name generation system
- Supports 100,000+ unique combinations
- Four complexity levels:
  - `simple`: 2-part names (1,600 combos) - "QuantumTrader"
  - `medium`: 3-part names (77,000 combos) - "NeuralDataProfit"
  - `complex`: 4-part names (3.7M combos) - "QuantumNeuralDataTrader"
  - `numbered`: unlimited - "QuantumTrader47"
- Ship names: "Swift Venture", "Neural Horizon", optional roman numerals
- Collision avoidance with used name tracking
- Deterministic generation with optional seed

### 2. Configuration (`src/bbsbot/games/tw2002/config.py`)
- Updated `CharacterConfig` with themed name settings:
  - `name_complexity`: Literal["simple", "medium", "complex", "numbered"]
  - `generate_ship_names`: bool (default True)
  - `ship_names_with_numbers`: bool (default False)
  - `name_seed`: int | None (for reproducible names)
- Removed legacy `name_prefix` and `use_themed_names` (themed is now the only way)

### 3. Character State (`src/bbsbot/games/tw2002/character.py`)
- Added `ship_name: str | None` field to `CharacterState`
- Persisted in character JSON files

### 4. Multi-Character Manager (`src/bbsbot/games/tw2002/multi_character.py`)
- Integrated `NameGenerator` into character creation
- Added `generate_character_name()` - returns themed names
- Added `generate_ship_name()` - returns ship names or None
- Updated `CharacterRecord` to include `ship_name`
- Loads existing names on startup to avoid collisions
- Updated `create_character()` to generate and assign ship names

### 5. Tests (`tests/games/tw2002/test_name_generator.py`)
- **NEW FILE**: Comprehensive unit tests
- Tests for all complexity levels
- Uniqueness verification
- Collision avoidance
- Deterministic generation with seeds
- Statistics tracking

### 6. Example Config (`examples/configs/themed_names.yml`)
- **NEW FILE**: Complete working example
- Shows all configuration options
- Includes comments explaining each setting

## Word Lists

### Character Names (42 prefixes × 48 middles × 38 suffixes)
- **Prefixes**: Quantum, Neural, Algo, Cyber, Crypto, Digital, Smart, Meta...
- **Middles**: Data, Compute, Net, Metric, Process, Signal, Model...
- **Suffixes**: Trader, Profit, Broker, Agent, Alpha, Market, Capital...

### Ship Names (96 descriptors × 84 concepts)
- **Descriptors**: Swift, Silent, Mighty, Nova, Iron, Quantum, Storm...
- **Concepts**: Venture, Horizon, Phoenix, Dragon, Storm, Legacy...

## Example Output

```
=== Creating Characters ===
1. CyberCalculateOperator         - Ship: Solar Tiger
2. LogicByteTrade                 - Ship: Adamant Sword
3. AdaptPredictAgent              - Ship: Cloak Refuge
4. AdaptQueueMarket               - Ship: Regal Wyvern
5. CodeDataHedge                  - Ship: Streak Scimitar
```

## Configuration Examples

### Default (Medium Complexity)
```yaml
character:
  name_complexity: medium
  generate_ship_names: true
  ship_names_with_numbers: false
```

### Maximum Variety (Complex Names)
```yaml
character:
  name_complexity: complex  # 3.7M combinations
  generate_ship_names: true
  ship_names_with_numbers: true  # Add roman numerals
```

### Testing (Deterministic Names)
```yaml
character:
  name_complexity: medium
  name_seed: 42  # Same names every time
```

## Usage

### Create Character with Themed Names
```python
from bbsbot.games.tw2002.multi_character import MultiCharacterManager
from bbsbot.games.tw2002.config import BotConfig

config = BotConfig.from_yaml("config.yml")
manager = MultiCharacterManager(config, data_dir)

# Auto-generates themed name and ship name
char = manager.create_character()
print(f"Character: {char.name}")
print(f"Ship: {char.ship_name}")
```

### Manual Name Generation
```python
from bbsbot.games.tw2002.name_generator import NameGenerator

gen = NameGenerator(seed=123)  # Optional seed
char_name = gen.generate_character_name(complexity="medium")
ship_name = gen.generate_ship_name(add_number=False)
```

## Statistics

Generated names support massive scale:
- **Simple**: 1,596 unique names
- **Medium**: 76,608 unique names (default)
- **Complex**: 3,673,728 unique names
- **Ships**: 8,064 unique ship names
- **Ships with numerals**: 161,280 combinations

## Migration Notes

**NO MIGRATION NEEDED** - This is the only implementation:
- Old `name_prefix` field removed from config
- No legacy support or backward compatibility
- Themed names are the default and only option
- Existing character files will continue to work (ship_name is optional)

## Testing

### Unit Tests
```bash
pytest tests/games/tw2002/test_name_generator.py -v
```

### Integration Test
```bash
python -c "
from bbsbot.games.tw2002.multi_character import MultiCharacterManager
from bbsbot.games.tw2002.config import BotConfig
import tempfile
from pathlib import Path

with tempfile.TemporaryDirectory() as tmpdir:
    config = BotConfig.from_yaml('examples/configs/themed_names.yml')
    manager = MultiCharacterManager(config, Path(tmpdir))
    for i in range(5):
        char = manager.create_character()
        print(f'{char.name} - Ship: {char.ship_name}')
"
```

## Files Modified
- `src/bbsbot/games/tw2002/name_generator.py` - NEW
- `src/bbsbot/games/tw2002/config.py` - MODIFIED
- `src/bbsbot/games/tw2002/character.py` - MODIFIED
- `src/bbsbot/games/tw2002/multi_character.py` - MODIFIED
- `tests/games/tw2002/test_name_generator.py` - NEW
- `examples/configs/themed_names.yml` - NEW

## Next Steps (Optional Enhancements)

1. **Display ship names in game UI** - Update bot logs to show ship name
2. **Custom word lists** - Allow loading names from JSON files
3. **More themes** - Add sci-fi, fantasy, corporate name themes
4. **LLM generation** - Use Gemma3 to generate unique names on-demand
5. **Achievement titles** - Add suffixes based on bot performance

## Status

✅ **COMPLETE** - Feature is fully implemented and tested
- Name generation working
- Integration complete
- Tests passing
- Example config provided
- Documentation complete
