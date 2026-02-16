# Trade Wars 2002 - Multi-Bot Coordinated Gameplay

## Overview

The multi-bot system allows you to run 5 (or more) coordinated bots simultaneously in Trade Wars 2002. Each bot has a specific role and they share knowledge through a common state file.

## Quick Start

### Run with 5 bots (default):
```bash
./run_multibot.sh
```

### Run with custom number of bots:
```bash
./run_multibot.sh 3    # Run 3 bots
```

### Direct Python execution:
```bash
python3 -m bbsbot.commands.scripts.play_tw2002_multibot 5
```

## Bot Roles

The system creates bots with these specialized roles:

1. **Trader #1** - Primary trading bot using configured strategy
2. **Scout** - Explores and maps sectors
3. **Trader #2** - Secondary trading bot
4. **Banker** - Manages banking operations
5. **Defender** - Monitors threats and danger zones

## Coordination Features

### Shared State
All bots share knowledge via `~/.bbsbot_multibot/shared_state.json`:

- **Profitable Routes**: Discovered trading routes
- **Danger Sectors**: Known hostile areas
- **Port Locations**: Mapped port positions
- **Unexplored Sectors**: Areas not yet visited
- **Bot Status**: Real-time status of all bots

### Real-Time Updates
- Bots coordinate every 30 seconds
- Shared state is persisted to disk
- Status reports every 30 seconds showing:
  - Active bots and their roles
  - Current sectors
  - Credits and profit
  - Actions performed

## Architecture

### File Structure
```
bbsbot/
├── src/bbsbot/commands/scripts/
│   └── play_tw2002_multibot.py    # Main multi-bot script
├── run_multibot.sh                  # Quick launcher
└── ~/.bbsbot_multibot/             # Runtime data directory
    ├── shared_state.json           # Shared coordination state
    └── character_*.json            # Individual character states
```

### Key Components

**MultiBotCoordinator**
- Spawns and manages all bots
- Handles graceful shutdown on Ctrl+C
- Monitors and reports status

**CoordinatedBot**
- Individual bot instance
- Executes role-specific behavior
- Updates shared state

**SharedState**
- Coordination data structure
- Persisted to JSON file
- Enables bot-to-bot knowledge sharing

## Bot Behaviors

### Trader Bot
```python
async def trader_behavior(self):
    # Execute trading strategy
    # Update shared state with profit info
    # Share discovered routes
```

### Scout Bot
```python
async def scout_behavior(self):
    # Scan sectors using D command
    # Explore random sectors
    # Share map data via shared state
```

### Banker Bot
```python
async def banker_behavior(self):
    # Monitor credit thresholds
    # Execute deposits/withdrawals
    # Less active (checks every 10s)
```

### Upgrader Bot
```python
async def upgrader_behavior(self):
    # Monitor ship upgrade needs
    # Purchase holds, fighters, shields
    # Checks every 15s
```

### Defender Bot
```python
async def defender_behavior(self):
    # Monitor danger zones
    # Patrol hostile areas
    # Provide early warning
```

## Configuration

Bots use the standard `bbsbot` config system:

```yaml
# config/tw2002.yml
connection:
  host: localhost
  port: 2002
  game_password: game

trading:
  strategy: opportunistic  # Used by trader bots

banking:
  enabled: true
  deposit_threshold: 50000
```

### Environment Variables
```bash
export BBSBOT_TW_HOST=localhost
export BBSBOT_TW_PORT=2002
export BBSBOT_TW_PASSWORD=yourpassword
export BBSBOT_TW_GAME=B
```

## Monitoring

### Status Reports
Every 30 seconds, see output like:
```
================================================================================
MULTI-BOT STATUS REPORT
================================================================================
  trader_01       | Role: trader     | Actions:   42 | Sector:   15 | Credits:    15000 | Last seen: 2s ago
  scout_02        | Role: scout      | Actions:   38 | Sector:  127 | Credits:     3000 | Last seen: 1s ago
  trader_03       | Role: trader     | Actions:   40 | Sector:   89 | Credits:    12000 | Last seen: 3s ago
  banker_04       | Role: banker     | Actions:   12 | Sector:    1 | Credits:   100000 | Last seen: 5s ago
  defender_05     | Role: defender   | Actions:   25 | Sector:   45 | Credits:     8000 | Last seen: 2s ago

  Total Trades: 85
  Total Credits: 138000
  Sectors Mapped: 127
================================================================================
```

