# Intelligent Bot Quick Reference

## Running the Bots

### Full Intelligent Bot
```bash
python play_tw2002_intelligent.py
```
- Navigates TWGS → Game
- Tests commands
- Tests navigation
- Tests quit sequence
- Generates comprehensive report

### Pattern Validator
```bash
python test_all_patterns.py
```
- Tests each of 13 patterns individually
- Validates accuracy
- Generates coverage report

## Key Methods

### IntelligentBot Core Methods

```python
# Wait for any prompt to appear
snapshot = await bot.wait_for_prompt()

# Wait for specific prompt
snapshot = await bot.wait_for_prompt(expected_prompt_id="main_menu")

# Send keys and wait for response
snapshot = await bot.send_and_wait("D\r", "Display computer")

# Handle pagination automatically
snapshot = await bot.handle_pagination(snapshot)

# Test a command with validation
await bot.test_command("?\r", "Help menu", expected_pattern="command_prompt_generic")
```

## Detection Response

### Based on input_type

```python
if 'prompt_detected' in snapshot:
    detected = snapshot['prompt_detected']
    input_type = detected['input_type']

    if input_type == 'single_key':
        # Send single character, no Enter
        await session.send("D")

    elif input_type == 'multi_key':
        # Send string + Enter
        await session.send("PlayerName\r")

    elif input_type == 'any_key':
        # Send space to continue
        await session.send(" ")
```

## Common Patterns

### Navigate Menus
```python
# Wait for menu
snapshot = await bot.wait_for_prompt()

# Send selection
snapshot = await bot.send_and_wait("A\r", "Select option A")

# Handle any pagination
snapshot = await bot.handle_pagination(snapshot)
```

### Execute Command Sequence
```python
commands = [
    ("D\r", "Display computer"),
    ("I\r", "Show inventory"),
    ("P\r", "Port report"),
]

for cmd, desc in commands:
    snapshot = await bot.send_and_wait(cmd, desc)
    snapshot = await bot.handle_pagination(snapshot)
```

### Handle Unknown Screens
```python
# If no prompt detected, screen is stable
snapshot = await bot.wait_for_prompt(max_wait=5.0)

if 'prompt_detected' not in snapshot:
    # Screen stable but no pattern matched
    # This is an unknown prompt - save for analysis
    print("Unknown prompt - check saved screen")
```

## Output Files

### Generated Reports

**Intelligent Bot**:
- `.provide/intelligent-bot-{timestamp}.json` - Full test results
- `.provide/intelligent-bot-{timestamp}.md` - Human-readable report

**Pattern Validator**:
- `.provide/pattern-validation-results.json` - Validation data
- `.provide/pattern-validation-results.md` - Coverage report

### Saved Screens
`.bbs-knowledge/games/tw2002/screens/{hash}.txt` - Unique screens

## Snapshot Structure

```python
snapshot = {
    'screen': str,              # Formatted screen text (80x25)
    'screen_hash': str,         # SHA256 of screen
    'cursor': {'x': int, 'y': int},
    'prompt_detected': {        # If prompt found
        'prompt_id': str,       # e.g., "main_menu"
        'input_type': str,      # "single_key", "multi_key", "any_key"
        'matched_text': str,    # Text that matched regex
    }
}
```

## Tracking & Metrics

### Pattern Matches
```python
bot.pattern_matches = {
    'main_menu': 8,
    'command_prompt_generic': 3,
    'press_any_key': 2,
    # ...
}
```

### Prompt Sequences
```python
bot.prompt_sequences = [
    ("Select 'A' - My Game", "twgs_main_menu"),
    ("Enter player name", "twgs_select_game"),
    ("Show help", "main_menu"),
    # ...
]
```

### Test Results
```python
bot.pattern_test_results = [
    {
        'command': '?\r',
        'description': 'Show help menu',
        'expected_pattern': 'command_prompt_generic',
        'detected_pattern': 'command_prompt_generic',
        'success': True,
        'notes': ['✓ Matched expected pattern']
    },
    # ...
]
```

## Pattern Coverage

### All 13 Patterns

| Pattern ID | Input Type | Tested By |
|------------|------------|-----------|
| login_username | multi_key | Initial connect |
| login_password | multi_key | After username |
| twgs_main_menu | single_key | After login |
| twgs_select_game | single_key | Select game |
| main_menu | single_key | In-game prompt |
| command_prompt_generic | single_key | Help menu |
| press_any_key | any_key | Display screens |
| more_prompt | any_key | Long reports |
| sector_command | single_key | At sector |
| planet_command | single_key | On planet |
| enter_number | multi_key | Move command |
| quit_confirm | single_key | Quit game |
| yes_no_prompt | single_key | Confirmations |

## Debugging

### Check Detection
```python
snapshot = await bot.read_screen()

if 'prompt_detected' in snapshot:
    print(f"Detected: {snapshot['prompt_detected']}")
else:
    print("No detection")
    print(f"Screen:\n{snapshot['screen']}")
    # Save this screen for pattern creation
```

### Show Screen
```python
await bot.show_screen(snapshot, max_lines=25, title="Debug")
```

### Track Steps
```python
print(f"Step {bot.step_counter}: {action}")
print(f"Last prompt: {bot.last_prompt_id}")
print(f"Location: {bot.game_location}")
```

## Troubleshooting

### Pattern Not Detected

1. Check saved screen: `.bbs-knowledge/games/tw2002/screens/`
2. Look at pattern regex in `prompts.json`
3. Test regex against screen text
4. Adjust pattern or add new one

### False Positive

1. Make pattern more specific
2. Add context to regex (before/after text)
3. Check pattern priority order

### Screen Stuck

1. Check if screen is stable: `bot.wait_for_prompt()` returns after timeout
2. Look for unknown prompt on screen
3. Add pattern for this prompt
4. Or manually send expected input

## Success Metrics

- **Coverage**: >90% patterns matched (11-12 of 13)
- **False Positives**: <5% wrong detections
- **Automation**: Complete session without manual intervention
- **Documentation**: All unique screens saved

## Next Steps

1. Run `play_tw2002_intelligent.py`
2. Review pattern match results
3. Check for unmatched prompts
4. Refine patterns in `prompts.json`
5. Re-test with `test_all_patterns.py`
6. Iterate until >90% coverage
