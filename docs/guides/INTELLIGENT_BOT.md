# Intelligent TW2002 Bot Guide

## Overview

This implementation creates an intelligent automated player for Trade Wars 2002 that uses the prompt detection system to navigate the game, test all 13 prompt patterns, and document the complete game flow.

## Architecture: Hybrid Reactive Approach

### Strategy

**Phase 1: Pure Reactive** (IMPLEMENTED)
- Wait for screens to appear
- Detect prompts using pattern matching
- Respond based on detected `input_type`
- Handle pagination automatically

**Phase 2: Flow Tracking** (IMPLEMENTED)
- Record prompt sequences: (action, detected_prompt)
- Build state transition log
- Track pattern match statistics

**Phase 3: Prediction** (Future Enhancement)
- Add state machine for game location
- Predict next prompt based on last command
- Validate detection matches expectation
- Log anomalies

### Key Components

#### IntelligentBot Class (`src/bbsbot/commands/scripts/play_tw2002_intelligent.py`)

Core methods:
- `wait_for_prompt(expected_prompt_id)` - Wait until prompt detected
- `send_and_wait(keys, expected_prompt)` - Send input and wait for response
- `handle_pagination(snapshot)` - Auto-continue through "more" prompts
- `test_command(cmd, desc, expected)` - Test command and validate pattern

Benefits:
- **Self-documenting**: Detection drives action
- **Handles unknowns**: Waits gracefully when no prompt detected
- **Pattern validation**: Tracks which patterns match
- **Incremental**: Easy to add new patterns

## Files

### Active Modules

1. **`src/bbsbot/commands/scripts/play_tw2002_intelligent.py`** - Main intelligent bot runner
   - Implements hybrid reactive approach
   - Tests all patterns through gameplay
   - Tracks pattern matches and sequences
   - Generates comprehensive reports

2. **`src/bbsbot/commands/scripts/test_all_patterns.py`** - Systematic pattern validator
   - Tests each of 13 patterns individually
   - Uses specific trigger sequences
   - Validates pattern accuracy
   - Generates coverage report

3. **`docs/guides/INTELLIGENT_BOT.md`** - This file
   - Architecture documentation
   - Usage instructions
   - Pattern testing guide

### Reference Files

- `.bbs-knowledge/games/tw2002/prompts.json` - 13 pattern definitions
- `src/bbsbot/learning/detector.py` - PromptDetector implementation
- `src/bbsbot/app.py` - MCP tools

## 13 Prompt Patterns to Test

| Pattern ID | Input Type | Notes |
|------------|------------|-------|
| `login_username` | multi_key | Username/handle at login |
| `login_password` | multi_key | Password entry |
| `press_any_key` | any_key | Pause screens |
| `main_menu` | single_key | Main command prompt |
| `yes_no_prompt` | single_key | Y/N confirmations |
| `more_prompt` | any_key | Pagination |
| `quit_confirm` | single_key | Quit confirmation |
| `enter_number` | multi_key | Numeric input |
| `sector_command` | single_key | Sector navigation |
| `planet_command` | single_key | Planet management |
| `twgs_select_game` | single_key | TWGS game selection |
| `twgs_main_menu` | single_key | TWGS main menu |
| `command_prompt_generic` | single_key | Generic commands |

## Usage

### Current Command Surface (Recommended)

Use play mode for the intelligent runner:

```bash
bbsbot tw2002 play --mode intelligent
```

Use direct bot mode with an AI strategy config:

```bash
bbsbot tw2002 bot -c examples/configs/ai_strategy_ollama.yml
```

Legacy compatibility command (still available, but not preferred):

```bash
bbsbot script play_tw2002_intelligent
```

### Running the Intelligent Bot

```bash
# Full playthrough with pattern testing
bbsbot tw2002 play --mode intelligent
```

This will:
1. Connect to TW2002 BBS at localhost:2002
2. Navigate TWGS menus to enter game
3. Test various commands to trigger patterns
4. Test navigation (moving sectors)
5. Test quit sequence
6. Generate comprehensive report
7. Save results to `logs/reports/intelligent-bot-{timestamp}.json`

### Running Pattern Validator

```bash
# Systematic validation of all 13 patterns
bbsbot script test_all_patterns
```