### Log Output
```bash
19:45:23 [INFO] [trader_01] Executing trade cycle
19:45:24 [INFO] [scout_02] Exploring sectors
19:45:25 [DEBUG] [trader_01] Coordination update - Actions: 43
```

## Graceful Shutdown

Press **Ctrl+C** to stop all bots gracefully:
```
🛑 Shutdown signal received, stopping all bots...
[trader_01] Shutting down gracefully
[scout_02] Shutting down gracefully
...
✓ All bots shut down successfully
```

## Scaling

### More Bots
To run more than 5 bots, modify the roles list in `MultiBotCoordinator.spawn_bots()`:

```python
roles = [
    BotRole.TRADER,
    BotRole.SCOUT,
    BotRole.TRADER,
    BotRole.BANKER,
    BotRole.DEFENDER,
    BotRole.TRADER,      # Add more roles
    BotRole.SCOUT,
    # ... etc
]
```

### Server Capacity
- Each bot requires a separate telnet connection to port 2002
- TWGS server must support concurrent connections
- Test with smaller numbers first (2-3 bots)

## Troubleshooting

### Connection Issues
```
Error: Connection refused to localhost:2002
```
**Solution**: Verify TWGS server is running:
```bash
lsof -nP -iTCP:2002 -sTCP:LISTEN
```

### Import Errors
```
ModuleNotFoundError: No module named 'bbsbot.tw2002.login'
```
**Solution**: Ensure you're in the bbsbot directory and venv is activated:
```bash
cd /path/to/bbsbot
source .venv/bin/activate
```

### Character Limit
If the game has a character limit per account, each bot creates its own character:
- trader_01
- scout_02
- trader_03
- etc.

You may need to delete old characters or configure the game for more slots.

### Performance
If bots are slow or unresponsive:
1. Reduce coordination frequency (increase 30s interval)
2. Reduce number of bots
3. Add delays between bot spawns
4. Check server CPU/memory usage

## Future Enhancements

Potential improvements:

1. **Advanced Coordination**
   - Team trading (one buys, another sells)
   - Convoy protection (defender escorts traders)
   - Resource pooling (shared credits)

2. **Smart Strategies**
   - Route optimization across bots
   - Collaborative sector mapping
   - Threat response coordination

3. **Monitoring**
   - Web dashboard
   - Real-time statistics
   - Alert notifications

4. **Resilience**
   - Auto-restart on crashes
   - Death recovery
   - Connection retry logic

## Development

### Adding New Roles

1. Add to `BotRole` enum:
```python
class BotRole(Enum):
    MERCHANT = "merchant"  # New role
```

2. Implement behavior:
```python
async def merchant_behavior(self):
    # Custom logic here
    pass
```

3. Add to behavior loop:
```python
async def run_behavior_loop(self):
    if self.role == BotRole.MERCHANT:
        await self.merchant_behavior()
```

### Testing Individual Bots

Run a single bot manually:
```python
from bbsbot.commands.scripts.play_tw2002_multibot import CoordinatedBot, BotRole, SharedState

bot = CoordinatedBot(
    bot_id=1,
    role=BotRole.TRADER,
    shared_state=SharedState(),
    config=load_config(),
    data_dir=Path.home() / ".bbsbot_multibot"
)
await bot.connect()
await bot.login_and_setup()
```

## Technical Details

### Async Architecture
- Uses `asyncio` for concurrent execution
- Each bot runs in its own task
- Non-blocking coordination updates

### Session Management
- Each bot has unique `SessionManager` instance
- Separate telnet connections per bot
- Learning engine per session

### State Persistence
- Shared state saved on every coordination update
- Character states saved via `CharacterManager`
- Survives restarts (bots can resume)

### Signal Handling
- SIGINT (Ctrl+C) triggers graceful shutdown
- SIGTERM also handled
- Tasks cancelled cleanly

## Credits

Built on top of:
- `bbsbot` framework
- `SessionManager` for telnet handling
- `TradingBot` core logic
- TW2002 game engine

## License

Same as bbsbot project
