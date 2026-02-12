# TEDIT Reference Documentation

Trade Wars 2002 Sysop Editor v3.34b

## Connection Details

- **Host**: localhost
- **Port**: 2003 (admin port)
- **Password**: admin
- **Access Path**: Admin Menu → E (Run TEDIT) → Select Game (A or B)

---

## Login Flow (CRITICAL)

The admin login screen displays **two prompts simultaneously**:

```
Telnet connection detected.

Please enter your name (ENTER for none):
Enter admin password:
```

**The input order is sequential, not based on cursor position:**

1. First input goes to **name prompt** - send Enter (empty) for anonymous
2. Wait for the name to be processed
3. Second input goes to **password prompt** - send "admin" + Enter

### Working Login Sequence (expect/bash)

```bash
expect -c '
spawn telnet localhost 2003
expect "name (ENTER for none):"
send "\r"
expect "password:"
send "admin\r"
expect "Selection"
'
```

### BBSBot Issue

**IMPORTANT**: BBSBot has a bug where escape sequences like `\r` and `\n` are sent as literal characters instead of control codes. This causes the TWGS admin login to fail because:

1. `\r` is echoed as `\r` (two characters) instead of submitting input
2. The name prompt never receives a proper Enter keystroke
3. All input accumulates as "password" characters

**Workaround**: Use `expect` or standard telnet for TEDIT automation until BBSBot escape handling is fixed.

---

## Main Menu Structure

```
Trade Wars 2002 Sysop Editor v3.34b

Standard Editors                    Gold Editors
────────────────                    ────────────
A - Aliens Editor                   1 - Ship Editor
F - Ferrengi Editor                 2 - Planet Editor
G - General Editor One              3 - Alien Race Editor
H - General Editor Two              4 - Active Aliens Editor
I - General Editor Three
N - Planet Editor                   Maintenance
P - Port Editor                     ────────────
S - Sector Editor                   D - Remove derelict spacecraft
T - Corporation Editor              L - List current users
U - User Editor                     C - Add player to closed game
V - Ship Editor                     E - Repair Gold data
Y - Emulation Editor
Z - Game Timing Editor
B - Access Manager
R - Report Manager
Q - Quit editor
```

---

## General Editor One (G) - Core Settings

| Key | Setting | Default Value | Description |
|-----|---------|---------------|-------------|
| A | Turns per day | 250 | Daily turn allocation per player |
| B | Initial fighters | 30 | Starting fighters for new players |
| C | Initial credits | 300 | Starting credits for new players |
| D | Initial holds | 20 | Starting cargo holds for new players |
| E | Days until inactive deleted | 30 | Cleanup inactive players |
| G | Ferrengi regeneration % | 20% | Ferrengi respawn rate |
| H | Colonist reproduction rate | 750/day | Daily colonist growth |
| I | Daily log limit | 800 lines | Max log entries |
| J | StarShip Intrepid location | Sect 416 | Special ship location |
| K | StarShip Valiant location | Sect 1400 | Special ship location |
| L | StarShip Lexington location | Sect 2048 | Special ship location |
| M | Max planets per sector | 5 | Density limit |
| N | Max traders per corp | 5 | Corp size limit |
| O | Underground password | BEWARE OF KAL DURAK | Secret phrase |
| P | Age of game (days) | 0 | Game duration |
| R | Tournament mode | Off | Competition mode |

**Game Limits**: Max 500 players, 2222 sectors, 888 ports, 444 planets

---

## General Editor Two (H) - Advanced Settings

| Key | Setting | Default Value |
|-----|---------|---------------|
| 1 | Allow MBBS MegaRob Bug | No |
| 2 | Inactivity Timeout | 300 sec |
| 3 | Steal from Buy Port? | Yes |
| 4 | Planetary Trade Offers | 60% Normal |
| 5 | Highscores Update Mode | On demand |
| 6 | Clear Busts Every | 7 days |
| 7 | Port Regeneration Rate | 5%/day |
| 8 | Max Regen Per Visit | 100% |
| 0 | Interactive Sub-Prompts | No |
| N | Turn Accumulation Days | 1 day |
| Z | Alien Server Offline Mode | Active |
| X | Gold Editor Expert Mode | Disabled |
| [ | Closed Game | No |
| ] | Password Required | Yes |
| ; | Photon Disables Players | Yes |
| : | Maximum Course Length | 34 |
| / | Daily Game Time | Unlimited |
| # | Invincible Ferrengal | No |
| R | Alien Depreciation % | 100% |
| H | Ferrengi move chance | 1 in 20 |
| I | Aliens move chance | 1 in 20 |
| L | Allow Aliases? | Yes |
| M | Display Stardock? | Yes |
| O | FedSpace Ship Limit | 5 |
| P | Photon Wave Duration | 20 seconds |
| T | Max Bank Credits | 500,000 cr |
| U | Cloaking Fail Rate | 3% |
| V | NavHaz Dispersion | 3% |
| W | NewPlayer Planets | Yes |

