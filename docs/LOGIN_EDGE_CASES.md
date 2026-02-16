# TW2002 Login Edge Cases

This document records edge cases discovered during testing of the twbot login and orientation system.

## Edge Cases by Category

### 1. Pattern Matching Issues

**Rules.json vs Prompts.json Priority**
- The BBSBot learning engine loads patterns from `rules.json` first, falling back to `prompts.json`
- When adding new patterns, they MUST be added to `rules.json` in the game namespace
- Location: `games/tw2002/rules.json`

**cursor_at_end Requirement**
- The PromptDetector checks `cursor_at_end` for patterns with `expect_cursor_at_end: true`
- Set `expect_cursor_at_end: false` for patterns that may appear on screens with additional content
- Example: The TW2002 game menu "Enter your choice:" often has other text above it

**Kind Field Validation**
- The `kind` field in rules.json must be one of: `login_name`, `login_pass`, `game_pass`, `pause`, `confirm`, `menu`, `input`, `unknown`
- Invalid values cause pydantic validation errors

### 2. Game Configuration Issues

**Private vs Open Games**
- "My Game" (option A) is a closed/private game requiring admin registration
- "The AI Apocalypse" (option B) allows open registration
- Detection: Look for "closed game" or "must request a player account" in screen text

**Game Password Prompt**
- Private games show: "This is a private game. Please enter a password:"
- Must handle this before character creation can proceed

### 3. Screen Timing Issues

**is_idle Detection**
- The `wait_and_respond` function requires `is_idle=True` before returning prompt detection
- Rapid screen transitions may prevent idle state detection
- Solution: Accept non-idle prompts after 80% of timeout elapsed

**Baud Rate Simulation**
- At low baud rates, screens render character-by-character
- `_wait_for_screen_stability()` polls until screen stops changing
- Configurable stability threshold (default: 100ms unchanged)

### 4. Character Creation Flow

**Name Already Taken**
- If BBS name is taken, game asks for alias
- Detection: Look for "alias" and "want to use" on last line

**Multiple Password Prompts**
- Character creation has TWO password prompts (enter + verify)
- Both show "Password?" but must be handled sequentially

**Name Confirmation**
- After ship/planet naming, game asks "is what you want?" (Y/N)
- Must detect BEFORE generic yes_no_prompt handler runs

### 5. Loop Detection

**Menu Bounce-Back**
- Invalid credentials or access issues cause return to BBS game selection menu
- Detection: Track how many times `menu_selection` appears after game selection
- Indicates: Wrong password, closed game, or session issue

**Pause Screen Accumulation**
- Multiple pause screens may appear on same screen buffer
- Detection: "[Pause]" mid-screen + "Enter your choice:" at end
- Solution: Added `prompt.pause_simple` pattern for bare `[Pause]`

## Debugging Tips

1. **Pattern Not Matching?**
   - Check if pattern is in `rules.json` (not just `prompts.json`)
   - Verify `expect_cursor_at_end` setting
   - Test regex manually against actual screen content

2. **Timeout After Action?**
   - Add debug output showing detected prompt vs actual_prompt
   - Check `is_idle` state in snapshot
   - Consider increasing timeout or relaxing idle requirement

3. **Game Kick-Back?**
   - Look for error messages in screen content
   - Check game access mode (open vs closed)
   - Verify game password is correct

## Test Verification

Run orientation recovery tests:
```bash
bbsbot script test_orientation_recovery
```

Run hypothesis property tests:
```bash
pytest tests/test_orientation_hypothesis.py -v
```

These tests verify:
- Context detection handles garbage input
- Parsing works with edge cases (ANSI codes, unicode, long screens)
- Recovery from confused states works
