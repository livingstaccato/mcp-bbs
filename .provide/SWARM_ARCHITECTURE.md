# BBSBot Swarm Management Architecture

## System Overview

```
╔════════════════════════════════════════════════════════════════════════════╗
║                          BBSBOT SWARM SYSTEM                              ║
╠════════════════════════════════════════════════════════════════════════════╣
║                                                                            ║
║                    ┌──────────────────────────────┐                       ║
║                    │   SWARM MANAGER SERVER       │                       ║
║                    │  (Single Instance)           │                       ║
║                    │  localhost:8000              │                       ║
║                    │  - Spawn/Monitor Bots        │                       ║
║                    │  - REST API                  │                       ║
║                    │  - WebSocket Updates         │                       ║
║                    │  - State Persistence         │                       ║
║                    └────────┬─────────────────────┘                       ║
║                             │                                             ║
║              ┌──────────────┼──────────────┐                             ║
║              │              │              │                             ║
║              ▼              ▼              ▼                             ║
║        ┌──────────┐  ┌──────────┐  ┌──────────┐                         ║
║        │   CLI    │  │   MCP    │  │WebSocket │                         ║
║        │ Client   │  │  Tools   │  │ Monitor  │                         ║
║        │(Terminal)│  │ (Claude) │  │(Browser) │                         ║
║        └──────────┘  └──────────┘  └──────────┘                         ║
║              │              │              │                             ║
║              └──────────────┼──────────────┘                             ║
║                             │                                             ║
║                      HTTP/JSON/REST                                      ║
║                             │                                             ║
║              ┌──────────────▼──────────────┐                             ║
║              │   Bot Worker Pool           │                             ║
║              │  (Multi-Process)            │                             ║
║              │                             │                             ║
║    ┌─────────┼─────────┬─────────┬──────┐ │                             ║
║    │         │         │         │      │ │                             ║
║    ▼         ▼         ▼         ▼      ▼ │                             ║
║  ┌────┐  ┌────┐  ┌────┐  ┌────┐      ┌────┐                            ║
║  │Bot1│  │Bot2│  │Bot3│  │Bot4│ ...  │Botn│                            ║
║  │PID │  │PID │  │PID │  │PID │      │PID │                            ║
║  │5001│  │5002│  │5003│  │5004│      │5NNN│                            ║
║  └────┘  └────┘  └────┘  └────┘      └────┘                            ║
║    │         │         │         │      │                              ║
║    └─────────┼─────────┼─────────┼──────┘                              ║
║              │         │         │                                      ║
║              └─────────┼─────────┘                                      ║
║                        │                                                ║
║                   Telnet (2002)                                         ║
║                        │                                                ║
║              ┌─────────▼──────────┐                                     ║
║              │ Game Server        │                                     ║
║              │ localhost:2002     │                                     ║
║              │ TW2002 TWGS        │                                     ║
║              │ (Games A, B, C)    │                                     ║
║              └────────────────────┘                                     ║
║                                                                            ║
╚════════════════════════════════════════════════════════════════════════════╝
```

## Component Architecture

### 1. Swarm Manager (Central Coordinator)

```
SWARM MANAGER (port 8000)
├── State Management
│   ├── Bots Registry: Dict[bot_id] → BotStatus
│   ├── Process Map: Dict[bot_id] → subprocess.Popen
│   ├── Metrics: Aggregated stats
│   └── Persistence: swarm_state.json
│
├── Bot Control
│   ├── spawn_bot(config, bot_id) → bot_id
│   ├── spawn_swarm(configs[]) → [bot_ids]
│   ├── pause_bot(bot_id)
│   ├── resume_bot(bot_id)
│   ├── kill_bot(bot_id)
│   └── set_bot_goal(bot_id, goal)
│
├── Monitoring
│   ├── get_swarm_status() → SwarmStatus
│   ├── get_bot_status(bot_id) → BotStatus
│   ├── monitor_processes() [background]
│   └── WebSocket broadcasts
│
└── HTTP API (FastAPI)
    ├── POST   /swarm/spawn
    ├── POST   /swarm/spawn-batch
    ├── GET    /swarm/status
    ├── GET    /bot/{bot_id}/status
    ├── POST   /bot/{bot_id}/pause
    ├── POST   /bot/{bot_id}/resume
    ├── DELETE /bot/{bot_id}
    ├── POST   /bot/{bot_id}/set-goal
    └── WS     /ws/swarm
```

### 2. Bot Worker Process

```
BOT WORKER PROCESS
├── Configuration
│   ├── Load YAML config
│   ├── Parse credentials
│   └── Initialize strategy
│
├── Lifecycle
│   ├── Register with manager (via HTTP)
│   ├── Execute trading loop
│   └── Report status periodically
│
├── State Tracking
│   ├── Current sector
│   ├── Credits
│   ├── Turns executed
│   ├── Last activity timestamp
│   └── Error state
│
└── IPC with Manager
    ├── Send status updates
    ├── Receive commands (pause/resume/goal)
    └── Log events
```

### 3. Management Interfaces

```
┌─ CLI INTERFACE ─────────────────────┐
│ $ python -m bbsbot.cli              │
│  - spawn <config>                   │
│  - spawn-swarm --count 111           │
│  - status                            │
│  - kill <bot_id>                     │
│  - pause <bot_id>                    │
│  - resume <bot_id>                   │
│  - set-goal <bot_id> <goal>          │
└─────────────────────────────────────┘

┌─ MCP TOOLS (Claude) ────────────────┐
│ tw2002_spawn_bot(config)             │
│ tw2002_spawn_swarm(configs, count)   │
│ tw2002_get_swarm_status()            │
│ tw2002_get_bot_status(bot_id)        │
│ tw2002_kill_bot(bot_id)              │
│ tw2002_pause_bot(bot_id)             │
│ tw2002_resume_bot(bot_id)            │
│ tw2002_set_bot_goal(bot_id, goal)    │
└─────────────────────────────────────┘

┌─ WEB DASHBOARD ─────────────────────┐
│ http://localhost:3000                │
│ - Real-time bot status               │
│ - Performance graphs                 │
│ - Individual bot details              │
│ - Control buttons                     │
└─────────────────────────────────────┘
```

