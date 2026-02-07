# Intelligent Bot Architecture Overview

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Intelligent TW2002 Bot                       │
│                  (play_tw2002_intelligent.py)                   │
└───────────────────────┬─────────────────────────────────────────┘
                        │
                        │ uses
                        ↓
┌─────────────────────────────────────────────────────────────────┐
│                     SessionManager                              │
│                  (mcp_bbs.core.session_manager)                 │
└───────────────────────┬─────────────────────────────────────────┘
                        │
                        │ creates/manages
                        ↓
┌─────────────────────────────────────────────────────────────────┐
│                       Session                                   │
│                   (mcp_bbs.core.session)                        │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │             LearningEngine                                │  │
│  │         (mcp_bbs.learning.engine)                         │  │
│  │  ┌──────────────────────────────────────────────────┐    │  │
│  │  │        PromptDetector                            │    │  │
│  │  │    (mcp_bbs.learning.detector)                   │    │  │
│  │  │  - Loads patterns from prompts.json              │    │  │
│  │  │  - Detects prompts on each read                  │    │  │
│  │  │  - Returns prompt_id + input_type                │    │  │
│  │  └──────────────────────────────────────────────────┘    │  │
│  │                                                            │  │
│  │  ┌──────────────────────────────────────────────────┐    │  │
│  │  │        ScreenSaver                               │    │  │
│  │  │    (mcp_bbs.learning.screen_saver)               │    │  │
│  │  │  - Saves unique screens (hash-based)             │    │  │
│  │  │  - Deduplicates automatically                    │    │  │
│  │  │  - Stores in .bbs-knowledge/games/tw2002/screens/│   │  │
│  │  └──────────────────────────────────────────────────┘    │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │            TerminalEmulator (pyte)                       │  │
│  │  - Processes ANSI escape codes                           │  │
│  │  - Maintains 80x25 screen buffer                         │  │
│  │  - Tracks cursor position                                │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │            Transport (Telnet/SSH)                        │  │
│  │  - Handles connection to BBS                             │  │
│  │  - Sends/receives raw bytes                              │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## Bot Operation Flow

```
┌─────────────┐
│   Connect   │
└──────┬──────┘
       │
       ↓
┌─────────────────────────────────────┐
│  Enable Learning                    │
│  - Load prompt patterns             │
│  - Initialize screen saver          │
└──────┬──────────────────────────────┘
       │
       ↓
┌─────────────────────────────────────┐
│  Navigate TWGS to Game              │
│  1. Wait for TWGS menu              │
│  2. Send "A" (My Game)              │
│  3. Wait for player name prompt     │
│  4. Send player name                │
│  5. Handle new player creation      │
└──────┬──────────────────────────────┘
       │
       ↓
┌─────────────────────────────────────┐
│  Test Commands (Pattern Validation) │
│  For each command:                  │
│    - Send command                   │
│    - Wait for prompt detection      │
│    - Handle pagination if needed    │
│    - Track pattern match            │
│    - Record sequence                │
└──────┬──────────────────────────────┘
       │
       ↓
┌─────────────────────────────────────┐
│  Test Navigation                    │
│  - Move between sectors             │
│  - Test sector prompts              │
└──────┬──────────────────────────────┘
       │
       ↓
┌─────────────────────────────────────┐
│  Test Quit Sequence                 │
│  - Send quit command                │
│  - Wait for confirmation            │
│  - Confirm quit                     │
└──────┬──────────────────────────────┘
       │
       ↓
┌─────────────────────────────────────┐
│  Generate Report                    │
│  - Pattern matches                  │
│  - Test results                     │
│  - Prompt sequences                 │
│  - Screen statistics                │
└──────┬──────────────────────────────┘
       │
       ↓
┌─────────────────────────────────────┐
│  Save Results                       │
│  - JSON: Full data                  │
│  - Markdown: Human-readable report  │
└─────────────────────────────────────┘
```

