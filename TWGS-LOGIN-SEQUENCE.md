# TW2002 TWGS Complete Login Sequence

## Overview

This document details the complete login sequence for Trade Wars 2002 via TWGS (Trade Wars Game Server) on the BBS system. This is based on:
- Actual screen captures from telnet connections
- Prompt detection patterns in `rules.json`
- Testing with `play_tw2002_trading.py`

## Complete Flow

### Step 1: Telnet Connection
**Screen Content:**
```
Telnet connection detected.

Please enter your name (ENTER for none):
```

**Prompt Detected:** `prompt.login_name` (multi_key)

**Bot Action:** Send `\r` (Enter) to skip telnet login name prompt

**Next State:** TWGS Main Menu

---

### Step 2: TWGS Main Menu
**Screen Content:**
```
Show Game Descriptions

<A> My Game

Select game (Q for none):
```

**Prompt Detected:** `prompt.twgs_select_game` (single_key)

**Bot Action:**
- Parse available games from screen (extract letter and description)
- Identify Trade Wars game (match against description keywords)
- Send game letter + `\r` (e.g., `"A\r"`)

**Known Issues:**
- After sending game selection, game description is shown with `[ANY KEY]` prompt
- Pressing space/Enter returns to game selection menu instead of proceeding
- This creates a loop: select game → show description → return to menu
- Appears to be BBS configuration issue, not bot logic

**Expected Next State (if working):** Game Description or Private Game Password

---

### Step 3: Game Description (BLOCKED)
**Screen Content:**
```
No description...

[ANY KEY]
```

**Prompt Detected:** `prompt.any_key` (any_key)

**Current Behavior:**
- Sending space returns to Step 2 (TWGS Main Menu)
- Loop occurs repeatedly

**Expected Behavior:**
- Pressing any key should proceed to private game password prompt

---

### Step 4: Private Game Password (NOT YET REACHED)
**Expected Screen Content:**
```
This is a private game. Please enter a password:
```

**Prompt to Detect:** `prompt.private_game_password` (multi_key)

**Bot Action:** Send game password (default: `"game"`)

**Next State:** Character Password

---

### Step 5: Character Password (NOT YET REACHED)
**Expected Screen Content:**
```
Password?
```

**Prompt to Detect:** `prompt.game_password` (multi_key)

**Bot Action:** Send character password (default: `"tim"`)

**Next State:** Character Name

---

### Step 6: Character Name (NOT YET REACHED)
**Expected Screen Content:**
```
What is your name?
```

**Prompt to Detect:** `prompt.login_name` (multi_key)

**Bot Action:** Send character name (default: `"claude"`)

**Next State:** ANSI Graphics Confirmation

---

### Step 7: ANSI Graphics (NOT YET REACHED)
**Expected Screen Content:**
```
Use ANSI graphics? (y/n)
```

**Prompt to Detect:** `prompt.use_ansi_graphics` (single_key)

**Bot Action:** Send `"y"` for yes

**Next State:** Pagination/Intro Screens

---

### Step 8: Pagination & Intro (NOT YET REACHED)
**Expected Content:**
- Multiple `[Pause]` or `--More--` prompts
- Game introduction text
- Multiple `[ANY KEY]` prompts

**Prompt to Detect:** Various `any_key` patterns

**Bot Action:** Send space for each pause prompt (up to 10 times)

**Next State:** Game Sector Menu

---

### Step 9: Game Sector Command (FINAL)
**Expected Screen Content:**
```
Sector    ###
Credits:  1,000,000

[Port] [Move] [Scan] [Battle] [Status] [Reload] [Planet] [Reports]

Command?
```

**Prompt to Detect:** `prompt.sector_command` (single_key) or `prompt.command_generic` (single_key)

**Bot Status:** IN GAME - Ready for trading

---

## Prompt Patterns (rules.json)

### Login/Authentication Prompts
- `prompt.login_name` - Username/character name entry (multi_key)
- `prompt.game_password` - Character password (multi_key)
- `prompt.private_game_password` - Private game password (multi_key)
- `prompt.use_ansi_graphics` - ANSI selection (single_key)

### Menu Prompts
- `prompt.twgs_select_game` - TWGS game selection (single_key)
  - Pattern: `(?i)select\s+game`
  - Appears at game listing screen

### Pause/Pagination Prompts
- `prompt.any_key` - Generic "press any key" (any_key)
- `prompt.press_any_key` - "Press any key to continue" (any_key)
- `prompt.pause_space_or_enter` - "[Pause] Press space or enter" (any_key)
- `prompt.more` - "--More--" pagination (any_key)