## Data Flow Diagrams

### Spawning a Swarm

```
CLI/MCP Request
       │
       ▼
   Manager API
   POST /swarm/spawn-batch
       │
       ├─► Validate configs
       ├─► Check capacity (< max_bots)
       │
       ▼
   For each config:
       │
       ├─► Subprocess.Popen(bot worker)
       ├─► Store {bot_id: PID, config, status}
       │
       ▼
   Bot Worker Process
       │
       ├─► Load config
       ├─► Create TradingBot
       ├─► Register with manager
       │
       ▼
   Manager Updates
       │
       ├─► WebSocket broadcast
       └─► API clients updated
```

### Bot Execution Loop

```
Bot Worker
       │
       ├─► Connect to server (localhost:2002)
       │
       ├─► Login sequence
       │   ├─► Character creation
       │   └─► Game entry
       │
       ▼
   Trading Loop (per turn)
       │
       ├─► Get current state (orient)
       │
       ├─► Strategy decision
       │   ├─► Opportunistic: explore/trade
       │   └─► AI: LLM analysis
       │
       ├─► Execute action
       │
       ├─► Update credits
       │
       └─► Report to manager
           └─► Manager broadcasts status
```

### Monitoring & Control

```
WebSocket Stream (Real-time)
       │
       ├─► Manager broadcasts every 5s
       │   └─► {bot_id, sector, credits, turns, state}
       │
       ├─► Clients receive updates
       │   ├─► CLI: Pretty-print
       │   ├─► Web: Update graphs
       │   └─► MCP: Available for Claude
       │
       └─► Manual control
           ├─► Pause bot
           ├─► Resume bot
           ├─► Change goal
           └─► Kill bot
```

## Process Lifecycle

```
┌─────────────────────────────────────────────────────┐
│           BOT PROCESS LIFECYCLE                      │
├─────────────────────────────────────────────────────┤
│                                                      │
│  Created                                            │
│    │                                                 │
│    ▼                                                 │
│  [SPAWNING] ◄─── subprocess.Popen()                │
│    │                                                 │
│    ▼                                                 │
│  [REGISTERING] ◄─── Register with manager          │
│    │                                                 │
│    ▼                                                 │
│  [RUNNING] ◄─── Trading loop active                │
│    │                                                 │
│    ├─► Periodically report status                  │
│    ├─► Listen for commands                         │
│    └─► Execute trades                              │
│    │                                                 │
│    ▼                                                 │
│  [PAUSED] ◄─► [RUNNING] (manual control)           │
│    │                                                 │
│    ▼                                                 │
│  [COMPLETED] ◄─── max_turns reached                │
│    │                                                 │
│    ▼                                                 │
│  [DEAD] ◄─── Process terminated                    │
│                                                      │
└─────────────────────────────────────────────────────┘
```

## Error Handling & Resilience

```
Manager
   │
   ├─► Monitor subprocess exit
   │   └─► If crash: update state to "error"
   │       Report to API clients
   │
   ├─► Health check (periodic)
   │   ├─► Check if PID still exists
   │   ├─► Timeout detection (no status update > 60s)
   │   └─► Mark as stuck/error
   │
   └─► Recovery options
       ├─► Auto-restart on crash (optional)
       ├─► Manual restart via API
       └─► Kill & respawn with new config
```

## Resource Usage

```
Typical Configuration (111 bots, 65,000 turns each):

Manager Process:
  - Memory: ~200-500 MB
  - CPU: 1-2% (mostly I/O bound)
  - Network: ~10 Mbps (bot status updates)

Per Bot Process:
  - Memory: ~50-100 MB
  - CPU: <1% (async I/O)
  - Network: ~10 Kbps (telnet traffic)

Total for 111 bots:
  - Memory: 5-12 GB
  - CPU: ~30-40% total
  - Network: ~1-2 Mbps
```

## Configuration

```yaml
# manager_config.yaml
manager:
  port: 8000
  host: localhost
  max_bots: 200

  # Persistence
  state_file: swarm_state.json
  auto_save_interval: 60  # seconds

  # Monitoring
  health_check_interval: 10
  status_broadcast_interval: 5
  bot_timeout: 60  # seconds

  # Resource limits
  max_memory_per_bot: 200  # MB
  max_cpu_per_bot: 50  # percent
```

## Deployment

```bash
# 1. Start manager (production)
python -m bbsbot.manager --config manager_config.yaml

# 2. Spawn bots via CLI
python -m bbsbot.cli spawn-swarm --count 111

# 3. Monitor via API
curl http://localhost:8000/swarm/status

# 4. Or use MCP in Claude
"Spawn 50 opportunistic bots"
"Show me swarm status"
"Pause bot_042"
```

## Integration Points

### 1. With TradingBot
- Bot reports status periodically
- Receives control commands
- Runs independently after spawn

### 2. With MCP
- HTTP calls to manager
- Real-time status via WebSocket
- Can spawn/control entire swarm

### 3. With CLI
- Simple command interface
- Same HTTP API as MCP
- Human-readable output

### 4. With Game Server
- All bots connect to localhost:2002
- Manager doesn't intercept traffic
- Bots operate independently