---

## User List Format (L)

```
  # Trader Name              Sect Fghtrs Shlds ShipType             Trns Corp
  1 claude001                  15     30     0 Merchant Cruiser      246    0
```

Fields:
- **#**: Player ID
- **Trader Name**: Player name
- **Sect**: Current sector
- **Fghtrs**: Fighter count
- **Shlds**: Shield count
- **ShipType**: Ship type name
- **Trns**: Turns remaining
- **Corp**: Corporation ID (0 = no corp)

---

## User Editor (U)

The User Editor allows viewing and modifying individual player data.

### Navigation
1. Press `U` from main menu
2. Enter player ID or `?` to list players
3. View/edit player fields

### Editable Fields
| Key | Field |
|-----|-------|
| A | Player Name |
| B | Password |
| C | Sector Location |
| D | Fighters |
| E | Shields |
| F | Holds |
| G | Credits |
| H | Ship Type |
| I | Turns |
| J | Experience |
| K | Alignment |
| L | Corporation |

---

## Port Editor (P)

Manages trading ports across the universe.

### Port Classes
| Class | Type | Buys | Sells |
|-------|------|------|-------|
| 1 | BBS | Fuel, Organics | Equipment |
| 2 | BSB | Fuel, Equipment | Organics |
| 3 | SBB | Organics, Equipment | Fuel |
| 4 | SSB | Equipment | Fuel, Organics |
| 5 | SBS | Organics | Fuel, Equipment |
| 6 | BSS | Fuel | Organics, Equipment |
| 7 | SSS | - | All (StarDock) |
| 8 | BBB | All | - |

---

## Sector Editor (S)

Manages sector connections (warps) and sector properties.

### Editable Properties
- Warp connections (up to 6 per sector)
- Sector beacon message
- Navigation hazard level
- FedSpace designation

---

## Game Timing Editor (Z)

Controls game scheduling and timing.

| Key | Setting | Description |
|-----|---------|-------------|
| A | Game Start Time | When game becomes active |
| B | Game End Time | When game becomes inactive |
| C | Maintenance Time | Scheduled maintenance window |
| D | Turn Reset Time | When daily turns refresh |

---

## Common Navigation Keys

| Key | Action |
|-----|--------|
| Q | Quit/Back |
| ? | Help/List |
| Enter | Confirm/Default |
| Escape | Cancel |

---

## Data File Mappings

| TEDIT Section | Data File | Description |
|---------------|-----------|-------------|
| General Settings | game.dat, tedit.dat | Core game configuration |
| Users | user.dat | Player accounts and stats |
| Ports | port.dat | Trading port data |
| Sectors | sector.dat | Sector connections/properties |
| Planets | planet.dat | Planet ownership and resources |
| Corporations | corp.dat | Corporation membership |
| Ships | ship.dat | Ship type definitions |

---

## Tips for Automation

1. **Screen Detection**: TEDIT screens have consistent formatting:
   - Editor headers contain "Trade Wars 2002 Sysop Editor"
   - Menu prompts end with `[?]` or `[Q]`
   - Field lines follow `<KEY> Label: Value` format

2. **Input Types**:
   - Menu selections: single key (no Enter)
   - Numeric fields: digits followed by Enter
   - Text fields: string followed by Enter
   - Yes/No: Y or N (single key)

3. **Navigation Pattern**:
   ```
   Connect → Enter (name) → admin + Enter (password) → Admin Menu → E (TEDIT) → Select Game → Editor → Q (back)
   ```

4. **Recommended Automation Method**: Use `expect` for reliable TEDIT automation:
   ```bash
   expect -c '
   set timeout 10
   spawn telnet localhost 2003
   expect "name (ENTER for none):"
   send "\r"
   expect "password:"
   send "admin\r"
   expect "Selection"
   send "E"
   expect "Select game"
   send "A"
   expect "Editor"
   # ... your TEDIT commands here
   send "Q"
   expect eof
   '
   ```

5. **BBSBot Limitation**: BBSBot currently does not properly convert `\r` and `\n` escape sequences to control characters. Use `expect` or native telnet until this is fixed.

6. **Keepalive Consideration**: If using BBSBot, disable keepalive (`bbs_keepalive` with `interval_s=0`) to prevent `\r` interference during TEDIT sessions.