This will:
1. Test each pattern with specific trigger sequence
2. Validate detection accuracy
3. Track pattern coverage
4. Generate validation report
5. Save to `logs/reports/pattern-validation-results.json`

## Expected Output

### Intelligent Bot Output

```
================================================================================
INTELLIGENT TW2002 BOT - PROMPT DETECTION TESTING
================================================================================

✓ Connected to localhost:2002
✓ Learning enabled with 13 patterns

🎮 PHASE 1: Navigate TWGS to Game Entry
================================================================================

[1] Select 'A' - My Game
  → Detected: twgs_select_game (single_key)

[2] Enter player name: TestBot
  → Detected: login_username (multi_key)

🧪 PHASE 2: Pattern Testing
================================================================================

🧪 Testing: Show help menu
[3] Show help menu (from main_menu)
  → Detected: command_prompt_generic (single_key)
✓ Test result: ✓ Detected command_prompt_generic

... [more tests] ...

📊 Pattern Matches:
  ✓ twgs_select_game: 1 times
  ✓ login_username: 1 times
  ✓ main_menu: 8 times
  ✓ command_prompt_generic: 3 times
  ✓ press_any_key: 2 times
  ... etc ...

⚠️  Patterns NOT matched (3):
  - planet_command
  - login_password
  - more_prompt

💾 Screen Saver:
  Saved: 24 unique screens
  Location: .bbs-knowledge/games/tw2002/screens/
```

### Generated Reports

**JSON Report** (`logs/reports/intelligent-bot-{timestamp}.json`):
```json
{
  "timestamp": 1770159828,
  "steps": 35,
  "pattern_matches": {
    "twgs_select_game": 1,
    "login_username": 1,
    "main_menu": 8,
    "command_prompt_generic": 3,
    ...
  },
  "test_results": [
    {
      "command": "?\r",
      "description": "Show help menu",
      "expected_pattern": "command_prompt_generic",
      "detected_pattern": "command_prompt_generic",
      "success": true,
      "notes": ["✓ Matched expected pattern"]
    },
    ...
  ],
  "prompt_sequences": [
    {"action": "Select 'A' - My Game", "from_prompt": "twgs_main_menu"},
    {"action": "Enter player name: TestBot", "from_prompt": "twgs_select_game"},
    ...
  ]
}
```

**Markdown Report** (`logs/reports/intelligent-bot-{timestamp}.md`):
- Summary statistics
- Pattern matches
- Unmatched patterns
- Test results with details
- Screen save locations

## How Detection Works

### Detection Flow

```python
# 1. Read screen
snapshot = await self.read_screen()

# 2. Check detection
if 'prompt_detected' in snapshot:
    detected = snapshot['prompt_detected']
    prompt_id = detected['prompt_id']      # e.g., "main_menu"
    input_type = detected['input_type']    # "single_key", "multi_key", "any_key"
    matched_text = detected['matched_text'] # Text that matched regex

# 3. Respond based on input_type
if input_type == 'single_key':
    await self.session.send("D")  # Single char, no Enter
elif input_type == 'multi_key':
    await self.session.send("MyName\r")  # String + Enter
elif input_type == 'any_key':
    await self.session.send(" ")  # Space to continue
```

### Smart Waiting

```python
async def wait_for_prompt(expected_prompt_id=None, max_wait=10.0):
    """Wait until prompt detected or screen stable."""
    while time.time() - start < max_wait:
        snapshot = await self.read_screen()

        # Check for detection
        if 'prompt_detected' in snapshot:
            detected = snapshot['prompt_detected']

            # Match expected prompt (if specified)
            if expected_prompt_id:
                if detected['prompt_id'] == expected_prompt_id:
                    return snapshot  # Got it!
            else:
                return snapshot  # Any prompt is fine

        # No detection - check if screen stable
        if screen == last_screen:
            stable_count += 1
            if stable_count >= 3:
                # Screen stable, might be unknown prompt
                return snapshot
```

### Auto-Pagination

```python
async def handle_pagination(snapshot):
    """Auto-continue through 'more' prompts."""
    while True:
        if 'prompt_detected' not in snapshot:
            break

        detected = snapshot['prompt_detected']
        input_type = detected['input_type']
        prompt_id = detected['prompt_id']

        # Check if pagination prompt
        if input_type == 'any_key' or 'more' in prompt_id.lower():
            await self.session.send(" ")  # Continue
            snapshot = await self.read_screen()
        else:
            break  # Real prompt, return control
```