## Prompt Detection Flow

```
┌─────────────────────────────────────┐
│  Bot: read_screen()                 │
└──────┬──────────────────────────────┘
       │
       ↓
┌─────────────────────────────────────┐
│  Session: read(timeout_ms)          │
└──────┬──────────────────────────────┘
       │
       ↓
┌─────────────────────────────────────┐
│  Transport: receive bytes           │
└──────┬──────────────────────────────┘
       │
       ↓
┌─────────────────────────────────────┐
│  TerminalEmulator: process ANSI     │
│  - Update screen buffer             │
│  - Track cursor                     │
└──────┬──────────────────────────────┘
       │
       ↓
┌─────────────────────────────────────┐
│  LearningEngine: detect_prompt()    │
│  - Extract screen text              │
│  - Run through pattern regexes      │
│  - Return match if found            │
└──────┬──────────────────────────────┘
       │
       ↓
┌─────────────────────────────────────┐
│  Return snapshot to bot:            │
│  {                                  │
│    'screen': str,                   │
│    'screen_hash': str,              │
│    'cursor': {x, y},                │
│    'prompt_detected': {             │
│      'prompt_id': str,              │
│      'input_type': str,             │
│      'matched_text': str            │
│    }                                │
│  }                                  │
└──────┬──────────────────────────────┘
       │
       ↓
┌─────────────────────────────────────┐
│  Bot: Process detection             │
│  - Track pattern match              │
│  - Decide response based on type    │
│  - Send appropriate input           │
└─────────────────────────────────────┘
```

## Smart Waiting Algorithm

```
┌─────────────────────────────────────┐
│  wait_for_prompt(expected_id)       │
└──────┬──────────────────────────────┘
       │
       ↓
┌─────────────────────────────────────┐
│  While time < max_wait:             │
└──────┬──────────────────────────────┘
       │
       ↓
┌─────────────────────────────────────┐
│  Read screen                        │
└──────┬──────────────────────────────┘
       │
       ↓
    ┌──┴───────────────────────┐
    │                          │
    ↓                          ↓
┌─────────────┐        ┌──────────────┐
│  Prompt     │        │  No prompt   │
│  detected?  │        │  detected    │
└──────┬──────┘        └──────┬───────┘
       │                      │
       │                      ↓
       │              ┌───────────────┐
       │              │  Screen same  │
       │              │  as last?     │
       │              └──────┬────────┘
       │                     │
       │              ┌──────┴───────┐
       │              │              │
       │              ↓              ↓
       │        ┌──────────┐   ┌─────────┐
       │        │   Yes    │   │   No    │
       │        │  stable++│   │ stable=0│
       │        └──────┬───┘   └────┬────┘
       │               │            │
       │               ↓            │
       │        ┌─────────────┐    │
       │        │ stable >= 3?│    │
       │        └──────┬──────┘    │
       │               │            │
       │        ┌──────┴───┐        │
       │        │          │        │
       │        ↓          ↓        │
       │    ┌──────┐  ┌────────┐   │
       │    │ Yes  │  │   No   │   │
       │    │Return│  │Continue│←──┘
       │    └──────┘  └────────┘
       │
       ↓
┌─────────────────────┐
│  Expected prompt?   │
└──────┬──────────────┘
       │
  ┌────┴─────┐
  │          │
  ↓          ↓
┌─────┐  ┌──────┐
│ Yes │  │  No  │
│Match│  │Check │
└──┬──┘  └──┬───┘
   │        │
   │   ┌────┴────┐
   │   │         │
   │   ↓         ↓
   │ ┌────┐  ┌────────┐
   │ │Same│  │Different│
   │ │ID? │  │Continue │
   │ └──┬─┘  └─────────┘
   │    │
   │    ↓
   │ ┌──────┐
   └→│Return│
     └──────┘
```

## Auto-Pagination Flow

