# BBSBot Architecture Diagrams

## Complete System Stack

```
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃                      BBSBOT SYSTEM STACK                          ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛

┌──────────────────────────────────────────────────────────────────┐
│  LAYER 7: Multi-Character Management                             │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ NameGenerator          CharacterState      CharacterRecord │  │
│  │  - Themed names         - Resources         - History      │  │
│  │  - Ship names           - Progress          - Lineage      │  │
│  │  - Collision avoid      - Knowledge         - Stats        │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
                                 ↓
┌──────────────────────────────────────────────────────────────────┐
│  LAYER 6: Game Loop & Bot Orchestration                          │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ TradingBot (Main Loop)                                     │  │
│  │  1. CONNECT  → 2. ORIENT → 3. DECIDE → 4. EXECUTE         │  │
│  │     ↓            ↓          ↓           ↓                  │  │
│  │  5. RECORD  → 6. CHECK GOALS → 7. EXIT or LOOP            │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
                                 ↓
┌──────────────────────────────────────────────────────────────────┐
│  LAYER 5: Trading Strategies                                     │
│  ┌──────────────┬──────────────┬──────────────┬──────────────┐  │
│  │ Profitable   │ Opportunistic│ Twerk        │ AI Strategy  │  │
│  │ Pairs        │              │ Optimized    │              │  │
│  │              │              │              │              │  │
│  │ Pre-computed │ Explore &    │ Offline data │ LLM-driven   │  │
│  │ routes       │ trade        │ analysis     │ decisions    │  │
│  └──────────────┴──────────────┴──────────────┴──────────────┘  │
└──────────────────────────────────────────────────────────────────┘
                                 ↓
┌──────────────────────────────────────────────────────────────────┐
│  LAYER 4: LLM Integration (Optional)                             │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ Provider Abstraction                                       │  │
│  │  ┌─────────────┬──────────────┬──────────────────────┐    │  │
│  │  │ Ollama      │ OpenAI       │ Custom Providers     │    │  │
│  │  └─────────────┴──────────────┴──────────────────────┘    │  │
│  │                                                            │  │
│  │ PromptGenerator → LLM → ResponseParser → LearningEngine   │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
                                 ↓
┌──────────────────────────────────────────────────────────────────┐
│  LAYER 3: Game Mechanics (TW2002)                                │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ GameState    Orientation    Navigation    Trading          │  │
│  │  - Sectors    - Detect       - Pathfind    - Buy/Sell     │  │
│  │  - Warps      - Parse        - Route       - Profit calc  │  │
│  │  - Ports      - Validate     - BFS         - Port class   │  │
│  │                                                            │  │
│  │ Combat       Knowledge       Banking       Upgrades        │  │
│  │  - Danger     - Persist      - Deposits    - Holds/       │  │
│  │  - Avoid      - Share        - Withdraws   - Shields      │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
                                 ↓
┌──────────────────────────────────────────────────────────────────┐
│  LAYER 2: Pattern Detection & BBS Navigation                     │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ PromptDetector   RuleEngine   IOManager   LearningEngine  │  │
│  │  - Regex match   - Validate    - Send      - Discovery    │  │
│  │  - Screen text   - Expect      - Wait      - Menus        │  │
│  │  - Cursor pos    - Actual      - Validate  - Prompts      │  │
│  │                                                            │  │
│  │ Rules: games/tw2002/rules.json (50+ prompt patterns)      │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
                                 ↓
┌──────────────────────────────────────────────────────────────────┐
│  LAYER 1: Core MCP Server (bbsbot)                               │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ SessionManager                                             │  │
│  │  ├─ Session (per-connection)                               │  │
│  │  │   ├─ TerminalEmulator (pyte: ANSI/CP437)               │  │
│  │  │   ├─ TelnetTransport (RFC 854, IAC escaping)           │  │
│  │  │   └─ SessionLogger (JSONL with raw bytes)              │  │
│  │  └─ Keepalive, timeouts, resource limits                  │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
                                 ↓
                     ┌───────────────────────┐
                     │   TWGS BBS Server     │
                     │   Trade Wars 2002     │
                     │   localhost:2002      │
                     └───────────────────────┘
```

---

## LLM Decision Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                   LLM Decision Pipeline                         │
└─────────────────────────────────────────────────────────────────┘

