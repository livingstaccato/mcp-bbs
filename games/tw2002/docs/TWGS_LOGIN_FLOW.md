# TWGS Login Flow Documentation

**IMPORTANT**: This documents the actual TWGS v2.20b login flow. The bot MUST follow this exactly.

## Quick Reference - Working Login (2026-02-05)

The login sequence takes approximately **46 seconds** and handles:
1. Login prompt → username
2. Game selection → B (AI Apocalypse)
3. TW2002 game menu → T (Play Trade Wars) - may need multiple presses
4. "Show today's log?" → N
5. Pause screens → space
6. New character flow: password, ship name + Y confirmation
7. Planet/Sector command prompt = **SUCCESS**

## Connection Types

### Type 1: Fresh Telnet Connection (Bot's SessionManager)
When connecting via the bot's SessionManager with proper telnet negotiation:

```
Screen 1: "Telnet connection detected."
          "Please enter your name (ENTER for none):"

Action: Send username + Enter (multi_key input)

Screen 2: Game selection menu
          "Selection (? for menu):"

Action: Send game letter (e.g., "B") (single_key input)
```

### Type 2: BBSBot Direct Connection
When connecting via BBSBot tools, the login prompt may be skipped:

```
Screen 1: Game selection menu (skips login prompt)
          "Selection (? for menu):"
```

## Game Selection Flow

After selecting a game (e.g., pressing "B"), TWGS has a **complex flow**:

### Flow A: Game with Description
```
1. Press B at "Selection (? for menu):"
2. Shows: "No description..." or game description
         "[ANY KEY]"
3. Press any key
4. Shows: "Show Game Descriptions"
          "Select game (Q for none):"
5. This is description-viewing mode, NOT game entry!
6. Press Q to exit back to main menu
```

**CRITICAL**: Pressing a game letter (A/B) shows the description first, then enters "Show Game Descriptions" mode. You must press Q to exit this mode.

### Flow B: Private Game (Password Required)
```
1. Press A at "Selection (? for menu):"
2. Shows: "This is a private game. Please enter a password:"
3. Enter password + Enter
4. If correct: proceeds to game
5. If wrong: "Invalid password!" returns to menu
```

### Flow C: Direct Game Entry (After Username)
When a username was provided at login, the flow may differ:
```
1. Enter username at login
2. Select game B
3. May show pause screens: "[pause] press space or enter"
4. Eventually reaches: "Command [?]:" or "Sector Command:"
```

## Prompt Patterns

| Prompt | Regex | Input Type | Notes |
|--------|-------|------------|-------|
| Login name | `enter.*name` | multi_key | Send username + Enter |
| Game selection | `selection.*\?` | single_key | Send game letter |
| Game description select | `select game.*Q for none` | single_key | Send Q to exit |
| Private game password | `private game.*password` | multi_key | Send password + Enter |
| Any key | `\[ANY KEY\]` | any_key | Send space |
| Pause | `\[pause\].*press.*space.*enter` | any_key | Send space |
| Command prompt | `command.*\?` | single_key | GAME REACHED! |
| Sector command | `sector.*command` | single_key | GAME REACHED! |

## Common Issues

### Issue 1: Stuck in "Show Game Descriptions" Mode
**Symptom**: Bot keeps seeing pause prompts, never reaches game
**Cause**: Bot selected game, saw description, now in description mode
**Fix**: Detect "Select game (Q for none):" and send Q

### Issue 2: Username Not Submitted
**Symptom**: Screen shows "testbottestbot" (username repeated)
**Cause**: Sending username without Enter
**Fix**: Use `send_input()` which adds "\r" for multi_key

### Issue 3: Password Prompt Not Detected
**Symptom**: Bot stuck after selecting private game
**Cause**: Pattern `private_game_password` not matching
**Fix**: Check regex matches "This is a private game. Please enter a password"

## Correct Bot Flow

```python
# Phase 1: Login
1. Wait for prompt
2. If login_name: send username + Enter
3. If menu_selection: proceed to Phase 2

# Phase 2: Game Selection
4. Extract game options from screen
5. Find TW2002 game (look for "Trade Wars", "TW", "Apocalypse")
6. Send game letter

# Phase 3: Handle Post-Selection
7. Wait for prompt
8. If "Select game (Q for none)": send Q, go back to step 7
9. If private_game_password: send password + Enter
10. If any_key or pause: send space
11. If command or sector_command: DONE - game reached!
12. Loop until command prompt or timeout
```

## Testing

To test the login flow:
```bash
python debug_login_show_screens.py
```

To manually trace:
```bash
# Use BBSBot tools
bbsbot__bbs_connect localhost 2002
bbsbot__bbs_read
bbsbot__bbs_send "B"
# etc.
```
