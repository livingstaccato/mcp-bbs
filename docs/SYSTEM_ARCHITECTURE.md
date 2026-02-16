# BBSBot System Architecture

**Complete System Overview - Trade Wars 2002 Autonomous Trading Bot**

## Table of Contents

1. [System Overview](#system-overview)
2. [Architecture Layers](#architecture-layers)
3. [Component Interaction](#component-interaction)
4. [Multi-Character Management](#multi-character-management)
5. [LLM Integration](#llm-integration)
6. [Game Loop Architecture](#game-loop-architecture)
7. [Data Flow](#data-flow)
8. [Configuration System](#configuration-system)

---

## System Overview

BBSBot is a multi-layered autonomous trading system for Trade Wars 2002. It combines:
- **Core MCP Server**: Telnet/BBS connection and terminal emulation
- **Game Framework**: TW2002-specific game mechanics and navigation
- **Trading Strategies**: Multiple algorithmic and AI-driven trading approaches
- **Multi-Character System**: Manages multiple bot characters with knowledge sharing
- **LLM Integration**: Uses language models for decision-making and learning

```
┌─────────────────────────────────────────────────────────────────┐
│                     BBSBot System Stack                         │
├─────────────────────────────────────────────────────────────────┤
│  ┌────────────────────────────────────────────────────────┐    │
│  │ Multi-Character Management (themed names)              │    │
│  │  - NameGenerator: AI/trading-themed character names     │    │
│  │  - CharacterState: Per-character resources & progress   │    │
│  │  - Knowledge Sharing: shared/independent/inherit        │    │
│  └──────────────────────┬─────────────────────────────────┘    │
│                         │                                        │
│  ┌────────────────────────────────────────────────────────┐    │
│  │ Game Loop & Trading Strategies                         │    │
│  │  - TradingBot: Main game loop orchestrator             │    │
│  │  - ProfitablePairs: Pre-computed route trading         │    │
│  │  - Opportunistic: Explore and trade                    │    │
│  │  - TwerkOptimized: Offline data analysis               │    │
│  │  - AIStrategy: LLM-driven decision making              │    │
│  └──────────────────────┬─────────────────────────────────┘    │
│                         │                                        │
│  ┌────────────────────────────────────────────────────────┐    │
│  │ LLM Integration Layer                                  │    │
│  │  - Provider Abstraction: Ollama / OpenAI / etc         │    │
│  │  - Prompt Generation: Context → Decision               │    │
│  │  - Response Parsing: LLM output → Actions              │    │
│  │  - Learning Engine: Track outcomes, improve prompts    │    │
│  └──────────────────────┬─────────────────────────────────┘    │
│                         │                                        │
│  ┌────────────────────────────────────────────────────────┐    │
│  │ Game Mechanics Layer (TW2002)                          │    │
│  │  - GameState: Universe topology, sector knowledge      │    │
│  │  - Orientation: Sector detection, port identification  │    │
│  │  - Navigation: Warp planning, pathfinding              │    │
│  │  - Trading: Buy/sell logic, profit calculation         │    │
│  │  - Combat: Threat avoidance, sector danger tracking    │    │
│  └──────────────────────┬─────────────────────────────────┘    │
│                         │                                        │
│  ┌────────────────────────────────────────────────────────┐    │
│  │ Pattern Detection & Response (BBS Navigation)          │    │
│  │  - PromptDetector: Regex-based screen pattern matching │    │
│  │  - RuleEngine: Validate expected vs actual prompts     │    │
│  │  - IOManager: Send/wait/validate cycle                 │    │
│  └──────────────────────┬─────────────────────────────────┘    │
│                         │                                        │
│  ┌────────────────────────────────────────────────────────┐    │
│  │ Core MCP Server (bbsbot)                               │    │
│  │  - SessionManager: Connection lifecycle                │    │
│  │  - TerminalEmulator: ANSI/CP437 terminal (pyte)        │    │
│  │  - TelnetTransport: RFC 854 protocol, IAC escaping     │    │
│  │  - SessionLogger: JSONL logging with raw bytes         │    │
│  └──────────────────────┬─────────────────────────────────┘    │
│                         │                                        │
│                         ↓                                        │
│              ┌─────────────────────┐                            │
│              │  TWGS BBS Server    │                            │
│              │  Trade Wars 2002    │                            │
│              └─────────────────────┘                            │
└─────────────────────────────────────────────────────────────────┘
```

---

## Architecture Layers

### Layer 1: Core MCP Server

**Purpose**: Provide low-level BBS connectivity and terminal emulation

**Components**:
- **SessionManager**: Creates and manages telnet sessions
- **Session**: Per-connection state with terminal emulator
- **TelnetTransport**: Handles RFC 854 telnet protocol
- **TerminalEmulator** (pyte): ANSI escape code processing, 80x25 buffer
- **SessionLogger**: Records all I/O to JSONL for debugging

**Key Features**:
- Full telnet option negotiation (BINARY, SGA, NAWS, TTYPE)
- IAC byte escaping for binary-safe transmission
- Screen snapshots with hashing for change detection
- Raw byte logging for troubleshooting

**Files**:
- `src/bbsbot/core/session_manager.py`
- `src/bbsbot/core/session.py`
- `src/bbsbot/transport/telnet.py`
- `src/bbsbot/terminal/emulator.py`

---

### Layer 2: Pattern Detection & Response

**Purpose**: Navigate BBS menus and detect game prompts

**Components**:
- **PromptDetector**: Regex-based pattern matching against screen text
- **LearningEngine**: Auto-discovers menu options and prompts
- **RuleEngine**: Validates expected vs actual prompt sequences
- **IOManager**: High-level send/wait/validate operations

**Key Features**:
- Rules loaded from `games/tw2002/rules.json`
- Pattern matching with negative matches for disambiguation
- Automatic pagination detection (press any key, more prompts)
- Semantic K/V extraction from game screens (sector #, credits, etc)

**Pattern Example**:
```json
{
  "prompt_id": "prompt.sector_command",
  "pattern": "Command \\[\\?=Help\\]:",
  "input_type": "single_key",
  "negative_match": "Computer command"
}
```

**Files**:
- `src/bbsbot/learning/detector.py`
- `src/bbsbot/learning/engine.py`
- `src/bbsbot/games/tw2002/io.py`
- `src/bbsbot/games/tw2002/rules.json`

---

### Layer 3: Game Mechanics Layer

**Purpose**: Implement TW2002-specific game logic

**Components**:
- **GameState**: Sector topology, warps, ports, planets
- **SectorKnowledge**: Per-sector discovery (ports, planet types, danger)
- **Orientation**: Detect current sector from screen text
- **Navigation**: Pathfinding with BFS, route planning
- **Trading**: Port class detection, buy/sell logic, profit calculation
- **Combat**: Danger zone tracking, sector avoidance

**Key Features**:
- Sector graph built from warp connections
- Port classification (Class 1-9, Special/Genesis)
- Profit calculation: `(sell_price - buy_price) * holds - distance`
- Danger zone cooldown (avoid sectors with recent combat)
- BFS pathfinding for shortest routes

**Data Structures**:
```python
class SectorKnowledge:
    sector_id: int
    warps: set[int]
    has_port: bool
    port_class: str | None
    port_buys: set[str]
    port_sells: set[str]
    last_visited: float
    danger_level: int
```

**Files**:
- `src/bbsbot/games/tw2002/orientation/`
- `src/bbsbot/games/tw2002/bot_navigation.py`
- `src/bbsbot/games/tw2002/trading/`
- `src/bbsbot/games/tw2002/combat.py`

---

### Layer 4: LLM Integration

**Purpose**: AI-driven decision making using language models

**Components**:
- **LLMProvider**: Abstract interface for LLM backends
- **OllamaProvider**: Local model inference (Gemma3, Llama, etc)
- **OpenAIProvider**: OpenAI API (future)
- **PromptGenerator**: Build decision prompts from game context
- **ResponseParser**: Extract actions from LLM responses
- **LearningEngine**: Track decision outcomes, improve prompts

**Decision Flow**:
```
GameState → PromptGenerator → LLM → ResponseParser → Action
     ↓                                                   ↓
  Context                                          Outcome
  (sectors,                                      (profit,
   credits,                                       success,
   history)                                       errors)
                                                     ↓
                                            LearningEngine
                                          (update prompts)
```

**Prompt Structure**:
```
You are a Trade Wars 2002 trading bot in sector {sector}.

Current Status:
- Credits: {credits}
- Holds: {holds_used}/{holds_total}
- Turns: {turns_remaining}

Nearby Sectors:
- Sector 5: Class 2 port (Ore, Equipment) - 1 warp away
- Sector 12: Class 7 port (Food, Organics) - 2 warps away

Recent History:
- Bought Ore at Sector 5 for 15/unit
- Sold Ore at Sector 12 for 55/unit (+2000 profit)

What should you do? Respond with ONE action:
- WARP <sector> - Move to sector
- TRADE - Buy/sell at current port
- WAIT - Skip this turn
- QUIT - End session
```

**Response Parsing**:
```python
# LLM output: "WARP 12"
action = parse_llm_response(response)
# Returns: {"action": "warp", "target": 12}
```

**Files**:
- `src/bbsbot/llm/manager.py`
- `src/bbsbot/llm/providers/ollama.py`
- `src/bbsbot/llm/providers/openai.py`
- `src/bbsbot/games/tw2002/strategies/ai/prompts.py`
- `src/bbsbot/games/tw2002/strategies/ai/parser.py`
- `src/bbsbot/games/tw2002/strategies/ai_strategy.py`

---

### Layer 5: Trading Strategies

**Purpose**: Different algorithmic and AI approaches to maximize profit

**Strategies**:

#### 1. Profitable Pairs (Mode A)
- Pre-compute all buy-sell pairs
- Filter by minimum profit and max hop distance
- Execute highest-profit route each turn
- Fast, deterministic, simple

#### 2. Opportunistic (Mode B)
- Explore universe randomly
- Trade when profitable opportunities found
- Balance exploration vs exploitation
- Good for universe discovery

#### 3. Twerk Optimized (Mode C)
- Offline analysis of sector/port data from game files
- Find optimal trade routes using external data
- Pre-plan entire trading session
- Most efficient if data available

#### 4. AI Strategy (Mode D)
- LLM makes real-time decisions
- Learns from outcomes
- Adapts to changing universe conditions
- Handles unexpected situations
- Fallback to simpler strategy on repeated failures

**Strategy Selection**:
```yaml
trading:
  strategy: ai_strategy  # profitable_pairs | opportunistic | twerk_optimized | ai_strategy

  ai_strategy:
    enabled: true
    fallback_strategy: opportunistic
    fallback_threshold: 3  # Failures before fallback
    fallback_duration_turns: 10
```

**Files**:
- `src/bbsbot/games/tw2002/strategies/profitable_pairs.py`
- `src/bbsbot/games/tw2002/strategies/opportunistic.py`
- `src/bbsbot/games/tw2002/strategies/twerk_optimized.py`
- `src/bbsbot/games/tw2002/strategies/ai_strategy.py`

---

### Layer 6: Game Loop Architecture

**Purpose**: Main execution loop for bot operation

**Game Loop Phases**:

```
┌─────────────────────────────────────────────────────────────────┐
│                        Game Loop                                │
└─────────────────────────────────────────────────────────────────┘

1. CONNECT
   ├─ Telnet connection to TWGS BBS
   ├─ Navigate login menus
   ├─ Select game, enter credentials
   └─ Reach sector command prompt

2. ORIENT
   ├─ Detect current sector from screen
   ├─ Update GameState.current_sector
   ├─ Check for port presence
   └─ Extract semantic K/V data

3. DECIDE (Strategy-dependent)
   ├─ Collect nearby sector info
   ├─ Calculate possible trades
   ├─ Choose action: WARP | TRADE | SCAN | WAIT
   └─ (AI Strategy: call LLM for decision)

4. EXECUTE
   ├─ Send command to game
   ├─ Wait for prompt
   ├─ Validate expected vs actual
   └─ Handle errors/anomalies

5. RECORD
   ├─ Update CharacterState (credits, turns, profit)
   ├─ Save sector knowledge to database
   ├─ Log action → outcome
   └─ Update danger zones if combat

6. CHECK GOALS
   ├─ Target credits reached?
   ├─ Max turns exceeded?
   ├─ Character died?
   └─ If yes → EXIT, else → loop to step 2

7. EXIT
   ├─ Send quit command
   ├─ Confirm quit prompt
   ├─ Save final state
   └─ Disconnect session
```

**Turn Cycle**:
```python
while character.turns_used < config.max_turns:
    # Orient
    await orient(session, game_state)

    # Decide
    action = await strategy.decide(game_state, character)

    # Execute
    result = await execute_action(session, action, game_state)

    # Record
    character.turns_used += 1
    character.credits = result.credits
    await save_state(character)

    # Check goals
    if character.credits >= config.target_credits:
        break
    if character.deaths > 0:
        character = handle_death(character)
```

**Files**:
- `src/bbsbot/games/tw2002/bot.py`
- `src/bbsbot/games/tw2002/connection.py`

---

### Layer 7: Multi-Character Management

**Purpose**: Manage multiple bot characters with optional knowledge sharing

**Components**:
- **MultiCharacterManager**: Character lifecycle, naming, rotation
- **NameGenerator**: Themed AI/trading-themed character and ship names
- **CharacterState**: Per-character resources, progress, stats
- **CharacterRecord**: Historical tracking across sessions

**Themed Name Generation**:
```python
# Character names: AI/economic/data themed
NameGenerator(seed=42)
  → "QuantumTrader"
  → "NeuralDataProfit"
  → "CryptoByteMarket"

# Ship names: Two-word combinations
  → "Swift Venture"
  → "Neural Horizon"
  → "Dark Fortune III"
```

**Name Complexity Levels**:
- **Simple**: 2-part names (1,600 combinations) - "QuantumTrader"
- **Medium**: 3-part names (77,000 combinations) - "NeuralDataProfit" *[DEFAULT]*
- **Complex**: 4-part names (3.7M combinations) - "QuantumNeuralDataTrader"
- **Numbered**: Unlimited - "QuantumTrader47"

**Knowledge Sharing Modes**:

1. **Shared** (default)
   - All characters share sector knowledge
   - Common sector database
   - Fastest universe mapping

2. **Independent**
   - Each character has isolated knowledge
   - No sharing between characters
   - Simulates separate players

3. **Inherit on Death**
   - New character inherits from dead predecessor
   - Simulates generational knowledge transfer
   - Balance of isolation and continuity

**Character Lifecycle**:
```
CREATE
  ├─ Generate themed name (e.g., "CryptoDataTrader")
  ├─ Generate ship name (e.g., "Swift Phoenix")
  ├─ Initialize state (credits=1000, turns=150)
  └─ Create character record

PLAY
  ├─ Load character state
  ├─ Execute game loop
  ├─ Track: profits, deaths, turns played
  └─ Save state periodically

DEATH
  ├─ Mark character as dead
  ├─ Record final stats
  ├─ Create successor (if inherit mode)
  └─ Transfer knowledge (if inherit mode)

RETIRE
  ├─ Character reaches max sessions
  ├─ Save final record
  └─ Remove from active rotation
```

**Files**:
- `src/bbsbot/games/tw2002/multi_character.py`
- `src/bbsbot/games/tw2002/name_generator.py`
- `src/bbsbot/games/tw2002/character.py`

---

## Component Interaction

### Full Request Flow: "Warp to Sector 5"

```
┌──────────────────┐
│  Game Loop       │  "Strategy decided to warp to sector 5"
└────────┬─────────┘
         │
         ↓
┌─────────────────────────────────────────────────────────┐
│  Navigation Layer                                       │
│  ├─ Plan route: BFS from current to target             │
│  ├─ Result: [current_sector, 12, 5]                    │
│  └─ Return: "M\r12\r" (move command + sector)          │
└────────┬────────────────────────────────────────────────┘
         │
         ↓
┌─────────────────────────────────────────────────────────┐
│  IOManager                                              │
│  ├─ send("M\r", expect="prompt.warp_target")           │
│  │    ↓                                                 │
│  │  ┌──────────────────────────────────────┐           │
│  │  │  PromptDetector                      │           │
│  │  │  ├─ Wait for screen update            │          │
│  │  │  ├─ Match regex for warp prompt       │          │
│  │  │  └─ Return: {prompt_id, input_type}   │          │
│  │  └──────────────────────────────────────┘           │
│  │                                                      │
│  ├─ send("12\r", expect="prompt.sector_command")       │
│  └─ Validate: sector changed to 5                      │
└────────┬────────────────────────────────────────────────┘
         │
         ↓
┌─────────────────────────────────────────────────────────┐
│  Session (MCP Layer)                                    │
│  ├─ session.send("M\r")                                 │
│  │    ↓                                                 │
│  │  ┌──────────────────────────────────────┐           │
│  │  │  TelnetTransport                     │           │
│  │  │  ├─ Encode CP437                     │           │
│  │  │  ├─ Escape IAC bytes                 │           │
│  │  │  └─ Send via socket                  │           │
│  │  └──────────────────────────────────────┘           │
│  │                                                      │
│  ├─ session.read(timeout_ms=1000)                      │
│  │    ↓                                                 │
│  │  ┌──────────────────────────────────────┐           │
│  │  │  TelnetTransport                     │           │
│  │  │  ├─ Receive bytes                    │           │
│  │  │  ├─ Parse telnet options (IAC)       │           │
│  │  │  └─ Return raw data                  │           │
│  │  └─────────────┬────────────────────────┘           │
│  │                ↓                                     │
│  │  ┌──────────────────────────────────────┐           │
│  │  │  TerminalEmulator (pyte)             │           │
│  │  │  ├─ Process ANSI escape codes        │           │
│  │  │  ├─ Update 80x25 screen buffer       │           │
│  │  │  ├─ Track cursor position             │           │
│  │  │  └─ Return formatted screen text      │           │
│  │  └──────────────────────────────────────┘           │
│  │                                                      │
│  └─ Return snapshot: {screen, cursor, hash}            │
└────────┬────────────────────────────────────────────────┘
         │
         ↓
┌─────────────────────────────────────────────────────────┐
│  Orientation Layer                                      │
│  ├─ Parse screen for sector number                      │
│  ├─ Extract warp list                                   │
│  ├─ Detect port presence/class                          │
│  └─ Update GameState.current_sector = 5                 │
└─────────────────────────────────────────────────────────┘
```

---

## Data Flow

### Knowledge Persistence

```
┌──────────────────────────────────────────────────────────┐
│  Game Session                                            │
│  ├─ Discover sector 5: has Class 2 port                 │
│  ├─ Discover warp: 5 → 12                               │
│  └─ Record profit: bought Ore @15, sold @55 (+2000)     │
└────────┬─────────────────────────────────────────────────┘
         │
         ↓
┌──────────────────────────────────────────────────────────┐
│  GameState (in-memory)                                   │
│  sectors: {                                              │
│    5: SectorKnowledge(                                   │
│      warps={12, 17, 23},                                 │
│      has_port=True,                                      │
│      port_class="Class 2",                               │
│      port_buys={"Ore"},                                  │
│      port_sells={"Equipment"}                            │
│    )                                                     │
│  }                                                       │
└────────┬─────────────────────────────────────────────────┘
         │
         ↓ (save periodically)
┌──────────────────────────────────────────────────────────┐
│  Character State File                                    │
│  ~/.bbsbot/tw2002/QuantumTrader_state.json              │
│  {                                                       │
│    "name": "QuantumTrader",                             │
│    "ship_name": "Swift Venture",                        │
│    "credits": 45000,                                     │
│    "turns_used": 87,                                     │
│    "visited_sectors": [1, 5, 12, 17, 23, ...],          │
│    "scanned_sectors": {5: 1738814400.0, ...}            │
│  }                                                       │
└────────┬─────────────────────────────────────────────────┘
         │
         ↓ (shared mode)
┌──────────────────────────────────────────────────────────┐
│  Shared Sector Database                                  │
│  ~/.bbsbot/tw2002/shared_sectors.json                   │
│  {                                                       │
│    "5": {                                                │
│      "warps": [12, 17, 23],                              │
│      "port_class": "Class 2",                            │
│      "last_visited": 1738814400.0                        │
│    },                                                    │
│    ...                                                   │
│  }                                                       │
└──────────────────────────────────────────────────────────┘
```

---

## Configuration System

**Hierarchical Configuration**:
```yaml
# examples/configs/themed_names.yml

connection:
  host: localhost
  port: 2002

character:
  password: trade123
  name_complexity: medium  # Character name generation
  generate_ship_names: true
  ship_names_with_numbers: false

trading:
  strategy: ai_strategy  # Strategy selection

  ai_strategy:
    enabled: true
    fallback_strategy: opportunistic
    context_mode: summary
    timeout_ms: 30000

multi_character:
  enabled: true
  max_characters: 50
  knowledge_sharing: shared  # shared | independent | inherit_on_death

session:
  target_credits: 5000000
  max_turns_per_session: 500

llm:
  provider: ollama
  ollama:
    base_url: http://localhost:11434
    model: gemma3
```

**Configuration Loading**:
```python
from bbsbot.games.tw2002.config import BotConfig

# Load from YAML
config = BotConfig.from_yaml("config.yml")

# Override from environment
# BBSBOT_CHARACTER__NAME_COMPLEXITY=complex
# BBSBOT_TRADING__STRATEGY=opportunistic

# Access nested config
config.character.name_complexity  # "medium"
config.trading.strategy  # "ai_strategy"
config.llm.ollama.model  # "gemma3"
```

---

## Example: Complete Bot Session

```python
from bbsbot.games.tw2002.bot import TradingBot
from bbsbot.games.tw2002.config import BotConfig
from bbsbot.games.tw2002.multi_character import MultiCharacterManager

# Load configuration
config = BotConfig.from_yaml("themed_names.yml")

# Create multi-character manager
manager = MultiCharacterManager(config, data_dir=Path("~/.bbsbot"))

# Create themed character
char_state = manager.create_character()
print(f"Character: {char_state.name}")
print(f"Ship: {char_state.ship_name}")
# Output:
# Character: CryptoDataTrader
# Ship: Swift Phoenix

# Create bot for character
bot = TradingBot(
    character_name=char_state.name,
    ship_name=char_state.ship_name,
    config=config
)

# Run bot session
await bot.run_session()
# Bot will:
# 1. Connect to TWGS (localhost:2002)
# 2. Login as CryptoDataTrader
# 3. Orient to current sector
# 4. Execute trading strategy (AI or algorithmic)
# 5. Record profits, update state
# 6. Handle death → create successor
# 7. Save final state and disconnect
```

**Output**:
```
[2026-02-06 15:30:42] Created character: CryptoDataTrader (Ship: Swift Phoenix)
[2026-02-06 15:30:43] Connected to localhost:2002
[2026-02-06 15:30:45] Logged in as CryptoDataTrader
[2026-02-06 15:30:46] Oriented: Sector 1, no port
[2026-02-06 15:30:47] Strategy: AI decided to warp to sector 5
[2026-02-06 15:30:48] Warped to sector 5 (Class 2 port)
[2026-02-06 15:30:49] Bought 20 Ore @ 15 credits/unit
[2026-02-06 15:30:52] Warped to sector 12 (Class 7 port)
[2026-02-06 15:30:53] Sold 20 Ore @ 55 credits/unit (+800 profit)
...
[2026-02-06 16:15:30] Target reached: 5,120,000 credits (120,000 profit)
[2026-02-06 16:15:31] Session complete. Turns used: 487/500
[2026-02-06 16:15:32] Saved state to ~/.bbsbot/tw2002/CryptoDataTrader_state.json
[2026-02-06 16:15:33] Disconnected
```

---

## Summary

BBSBot is a sophisticated autonomous trading system that combines:
- **Low-level infrastructure**: Telnet, terminal emulation, logging
- **Pattern-based navigation**: Regex prompts, screen validation
- **Game mechanics**: Sector graphs, pathfinding, trading logic
- **AI integration**: LLM-driven decisions with learning
- **Multi-character management**: Themed names, knowledge sharing
- **Multiple strategies**: Algorithmic and AI-driven trading

The system is designed for both fully autonomous operation and human-in-the-loop debugging, with comprehensive logging, state persistence, and error recovery.

---

**Last Updated**: 2026-02-16
**Version**: 0.2.1 (pre-release)
