# TW2002 BBS Login Solution

## Problem
When connecting to TW2002 via BBS MCP on localhost:2002, the private game password "game" was being rejected with "Invalid password!" error.

## Root Cause
Sending `"game\r"` as a single string resulted in 6 asterisks being displayed instead of 4, indicating the carriage return was being encoded as 2 additional characters. This caused the password validation to fail.

## Solution
**Separate the password text from the Enter key:**

1. Send only the password text: `"game"` (without `\r`)
2. Verify 4 asterisks appear on screen (one per character)
3. Then send `"\r"` separately to submit

## Correct Login Sequence

```python
# 1. Connect to BBS
bbs_connect(host="localhost", port=2002)

# 2. Read initial TWGS menu
# Shows: "Selection (? for menu):"

# 3. Select game (directly from main menu, not via game descriptions)
bbs_send("A")
bbs_read()  # Should show: "This is a private game. Please enter a password:"

# 4. Send password WITHOUT carriage return
bbs_send("game")  # NOT "game\r"
bbs_read()  # Verify exactly 4 asterisks: "****"

# 5. Submit password with separate Enter
bbs_send("\r")
bbs_read()  # Should show: "What is your name?"

# 6. Enter username
bbs_send("gemini")
bbs_send("\r")

# 7. Select ANSI graphics
# Shows: "Use ANSI graphics?"
bbs_send("Y")

# 8. Continue through game intro
# Shows [Pause] prompts and main menu
```

## Key Lesson
When using BBS MCP for password entry, always send the password string separately from the Enter/Return key to avoid character encoding issues.