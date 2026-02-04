# TW2002 Bot - Systematic Debugging Guide

When the bot gets stuck in the login phase, use the **diagnostic tools** to systematically understand what's happening.

## The Systematic Approach

### Step 1: Determine Current Screen State

**Tool**: `debug_login_diagnostic_fixed.py`

```bash
python debug_login_diagnostic_fixed.py
```

This shows:
- Exact screen content at each step
- Detected prompt ID (what the bot thinks it sees)
- Input type (single_key, multi_key, any_key)
- Any error messages on screen

**Example output:**
```
STEP 1: prompt.login_name (multi_key)
Screen shows:
  "Please enter your name (ENTER for none):"

✓ DETECTED: prompt.login_name (multi_key)
→ Sending username using send_input() with \r newline

STEP 2: prompt.menu_selection (single_key)  
Screen shows:
  <A> My Game      <B> The AI Apocalypse
  Selection (? for menu):

✓ DETECTED: prompt.menu_selection (single_key)
✓ REACHED MENU SELECTION - Success!
```

### Step 2: Look for Regex Issues

If the diagnostic shows a mismatch between what's on screen and what was detected:

1. Find the rule in `games/tw2002/rules.json`
2. Check the pattern regex
3. Test if pattern matches the actual text

**Example mismatch:**
```
Screen shows: "Sector command:"
Detected: prompt.pause_space_or_enter (WRONG!)
Expected: prompt.sector_command
```

**Fix**: Update regex in rules.json for sector_command

### Step 3: Understand Why It's Looping

**Common causes:**

| Symptom | Cause | Fix |
|---------|-------|-----|
| Same prompt repeats 3+ times | Function sending wrong thing | Check `send_input()` is being used |
| Username echoed but not submitted | Missing `\r` newline | Use `send_input()` not `bot.session.send()` |
| Multiple prompts on same screen | Competing regex patterns | Make patterns more specific |
| Screen blank | Network/connection issue | Check server is running |
| Error messages on screen | Wrong credentials | Verify username/password |

### Step 4: Educational Diagnostic

**Tool**: `debug_login_show_screens.py`

This intentionally shows what happens when you DON'T use `send_input()`:

```bash
python debug_login_show_screens.py
```

**What you'll see:**
```
STEP 1: prompt.login_name → screen shows "Please enter your name:"
STEP 2: Screen echoes username but prompt repeats
STEP 3: Username doubled - "testbottestbot"
ERROR: Stuck in loop!
```

**Why it fails**: Direct `bot.session.send()` without `\r` newline

## Key Implementation Details

### Correct Way (What Bot Does)

```python
# In login.py
await send_input(bot, username, input_type)
```

The `send_input()` function (io.py:97-120):
- For `multi_key`: adds `\r` (carriage return)
- For `single_key`: sends without newline
- For `any_key`: sends space

### Wrong Way (What Causes Loop)

```python
# DON'T DO THIS
await bot.session.send(username)  # No \r, no newline!
```

## Debugging Workflow

When bot gets stuck:

1. **Calm down** - You have diagnostic tools
2. **Run diagnostic** - See exactly what's happening
3. **Identify the issue** - Match symptom to table above
4. **Check implementation** - Use correct function
5. **Verify with corrected diagnostic** - Confirm fix works

## Common Issues & Fixes

### Issue: Loop in login_name prompt

**Symptom**: Username echoed multiple times
```
Step 1: testbot
Step 2: testbottestbot  
Step 3: ERROR - loop detected
```

**Cause**: Calling `bot.session.send(username)` without newline

**Fix**: 
```python
# Change this:
await bot.session.send(username)

# To this:
await send_input(bot, username, input_type)
```

### Issue: Wrong prompt detected

**Symptom**: 
```
Screen: "Enter your choice:"
Detected: prompt.pause_space_or_enter (WRONG!)
```

**Cause**: Regex pattern too broad, matching wrong text

**Fix**: Update `games/tw2002/rules.json` - make pattern more specific

### Issue: Stuck after game selection

**Symptom**: Sends 'B', then timeouts on pause screens

**Cause**: Pause prompts repeat 50+ times (normal), loop detection threshold too low

**Fix**: Already fixed in io.py - pause_space_or_enter exempted from loop detection

## Testing Your Fix

After making a change, run diagnostic:

```bash
python debug_login_diagnostic_fixed.py
```

Expected output:
- ✓ Login name sent successfully
- ✓ Menu selection reached
- ✓ Game loads (shows pause screens)
- ✓ LOGIN COMPLETE message

## Remember

- **Never blindly send commands** - Always understand why first
- **Show, don't guess** - Use diagnostics to see what's happening
- **One thing at a time** - Fix one issue, test, verify
- **Use the right functions** - `send_input()` for normal prompts, `bot.session.send()` only for special cases