## Pattern Testing Strategy

### Test Sequence for Each Pattern

1. **login_username** - Appears on initial connect
2. **login_password** - Send username → password prompt
3. **twgs_main_menu** - After login
4. **twgs_select_game** - Select game option from TWGS
5. **main_menu** - In-game command prompt
6. **command_prompt_generic** - Help menu, various commands
7. **press_any_key** - Display screens, info pages
8. **more_prompt** - Long range scan, reports
9. **sector_command** - At sector prompt
10. **enter_number** - Move command (asks for sector)
11. **quit_confirm** - Quit command
12. **yes_no_prompt** - Same as quit confirm
13. **planet_command** - Land on planet (harder to trigger)

### Validation Criteria

For each pattern:
- ✓ Pattern matches when expected
- ✓ Pattern doesn't false-match
- ✓ `input_type` is correct
- ✓ `expect_cursor_at_end` is appropriate
- ✓ Bot responds correctly

## Success Metrics

**Pattern Coverage**: >90% of patterns matched during playthrough
- Target: 11-12 of 13 patterns
- planet_command may be difficult without specific gameplay

**False Positives**: <5% incorrect detections
- Patterns should only match intended screens
- Generic patterns should not override specific ones

**Automation**: Bot completes session autonomously
- No manual intervention needed
- Handles pagination automatically
- Graceful handling of unknown prompts

**Documentation**: Complete screen library
- All unique screens saved
- Prompt sequences recorded
- Pattern→screen mapping

## Next Steps

### Phase 1: Run Tests ✓
1. Run `bbsbot tw2002 play --mode intelligent`
2. Review pattern matches
3. Check for false positives/negatives

### Phase 2: Refine Patterns
1. Fix patterns that didn't match
2. Add patterns for unmatched prompts
3. Update `expect_cursor_at_end` flags

### Phase 3: Add Prediction (Optional)
1. Build state machine for game location
2. Predict next prompt based on command
3. Validate detection vs prediction
4. Log anomalies

## Troubleshooting

### Pattern Not Detected

**Symptom**: Expected pattern doesn't match

**Fixes**:
1. Check regex in `prompts.json`
2. Look at saved screen text
3. Verify pattern regex matches actual text
4. May need to adjust regex or flags

### False Positive

**Symptom**: Pattern matches wrong screen

**Fixes**:
1. Make pattern more specific
2. Add negative lookahead/lookbehind
3. Adjust pattern priority (more specific first)

### Screen Stable, No Prompt

**Symptom**: Bot waits, screen doesn't change, no detection

**Possible causes**:
1. Unknown prompt (needs new pattern)
2. Pattern regex doesn't match
3. Game waiting for specific input

**Debug**:
1. Look at saved screen
2. Manually identify the prompt
3. Create pattern or fix existing one

## Advanced Features

### Flow Tracking

The bot tracks sequences:
```
Action: "Select 'A'" → From: "twgs_main_menu"
Action: "Enter name" → From: "twgs_select_game"
Action: "Show help" → From: "main_menu"
```

Use this to:
- Build state diagrams
- Identify common paths
- Detect navigation loops

### Predictive Navigation (Future)

```python
class PredictiveBot(IntelligentBot):
    def __init__(self):
        super().__init__()
        self.state_machine = GameStateMachine()

    async def send_command(self, cmd):
        # Predict next prompt
        predicted = self.state_machine.predict_next(cmd)

        # Send command
        snapshot = await self.send_and_wait(cmd)

        # Validate detection
        detected = snapshot['prompt_detected']['prompt_id']
        if detected != predicted:
            self.log_anomaly(cmd, predicted, detected)
```

## Resources

- Pattern definitions: `.bbs-knowledge/games/tw2002/prompts.json`
- Saved screens: `.bbs-knowledge/games/tw2002/screens/`
- Test results: `logs/reports/intelligent-bot-*.json`
- Detector code: `src/bbsbot/learning/detector.py`

## Contributing

When adding new patterns:
1. Observe screen where prompt appears
2. Identify the prompt text
3. Write regex that matches uniquely
4. Set correct `input_type`
5. Test with `bbsbot script test_all_patterns`
6. Validate no false positives