```
┌─────────────────────────────────────┐
│  handle_pagination(snapshot)        │
└──────┬──────────────────────────────┘
       │
       ↓
┌─────────────────────────────────────┐
│  While pages < max_pages:           │
└──────┬──────────────────────────────┘
       │
       ↓
┌─────────────────────────────────────┐
│  Check snapshot for detection       │
└──────┬──────────────────────────────┘
       │
    ┌──┴─────────────────┐
    │                    │
    ↓                    ↓
┌─────────────┐    ┌──────────────┐
│  Prompt     │    │  No prompt   │
│  detected   │    │  Return      │
└──────┬──────┘    └──────────────┘
       │
       ↓
┌─────────────────────────────────────┐
│  Check input_type and prompt_id     │
└──────┬──────────────────────────────┘
       │
    ┌──┴────────────────────────────┐
    │                               │
    ↓                               ↓
┌─────────────────────┐    ┌───────────────┐
│  Pagination prompt? │    │  Real prompt  │
│  - any_key          │    │  Return       │
│  - "more" in id     │    └───────────────┘
│  - "press_any_key"  │
└──────┬──────────────┘
       │
       ↓
┌─────────────────────────────────────┐
│  Send " " to continue               │
└──────┬──────────────────────────────┘
       │
       ↓
┌─────────────────────────────────────┐
│  Read next screen                   │
│  pages++                            │
└──────┬──────────────────────────────┘
       │
       │ (loop back to while)
       ↓
```

## Data Flow

```
User Input
    │
    ↓
┌────────────────────────┐
│  Bot Command           │
│  - Command string      │
│  - Description         │
│  - Expected pattern    │
└────────┬───────────────┘
         │
         ↓
┌────────────────────────┐
│  Session.send()        │
│  - Send to transport   │
└────────┬───────────────┘
         │
         ↓
┌────────────────────────┐
│  BBS Server            │
│  - Process command     │
│  - Generate response   │
└────────┬───────────────┘
         │
         ↓
┌────────────────────────┐
│  Transport.receive()   │
│  - Read bytes          │
└────────┬───────────────┘
         │
         ↓
┌────────────────────────┐
│  Terminal Emulator     │
│  - Parse ANSI          │
│  - Update screen       │
└────────┬───────────────┘
         │
         ↓
┌────────────────────────┐
│  PromptDetector        │
│  - Match patterns      │
│  - Return detection    │
└────────┬───────────────┘
         │
         ↓
┌────────────────────────┐
│  ScreenSaver           │
│  - Hash screen         │
│  - Save if unique      │
└────────┬───────────────┘
         │
         ↓
┌────────────────────────┐
│  Bot Tracking          │
│  - Pattern matches     │
│  - Prompt sequences    │
│  - Test results        │
└────────┬───────────────┘
         │
         ↓
┌────────────────────────┐
│  Report Generation     │
│  - JSON results        │
│  - Markdown report     │
└────────────────────────┘
```

## Pattern Matching

```
Screen Text:
"Command [?=help]: _"

      ↓

Pattern Definitions (prompts.json):
[
  {
    "id": "main_menu",
    "regex": "(?i)command\\s*[\\[\\(:]?\\s*\\??\\s*$",
    "input_type": "single_key",
    ...
  },
  {
    "id": "command_prompt_generic",
    "regex": "(?i)command\\s*[:\\?]",
    "input_type": "single_key",
    ...
  },
  ...
]

      ↓

Detection Process:
1. Extract screen text
2. For each pattern in order:
   - Test regex against text
   - Check cursor position if needed
   - If match → return detection
3. If no match → return None

      ↓

Result:
{
  "prompt_id": "main_menu",
  "input_type": "single_key",
  "matched_text": "Command [?=help]:"
}

      ↓

Bot Response:
if input_type == 'single_key':
    send("D")  # Single character, no Enter
```

## File Organization