Game State                    Prompt Generator
  ├─ Current sector: 5    ─→   ┌────────────────────┐
  ├─ Credits: 45000            │ Build context:     │
  ├─ Holds: 15/20              │  - Status          │
  ├─ Nearby ports              │  - Options         │
  │   • Sector 12 (Class 7)    │  - History         │
  │   • Sector 23 (Class 2)    │  - Constraints     │
  └─ Recent trades             └──────┬─────────────┘
                                      │
                                      ↓
                              ┌────────────────────┐
                              │  LLM Provider      │
                              │  (Ollama/OpenAI)   │
                              │                    │
                              │  Input: Prompt     │
                              │  Model: gemma3     │
                              │  Timeout: 30s      │
                              └──────┬─────────────┘
                                      │
                                      ↓
                              ┌────────────────────┐
                              │  LLM Response      │
                              │  "WARP 12"         │
                              │  or                │
                              │  "TRADE"           │
                              │  or                │
                              │  "WAIT"            │
                              └──────┬─────────────┘
                                      │
                                      ↓
                              ┌────────────────────┐
                              │ Response Parser    │
                              │  Extract action    │
                              │  Validate format   │
                              │  Handle errors     │
                              └──────┬─────────────┘
                                      │
                                      ↓
                              ┌────────────────────┐
                              │  Action Decision   │
                              │  {                 │
                              │   action: "warp",  │
                              │   target: 12       │
                              │  }                 │
                              └──────┬─────────────┘
                                      │
                                      ↓
Execute Action                ┌────────────────────┐
  ├─ Warp to 12               │  Track Outcome     │
  ├─ Trade if profitable      │   - Success?       │
  └─ Record profit            │   - Profit amount  │
                              │   - Errors         │
                              └──────┬─────────────┘
                                      │
                                      ↓
                              ┌────────────────────┐
                              │ Learning Engine    │
                              │  Update prompts    │
                              │  Refine strategies │
                              │  Improve decisions │
                              └────────────────────┘

Fallback on Failure:
  ├─ LLM timeout → Fallback strategy (opportunistic)
  ├─ Parse error → Retry with clarification
  ├─ 3 consecutive failures → Switch to fallback for N turns
  └─ Return to LLM after fallback duration
```

---

## Multi-Character Knowledge Sharing

```
┌─────────────────────────────────────────────────────────────────┐
│                 Knowledge Sharing Modes                         │
└─────────────────────────────────────────────────────────────────┘

MODE 1: SHARED (Default)
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ QuantumTrader│  │AlgoProfit    │  │DataCapital   │
│ Ship: Swift  │  │Ship: Neural  │  │Ship: Dark    │
│ Venture      │  │Horizon       │  │Fortune       │
└──────┬───────┘  └──────┬───────┘  └──────┬───────┘
       │                 │                 │
       └─────────────────┼─────────────────┘
                         │
                         ↓
                ┌────────────────────┐
                │  Shared Database   │
                │  All sectors,      │
                │  ports, warps      │
                └────────────────────┘
  • Fastest universe mapping
  • All bots benefit from each discovery
  • Best for coordinated fleet


MODE 2: INDEPENDENT
┌──────────────┐      ┌──────────────┐      ┌──────────────┐
│ QuantumTrader│      │AlgoProfit    │      │DataCapital   │
└──────┬───────┘      └──────┬───────┘      └──────┬───────┘
       │                     │                     │
       ↓                     ↓                     ↓
┌──────────────┐      ┌──────────────┐      ┌──────────────┐
│ Private DB #1│      │ Private DB #2│      │ Private DB #3│
└──────────────┘      └──────────────┘      └──────────────┘
  • No knowledge sharing
  • Each bot explores independently
  • Simulates separate players


MODE 3: INHERIT ON DEATH
┌──────────────┐                    ┌──────────────┐
│ QuantumTrader│                    │AlgoProfit    │
│ Credits: 50k │ ─── Dies ─────→   │(successor)   │
│ Knowledge:   │                    │              │
│  500 sectors │                    │ Inherits:    │
└──────────────┘                    │  500 sectors │
                                    │  Trade routes│
                                    └──────────────┘
  • Generational knowledge transfer
  • New bot inherits from predecessor
  • Balance of isolation and continuity
```

---

## Game Loop Turn Cycle

```
┌─────────────────────────────────────────────────────────────────┐
│                     Single Turn Cycle                           │
└─────────────────────────────────────────────────────────────────┘

START TURN
    │
    ↓
┌─────────────────┐
│ 1. ORIENT       │  Read screen, detect current sector
│                 │  Extract: sector_id, warps, port_class
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│ 2. ANALYZE      │  Gather nearby sector info
│                 │  Calculate potential trades
│                 │  Check danger zones
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│ 3. DECIDE       │  Strategy chooses action:
│                 │   ┌──────────────────────┐
│                 │   │ ProfitablePairs:     │
│                 │   │  → Pick best route   │
│                 │   │                      │
│                 │   │ Opportunistic:       │
│                 │   │  → Explore or trade  │
│                 │   │                      │
│                 │   │ AI Strategy:         │
│                 │   │  → Ask LLM           │
│                 │   └──────────────────────┘
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│ 4. EXECUTE      │  Perform action:
│                 │   • WARP → Send "M\r{target}\r"
│                 │   • TRADE → Port buy/sell sequence
│                 │   • SCAN → Display computer "D"
│                 │   • WAIT → Skip turn
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│ 5. VALIDATE     │  Check execution success:
│                 │   • Expected prompt received?
│                 │   • Sector changed?
│                 │   • Credits updated?
│                 │   • Errors/anomalies?
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│ 6. RECORD       │  Update state:
│                 │   • character.turns_used++
│                 │   • character.credits = new_value
│                 │   • character.total_profit += profit
│                 │   • Save to disk
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│ 7. CHECK GOALS  │  Are we done?
│                 │   • Credits >= target?
│                 │   • Turns >= max_turns?
│                 │   • Character died?
└────────┬────────┘
         │
    ┌────┴────┐
    │         │
    ↓         ↓
  DONE     CONTINUE
    │         │
    ↓         └──→ LOOP to step 1
  EXIT
