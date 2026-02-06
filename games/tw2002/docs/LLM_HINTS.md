# TW2002 LLM Hints

Knowledge discovered during debugging sessions that helps LLMs avoid common pitfalls.

**NOTE:** These hints are also embedded in `rules.json` under the `llm_hints` field for programmatic access.

## Trading Protocol

### Pending Trade Flag
**Problem:** When skipping a commodity (entering 0 quantity), TW2002 still shows price offer screens. The bot incorrectly accepts these offers for commodities we didn't want to trade.

**Solution:** Track `pending_trade` flag:
- Set `pending_trade = True` when entering non-zero quantity
- Set `pending_trade = False` when entering 0 or skipping
- Only accept price offers when `pending_trade is True`
- Reset `pending_trade = False` after accepting an offer

**Code Pattern:**
```python
pending_trade = False

# In quantity handler:
if amount > 0:
    pending_trade = True
else:
    pending_trade = False
await send(f"{amount}\r")

# In price offer handler:
if price_match and pending_trade:
    await send("Y")  # Accept
    pending_trade = False  # Reset after trade
elif price_match and not pending_trade:
    pass  # Skip - we didn't enter quantity for this
```

### Screen Buffer Has Old Data
**Problem:** Screen buffer may contain old sector numbers at the top from previous screens. Using `re.search()` finds the FIRST match (old data).

**Solution:** Use `re.findall()` and take the LAST match (current prompt):
```python
# WRONG:
match = re.search(r'\[(\d+)\]', screen)
sector = int(match.group(1))  # May get OLD sector

# RIGHT:
matches = re.findall(r'\[(\d+)\]', screen)
sector = int(matches[-1])  # Take LAST (current)
```

### Price Offer Response
**Problem:** TW2002 expects Enter at "Your offer [193]?" prompts, not "Y".

**Solution:** Send `"\r"` (Enter) for price prompts, not `"Y"`:
```python
if "your offer" in screen_lower:
    await send("\r")  # Accept default price
```

### Port Class Parsing
**Port class format:** "BBS" = Buys Fuel, Buys Organics, Sells Equipment
- Position: 0=Fuel Ore, 1=Organics, 2=Equipment
- B = Port Buys (we sell to them)
- S = Port Sells (we buy from them)

### Trading Strategy - Port Pairs
**Problem:** Trading at a single port always loses money. The bot buys commodities but can't sell them profitably at the same port.

**Solution:** Profitable trading requires COMPLEMENTARY PORT PAIRS:
1. Find Port A that SELLS commodity X (class has S in position)
2. Find Port B that BUYS commodity X (class has B in position)
3. Buy at Port A (low price), travel to Port B, sell (high price)

**Example profitable pairs:**
- Port class "SSB" (sells fuel, sells organics, buys equipment)
- Port class "BBS" (buys fuel, buys organics, sells equipment)
- Trade equipment: Buy at SSB (sells equipment), Sell at BBS (buys equipment)

**Strategy requirements:**
- Must track port classes when scanning
- Find adjacent or nearby complementary pairs
- Route: Port A (buy) -> travel -> Port B (sell) -> travel -> Port A

### Credits Parsing
**Location:** Credits shown on port screens as "You have X credits"
**Pattern:** `r'You have\s+([\d,]+)\s*credits'`

## Loop Detection

### Same Screen Stuck
**Problem:** Bot gets stuck seeing same screen repeatedly.

**Solution:** Track `last_screen` and count consecutive identical screens:
```python
if screen == last_screen:
    stuck_count += 1
    if stuck_count >= 3:
        break  # Exit loop
else:
    stuck_count = 0
last_screen = screen
```

### Max Transactions Safety
**Limit:** Don't do more than 6 transactions per port visit to avoid infinite loops.

## Navigation

### Warp Detection
**Problem:** After warping, need to detect if we actually moved.

**Solution:** Check sector before and after, accept any movement as success:
```python
current = state.sector
await warp_to(target)
new = state.sector
if new == target:
    return True  # Exact match
elif new and new != current:
    return True  # Moved somewhere (good enough)
else:
    return False  # Still at original
```

## Login Flow

### Character Creation Sequence
New characters go through these prompts in order:
1. `new_character_prompt` - "Would you like to start a new character?"
2. `password_prompt` - "Password?" (twice for confirmation)
3. `name_selection` - "(N)ew Name or (B)BS Name"
4. `ship_name_prompt` - "What do you want to name your ship?"
5. `name_confirm` - "Is this what you want?" (for ship name)
6. `planet_name_prompt` - "What do you want to name your home planet?" (if applicable)
7. `name_confirm` - "Is this what you want?" (for planet name)
8. Finally reaches `sector_command` or `planet_command`

### Pattern vs Actual Prompt
**Problem:** Pattern matcher finds prompts anywhere in screen buffer. The actual prompt is at the bottom.

**Solution:** Use `_get_actual_prompt()` to analyze last lines of screen:
```python
# Pattern match says: prompt.pause_simple
# But last line shows: "Use (N)ew Name or (B)BS Name [B] ?"
# actual_prompt = "name_selection"
# Use actual_prompt for decision making, not pattern_id
```

### Stale [Pause] in ANSI Art
**Problem:** ANSI graphics at top of screen may contain "[Pause]" text that persists in buffer.

**Solution:** Check if [Pause] is on the LAST LINE before treating as pause prompt:
```python
lines = screen.split('\n')
last_line = lines[-1].strip().lower() if lines else ""
if "[pause]" in last_line:
    # Real pause prompt
else:
    # Stale text in buffer, ignore
```

## Context Detection

### Sector Command Prompt
**Pattern:** `Command [TL=00:00:00]:[123] (?=Help)? :`
- Check for "command" and "?" in same line
- Indicates we're at the main sector command prompt

### Safe Contexts
- `sector_command` - Main game prompt
- `computer_menu` - Computer submenu
- `stardock` - At StarDock

## Sector Knowledge Caching

### mark_scanned() Must Include Discovered Data
**Problem:** Calling `mark_scanned(sector)` without warps/port info stores empty data. Next visit uses cached empty data.

**Solution:** Always pass discovered data to mark_scanned():
```python
# WRONG - stores empty cache entry
bot.mark_scanned(sector)

# RIGHT - stores full sector info
bot.sector_knowledge.mark_scanned(
    sector,
    warps=[123, 456],
    has_port=True,
    has_planet=False,
)
```

### Cache Invalidation
- Cache entries become stale over time
- Use `needs_scan(sector, rescan_hours)` to check if rescan needed
- Set `rescan_interval_hours` in config for periodic refresh

## Debugging Tips

1. Always print screen last line during debugging
2. Clear `loop_detection` dict before major operations
3. Use `recover()` to get back to safe state
4. Check `where_am_i()` after any uncertain action