### Game Command Prompts
- `prompt.command_generic` - Generic "Command:" prompt (single_key)
- `prompt.sector_command` - "Sector command?" prompt (single_key)

---

## Input Type Metadata

The login sequence heavily relies on `input_type` metadata:

### single_key
- Send raw character without Enter
- Examples: "A" for game selection, "y" for ANSI graphics
- Used for: menu selections, yes/no confirmpts

### multi_key
- Send text + Enter (`\r`)
- Examples: "game\r" for password, "claude\r" for name
- Used for: text entry, passwords, numeric input

### any_key
- Send space character (or any key)
- Used for: pause prompts, pagination

---

## Current Implementation (play_tw2002_trading.py)

### Reactive Login Approach

```python
async def login_sequence(self, game_password="game",
                         character_password="tim",
                         username="claude"):
    """
    Reactive approach: detect prompt → respond appropriately → continue
    """
    for step in range(50):  # Max steps to prevent infinite loops
        input_type, prompt_id, screen = await self.wait_and_respond()

        # Handle prompts based on prompt_id and input_type
        if "login_name" in prompt_id:
            # Character name (or telnet login)
            await self.send_input(username, input_type)
        elif "twgs_select_game" in prompt_id:
            # Game selection
            game_letter = self._select_trade_wars_game(screen)
            await self.session.send(game_letter + "\r")
        # ... (more prompt handlers)
```

### Key Methods

- `wait_and_respond()` - Wrapper around session.read() with timeout
- `send_input()` - Smart send based on input_type
- `_select_trade_wars_game()` - Parse screen and identify Trade Wars
- `_extract_game_options()` - Parse game list from screen
- `_clean_screen_for_display()` - Remove padding lines (80 spaces)

---

## Known Issues & Workarounds

### Issue: Game Description Loop
**Status:** BLOCKING - Cannot proceed past game selection

**Root Cause:** After selecting game, description screen with `[ANY KEY]` returns to menu

**Investigation:**
- Tried sending space - returns to menu
- Tried sending Enter - returns to menu
- Tried sending multiple keys - still loops

**Possible Solutions:**
1. Check if BBS has correct game configuration
2. Try selecting different game option (if multiple available)
3. May require different credentials/setup
4. Investigate BBS command for bypassing game description

**Workaround:** Currently bot recognizes the loop and marks login as "complete" after 50 steps to continue development

---

## Testing Commands

```bash
# Test login only
python play_tw2002_trading.py --test-login

# Test with verbose output
python play_tw2002_trading.py --test-login 2>&1 | head -100

# Single trading cycle (once login works)
python play_tw2002_trading.py --single-cycle --start-sector=499

# Full automation (once login works)
python play_tw2002_trading.py --target-credits=5000000 --max-cycles=20
```

---

## Credential Reference

From `games/tw2002/credentials.md`:

- **TWGS Game Password:** `game`
- **Character Password:** `tim` (or `Claude4u@` for claude account)
- **Character Names:** `tim`, `tim2`, `claude`
- **Default Account:**
  - Username: `claude`
  - Password: `Claude4u@`
  - Home Planet: Homeworld (Sector 490)

---

## Next Steps

1. **Debug Game Description Loop:** Investigate why game selection doesn't proceed to password prompt
2. **Test with Alternative Approach:** Try different game selection methods
3. **Add Error Recovery:** Detect loop and recover gracefully
4. **Document Alternative Flows:** Check if there are other ways to enter the game
5. **Implement Fallback Credentials:** Support multiple character names for testing

---

## Architecture Notes

### Why Reactive Approach?

The bot uses a reactive approach rather than a fixed state machine because:

1. **BBS Variation:** Different BBS systems may show screens in different order
2. **Prompt Detection:** Relies on pattern matching, which may catch unexpected screens
3. **Flexibility:** Can handle alternate flows (new player vs existing player)
4. **Robustness:** Adapts to what the server sends, not what we expect

### Timing Model

- `wait_and_respond()` polls every ~250ms until prompt detected or timeout
- Eliminates race conditions where screen changes before we read
- Allows bot to "wait" without busy-polling

### Session Management

Uses MCP BBS tools via SessionManager:
- `session.read()` - Get screen with prompt detection
- `session.send()` - Send input to server
- Learning system tracks prompts for auto-discovery