```

---

## Data Persistence

```
┌─────────────────────────────────────────────────────────────────┐
│                    Data Storage Structure                       │
└─────────────────────────────────────────────────────────────────┘

~/.bbsbot/tw2002/
├── character_records.json          # Character lifecycle tracking
│   {
│     "records": {
│       "QuantumTrader": {
│         "name": "QuantumTrader",
│         "ship_name": "Swift Venture",
│         "created_at": 1738814400.0,
│         "died_at": null,
│         "sessions": 3,
│         "total_profit": 150000
│       }
│     },
│     "total_count": 5
│   }
│
├── QuantumTrader_state.json        # Character state
│   {
│     "name": "QuantumTrader",
│     "ship_name": "Swift Venture",
│     "credits": 45000,
│     "turns_used": 87,
│     "total_profit": 12000,
│     "visited_sectors": [1, 5, 12, 17, 23],
│     "scanned_sectors": {
│       "5": 1738814400.0,
│       "12": 1738814405.0
│     },
│     "danger_zones": {
│       "42": 1738814500.0
│     }
│   }
│
├── shared_sectors.json              # Shared knowledge (if enabled)
│   {
│     "5": {
│       "warps": [12, 17, 23],
│       "has_port": true,
│       "port_class": "Class 2",
│       "port_buys": ["Ore"],
│       "port_sells": ["Equipment"],
│       "last_visited": 1738814400.0
│     }
│   }
│
└── semantic/
    └── QuantumTrader_semantic.jsonl # Semantic K/V logs
        {"timestamp": 1738814400, "sector": 5, "credits": 45000, ...}
        {"timestamp": 1738814405, "sector": 12, "credits": 47000, ...}
```

---

## Character Naming System

```
┌─────────────────────────────────────────────────────────────────┐
│                  Themed Name Generation                         │
└─────────────────────────────────────────────────────────────────┘

NameGenerator (seed=optional)
    │
    ├─ Character Names (AI/Economic/Data themed)
    │   │
    │   ├─ SIMPLE (2-part): 1,596 combinations
    │   │   Format: {Prefix}{Suffix}
    │   │   Examples: QuantumTrader, NeuralProfit, AlgoMarket
    │   │
    │   ├─ MEDIUM (3-part): 77,000 combinations [DEFAULT]
    │   │   Format: {Prefix}{Middle}{Suffix}
    │   │   Examples: NeuralDataProfit, CryptoByteMarket
    │   │
    │   ├─ COMPLEX (4-part): 3.7M combinations
    │   │   Format: {Prefix}{Middle1}{Middle2}{Suffix}
    │   │   Examples: QuantumNeuralDataTrader
    │   │
    │   └─ NUMBERED: Unlimited
    │       Format: {Base}{Number}
    │       Examples: QuantumTrader47, AlgoProfit128
    │
    └─ Ship Names (Space/Adventure themed)
        │
        ├─ Basic: 8,064 combinations
        │   Format: {Descriptor} {Concept}
        │   Examples: Swift Venture, Neural Horizon
        │
        └─ With Numbers: 161,280 combinations
            Format: {Descriptor} {Concept} {Numeral}
            Examples: Swift Venture II, Dark Fortune VII

Word Lists:
  Prefixes (42): Quantum, Neural, Algo, Cyber, Crypto, Digital...
  Middles (48): Data, Compute, Net, Metric, Process, Signal...
  Suffixes (38): Trader, Profit, Broker, Agent, Alpha, Market...

  Ship Descriptors (96): Swift, Silent, Mighty, Nova, Iron...
  Ship Concepts (84): Venture, Horizon, Phoenix, Dragon, Storm...

Collision Avoidance:
  ├─ Track all used names
  ├─ Load existing from character_records.json
  ├─ Max 100 attempts to find unique name
  └─ Fallback to numbered suffix if exhausted
```

---

**Navigation**:
- [Complete System Architecture](.provide/SYSTEM_ARCHITECTURE.md)
- [Themed Names Implementation](.provide/HANDOFF_themed_names.md)
- [Main README](../README.md)