```
mcp-bbs/
├── play_tw2002_intelligent.py       # Main bot
├── test_all_patterns.py             # Pattern validator
│
├── src/mcp_bbs/
│   ├── core/
│   │   ├── session_manager.py       # Session management
│   │   └── session.py               # Session with learning
│   │
│   ├── learning/
│   │   ├── engine.py                # Learning engine
│   │   ├── detector.py              # Prompt detection
│   │   ├── screen_saver.py          # Screen saving
│   │   └── buffer.py                # Screen buffering
│   │
│   ├── terminal/
│   │   └── emulator.py              # Terminal emulation (pyte)
│   │
│   └── transport/
│       ├── telnet.py                # Telnet transport
│       └── ssh.py                   # SSH transport
│
├── .bbs-knowledge/
│   └── games/tw2002/
│       ├── prompts.json             # Pattern definitions
│       └── screens/                 # Saved unique screens
│           ├── abc123.txt
│           ├── def456.txt
│           └── ...
│
└── .provide/
    ├── intelligent-bot-*.json       # Test results (JSON)
    ├── intelligent-bot-*.md         # Test results (MD)
    ├── pattern-validation-*.json    # Validation results
    ├── pattern-validation-*.md      # Coverage report
    ├── INTELLIGENT-BOT-README.md    # Complete guide
    ├── BOT-QUICK-REFERENCE.md       # Quick ref
    ├── HANDOFF-intelligent-bot.md   # Handoff doc
    ├── IMPLEMENTATION-CHECKLIST.md  # Checklist
    └── ARCHITECTURE-OVERVIEW.md     # This file
```

## Key Classes

### IntelligentTW2002Bot
```python
class IntelligentTW2002Bot:
    async def connect()
    async def wait_for_prompt(expected_id=None)
    async def send_and_wait(keys, expected_prompt)
    async def handle_pagination(snapshot)
    async def test_command(cmd, desc, expected)
    async def navigate_twgs_to_game()
    async def enter_game_as_player(name)
    async def run_pattern_tests()
    async def test_navigation()
    async def test_quit_sequence()
    async def generate_report()
    async def save_results()
```

### PatternValidator
```python
class PatternValidator:
    async def connect()
    async def test_pattern(test: PatternTest)
    async def run_all_tests()
    def generate_report()
    async def save_results()
```

## Integration Points

### With SessionManager
```python
manager = SessionManager()
session_id = await manager.create_session(host, port, ...)
session = await manager.get_session(session_id)
await manager.enable_learning(session_id, knowledge_root, namespace)
```

### With Learning System
```python
# Automatic on each read
snapshot = await session.read()

# Contains detection if pattern matched
if 'prompt_detected' in snapshot:
    detected = snapshot['prompt_detected']
    # Use detection data
```

### With Screen Saver
```python
# Automatic on each read
# Saves unique screens to:
# .bbs-knowledge/games/{namespace}/screens/{hash}.txt

# Get statistics
status = session.learning.get_screen_saver_status()
# Returns: saved_count, screens_dir, etc.
```

## Success Path

```
Start
  ↓
Connect to BBS
  ↓
Enable learning (load patterns)
  ↓
Navigate TWGS → Game
  ↓
Test commands (10+ patterns)
  ↓
Test navigation
  ↓
Test quit
  ↓
Generate report
  ↓
Save results
  ↓
Success!

Expected outcome:
- 11-12 of 13 patterns matched
- 20-30 unique screens saved
- Complete prompt sequences
- No false positives
- Full automation
```

## Summary

The intelligent bot architecture implements a clean separation of concerns:

1. **Bot Layer**: High-level game navigation and testing
2. **Session Layer**: Screen reading and writing
3. **Learning Layer**: Prompt detection and screen saving
4. **Terminal Layer**: ANSI processing and display
5. **Transport Layer**: Network communication

All layers work together to provide:
- Reactive prompt detection
- Automatic pagination handling
- Pattern validation
- Flow tracking
- Comprehensive reporting

The system is **ready for testing** against a live TW2002 BBS server.
