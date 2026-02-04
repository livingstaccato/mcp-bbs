# TEDIT Exploration Log

## Scope
- Target: TradeWars 2002 TWGS Admin (TEDIT) on localhost:2003
- Slot: A / My Game
- Auto-learn: enabled

## Storage
- Screens: /Users/tim/Library/Application Support/mcp-bbs/shared/screens/
- Prompts: /Users/tim/Library/Application Support/mcp-bbs/games/tw2002/prompts.json
- Rules: /Users/tim/Library/Application Support/mcp-bbs/games/tw2002/rules.json

## Path
- TWGS Admin → `E` Run TEDIT → `A` My Game → TEDIT main menu

## TEDIT Main Menu (level 1)
- `A` Aliens Editor (standard) → disabled notice (BIGBANG only)
- `F` Ferrengi Editor (standard) → disabled notice (BIGBANG only)
- `G` General Editor One
- `H` General Editor Two
- `I` General Editor Three
- `N` Planet Editor (standard ID prompt)
- `P` Port Editor (standard ID prompt)
- `S` Sector Editor (standard ID prompt)
- `T` Corporation Editor (standard ID prompt)
- `U` User Editor (standard ID prompt)
- `V` Ship Editor (standard ID prompt)
- `L` List current users (paged)
- `C` Add player to closed game (requires Closed Game; warning)
- `D` Remove derelict spacecraft (confirm prompt)
- `E` Repair Gold data (confirm prompt)
- `Y` Emulation Editor
- `Z` Game Timing Editor
- `B` Access Manager
- `R` Report Manager
- Gold Editors: `1` Ship Editor, `2` Planet Editor, `3` Alien Race Editor, `4` Active Aliens Editor

## Gold Editors (level 2)
### Gold Ship Editor
- Tabs: `1` Max Values, `2` Initial Values, `3` Settings, `4` Costs
- Actions: `?` Help, `Q` Quit, `*` Abort, `^` Commit, `+` New class, `!` Delete class, `@` Reset, `G` Get Class, `>` Next Class
- Class selector list present

### Gold Planet Editor
- Tabs: `1` Max Values, `2` Initial Values, `3` Citadel Values
- Actions: `?` Help, `Q` Quit, `*` Abort, `^` Commit, `+` New class, `!` Delete class, `@` Reset, `G` Get Class, `>` Next Class

### Gold Alien Race Editor
- Tabs: `1` Settings, `2` Behaviors, `3` Spawning Profile, `4` Resources
- Actions: `?` Help, `Q` Quit, `*` Abort, `^` Commit, `+` New race, `!` Delete race, `@` Reset, `G` Get Race, `>` Next Race

### Gold Active Aliens Editor
- Tabs: `1` Traits, `2` Ship, `3` Inventory
- Actions: `?` Help, `Q` Quit, `A` Get Alien, `N` Next Alien, `G` Get Race, `>` Next Race

## Standard Editors (level 2 sample screens)
- Planet (ID 1): name, class, location, owner, colonists, regen, prompt `(?) (<>) (X=Exit)`
- Port (ID 1): name, class, sector, firepower, prompt `(?) (<>) (X=Exit)`
- Sector (ID 1): nebulae, beacon, warps, port/fighters/mines/planets/traders/aliens, prompt `(?) (<>) (X=Exit)`
- Corp (ID 1 empty): initialize corp, prompt `(?) (<>) (X=Exit)`
- User (ID 4): name/BBS/password/ship/turns/credits/etc., prompt `(?) (<>) (X=Exit)`
- Ship (ID 4): ship details/inventory/scanners/locks, prompt `(?) (<>) (X=Exit)`

## Editors (level 2)
### General Editor One
- Global game settings (turns/day, initial credits/holds/fighters, inactive delete days, max players, ship locations, etc.)

### General Editor Two
- Access/behavior toggles (aliases, stardock, photon settings, port regen, etc.)

### General Editor Three
- Pricing/limits/combat options

### Emulation Editor
- Input/Output bandwidth, latency, reset defaults, help

### Game Timing Editor
- Delay settings for ship/planet actions, help and reset

### Access Manager
- `+` Add access mode (mode/time prompts)
- `-` Remove access mode (select entry, confirm)
- `E` Edit access mode (select entry, set new mode)
- `I` Insert access mode (mode/time prompts)
- `@` Reset access
- `!` Cancel changes

### Report Manager
- High score mode/type, rankings mode/type, entry/game log blackout, port report delay

## Changes Made (persistent)
1. **General Editor One**: Turns per day changed from `65520` → `500`.
2. **Player created**: User #7 initialized.
   - BBS Name: `Alpha`
   - Password: `alpha`
3. **Player created + deleted**: User #8 initialized then deleted.
   - BBS Name: `Beta`
   - Password: `beta`
4. **Corp created**: Corp #1 created with CEO `Tertiary`.
   - Name: `GammaCorp`
   - Password: `GAMMA`
5. **Corp created + deleted**: Corp #2 created with CEO `ThePlayer`, then deleted.
   - Name: `DeltaCorp`
   - Password: `DELTAPW`

## Notes
- Closed Game toggle in General Editor Two (`[`) did not flip on initial attempts.
- `C` Add player to closed game still warns unless Closed Game enabled.


## Additional Changes (persistent)
6. **Player created**: User #9 initialized.
   - BBS Name: `Gamma`
   - Password: `gamma`
7. **Planet edit**: Planet #1 colonists on hand set to `50000`.
   - Path: TEDIT → `N` → `1` → `B` → `50000`
8. **Port edit**: Port #1 firepower set to `75%`.
   - Path: TEDIT → `P` → `1` → `L` → `75`
9. **Corp created**: Corp #3 created with CEO `ThePlayer`.
   - Name: `OmegaCorp`
   - Password: `OMEGA`

## Closed Game Attempts
- Tried toggling `[` (Closed Game) multiple times in General Editor Two; no visible change. Possibly requires different input or another mode.

## Addon
- Added `src/mcp_bbs/addons/tedit.py` to extract `<key> Label : Value` fields and prompts.
- Wired into `session_manager.py` for namespace `tedit`.

## Additional Changes (persistent)
10. **General Editor One bulk edits**:
   - Sysop Name: `SysopX`
   - Turns/day: `600`
   - Initial fighters: `40`
   - Initial credits: `2000`
   - Initial holds: `30`
   - Inactive delete days: `20`
   - Ferrengi regen %: `10` (of max 600)
   - Terran colonist reproduction: `2000`/day
   - Daily log limit: `900`
   - StarShip Intrepid location: `100`
   - StarShip Valiant location: `200`
   - StarShip Lexington location: `300`
   - Max planets/sector: `6`
   - Max traders/corp: `8`
   - Underground password phrase: `NEWPASS`
   - Age of game (days): `20`
   - Tournament Mode: `On`
   - Days to allow entry: `10`
   - Lock-out Mode: `On`
   - Max Pod/Death Count: `3`

## Incremental KV Export
- Started incremental JSONL export: `tedit-kv.jsonl`
- Entries will be appended as field prompts are triggered.
- 2026-02-04: Aliens Editor (Standard) shows message: "Internal Alien Traders are disabled. They can only be enabled during BIGBANG!" then [Pause].
- 2026-02-04: Ferrengi Editor (Standard) shows message: "Internal Ferrengi are disabled. They can only be enabled during BIGBANG!" then [Pause].
- 2026-02-04: Visited General Editor One; captured current values into tedit-kv.jsonl (sysop name AUnknown, turns/day 65520, etc.).
- 2026-02-04: Visited General Editor Two; captured current values into tedit-kv.jsonl. Some fields (Ferrengi HomeBase, Stardock/Rylos/Alpha Centauri sectors) were not displayed on-screen and logged as null for now.
- 2026-02-04: Visited General Editor Three; captured current values into tedit-kv.jsonl (item costs, radiation lifetime, combat settings, etc.).
- 2026-02-04: Planet Editor (Standard) prompts for Planet ID (0=Abort, range 0-200).
- 2026-02-04: Port Editor (Standard) prompts for Port ID (0=Abort, range 0-400).
- 2026-02-04: Sector Editor (Standard) prompts for Sector number (0=Abort, range 0-1,000).
- 2026-02-04: Corporation Editor (Standard) prompts for Corporation ID (0=Abort, range 0-50).
- 2026-02-04: User Editor (Standard) prompts for User ID (Name or Number, <CR>=Abort).
- 2026-02-04: Ship Editor (Standard) prompts for Ship ID (0=Abort, range 0-800).
- 2026-02-04: Emulation Editor values captured (input/output bandwidth 1 Mps Broadband, latency 150 ms).
- 2026-02-04: Game Timing Editor values captured (delay settings list) into tedit-kv.jsonl.
- 2026-02-04: Access Manager screen captured (access_modes: "All day : Multiplayer Access").
- 2026-02-04: Report Manager screen captured (modes, blackout settings, report types).
- 2026-02-04: Remove derelict spacecraft: confirmation prompt seen (answered N).
- 2026-02-04: List current users output paged; mostly "Unused record" entries; returned to main menu after multiple [Pause] screens.
- 2026-02-04: Add player to closed game: message "This isn't a closed game. Enable \"Closed Game\" in General Editor Two." then [Pause].
- 2026-02-04: Repair Gold data confirmation prompt seen (answered N).
- 2026-02-04: Gold Ship Editor opened (class Escape Pod, make Standard Manufacture, max values tab). Captured to tedit-kv.jsonl.
- 2026-02-04: Gold Planet Editor opened (Earth Type class, max values tab). Captured to tedit-kv.jsonl.
- 2026-02-04: Alien Race Editor opened (Alien Traders race, settings tab). Captured to tedit-kv.jsonl.
- 2026-02-04: Active Aliens Editor opened (Alien Traders, Alien #1 Cuni Sheushes, traits tab). Captured to tedit-kv.jsonl.
- 2026-02-04: Gold Ship/Planet/Alien Race tabs 2-6 and Active Aliens tabs 2-3 captured to tedit-kv.jsonl (initial values, settings, costs, misc, behaviors, spawning profile, resources, rankings, etc.).
- 2026-02-04: Sector 1: set Nebulae field to blank via <Z> in Sector Editor.
- 2026-02-04: Sector 1: marker beacon prompt seen; set beacon to "FedSpace, FedLaw Enforced".
- 2026-02-04: Corp #3 initialize failed; prompt for CEO name and trader; "Unknown Trader!" then "Corp must have a valid CEO!".
- 2026-02-04: Corporation Editor input appears to jump to Gold Ship Editor after entering ID (1) at prompt; unable to reach corp detail screen from this prompt (possible desync/bug).
- 2026-02-04: Access Manager edit flow prompts captured (select entry, access mode, time). Left defaults unchanged.
- 2026-02-04: Planet Editor (Standard) ID 1 captured (Terra, sector 1, Federation, 50,152 colonists on hand).
- 2026-02-04: Port Editor (Standard) ID 1 captured (Corp, class 0, sector 1, firepower 10%).
- 2026-02-04: Sector Editor (Standard) ID 1 captured; edited Nebulae to blank; beacon seen as None; warp F shows 0.
- 2026-02-04: User Editor (Standard) captured user #7 (Alpha/alpha) and #9 (Gamma/gamma) records.
- 2026-02-04: Ship Editor (Standard) ID 1 captured (tim2 ship details).
- 2026-02-04: Report Manager prompts captured for rankings mode and game log blackout; high score mode/entry blackout/port report delay did not prompt (possibly due to interactive subprompt setting). 
- 2026-02-04: Access Manager add (+) flow: entered mode=1 at 01:00 AM, but list did not display new entry afterward (possible desync). Insert (I) key unexpectedly dropped into General Editor Three screen.
- 2026-02-04: Planet Editor selection (N -> Planet ID 1) intermittently drops into Gold Ship Editor (Escape Pod) instead of planet detail screen; possible desync/bug.
- 2026-02-04: Port Editor (Standard) ID 1: attempting <L> to edit firepower unexpectedly triggered "List current users" paging; no port change confirmed.
- 2026-02-04: General Editor Two: Interactive Sub-Prompts prompt shown; answered Y, but value still shows No afterward. Closed Game toggle ([) did not change value.
- 2026-02-04: General Editor One Sysop name set to "TimSysop".
- 2026-02-04: General Editor Three: Beacon cost changed from 25 to 30.
- 2026-02-04: Port Editor selection (P -> Port ID 1) intermittently drops into Gold Ship Editor (Escape Pod) instead of port detail screen; possible desync/bug.
- 2026-02-04: Access Manager remove (-) prompts captured; declined removal. Insert (I) again unexpectedly jumped to General Editor Three (desync).
- 2026-02-04: General Editor Three prompts captured for Port Report Delay, Startup Asset Dropoff, Multiple Photon Fire, Who's Online. Beacon cost set to 30.
- 2026-02-04: Game Timing Editor: Ship Move/Attack delay mode prompt captured (kept default CONSTANT).
- 2026-02-04: Emulation Editor latency prompt captured (kept 150 ms).
- 2026-02-04: Planet Editor (Standard) ID 2 captured (Ferrengal details, production, treasury, citadel project). 
- 2026-02-04: Port Editor selection (P -> Port ID 2) jumped into Gold Planet Editor (Earth Type) instead of port detail screen; desync.
- 2026-02-04: Corporation Editor ID 1 selection returned to main menu (no corp detail screen). Likely desync/bug persists.
- 2026-02-04: Ship Editor ID 2 selection did not open ship detail (desync); screen returned to partial main menu.
- 2026-02-04: Screen saving disabled after disk full error; deleted old screen captures from /Users/tim/Library/Application Support/mcp-bbs/shared/screens.
- 2026-02-04: Maintenance: Remove derelict spacecraft confirmed (Y).
- 2026-02-04: User Editor selection (ID 7) returned to main menu without user detail screen (desync).
- 2026-02-04: Screen saving disabled again after disk-full error when reconnecting; cleared /tmp and screen files to recover space.
- 2026-02-04: Sector Editor selection (ID 3) returned to main menu without sector detail screen (desync).
- 2026-02-04: User Editor selection (ID 7) still returning to main menu (desync).
- 2026-02-04: Planet Editor selection (ID 3) returned to main menu without planet detail screen (desync).
- 2026-02-04: Sector Editor selection (ID 4) jumped into Active Alien Editor (desync).
- 2026-02-04: Alien Race Editor Ferrengi: captured settings/behaviors/spawning/resources and sample available ships (day 0).
- 2026-02-04: Active Aliens Editor: Ferrengi race (ID 1) alien #1 Darog captured (traits, ship, inventory).
- 2026-02-04: Active Aliens Editor: Ferrengi alien #2 Serpor captured (traits, ship, inventory).
- 2026-02-04: Active Aliens Editor: Ferrengi alien #3 Seret captured (traits, ship, inventory).
- 2026-02-04: Active Aliens Editor: Ferrengi alien #4 Larton captured (traits, ship, inventory).
- 2026-02-04: Active Aliens Editor: Ferrengi aliens #5-#15 shown as NOT SPAWNED; recorded in tedit-kv.jsonl.
- 2026-02-04: Active Aliens Editor: Ferrengi aliens #16-#25 shown as NOT SPAWNED; recorded in tedit-kv.jsonl.
- 2026-02-04: Active Aliens Editor: Ferrengi aliens #26-#30 shown as NOT SPAWNED; recorded in tedit-kv.jsonl.
- 2026-02-04: Active Aliens Editor: Ferrengi aliens #31-#35 shown as NOT SPAWNED; recorded in tedit-kv.jsonl.
- 2026-02-04: Fresh TEDIT session: Planet Editor ID 1 still returns to main menu (desync persists).
- 2026-02-04: Fresh TEDIT session: Port Editor ID 1 still jumps to Gold Ship Editor (desync persists).
[2026-02-04] Sector Editor: entered 3 -> returned to main menu (no sector details). Desync persists.
[2026-02-04] User Editor: entered user id 1 -> jumped to Gold Ship Editor class screen (desync).
[2026-02-04] Port Editor: entered port id 1 -> jumped to Gold Ship Editor class screen (desync).
[2026-02-04] Active Aliens: Ferrengi #36-#40 all NOT SPAWNED.
[2026-02-04] Closed Game set to Yes. Added closed-game users: TESTPLAYER1 (pw testpw1), TESTPLAYER2 (pw testpw2; confirmed prompt).
[2026-02-04] Corp init: Corp #2 created with CEO tim2, name TestCorpA, password CORPPW; Corp #3 created with CEO ThePlayer, name TestCorpB, password CORPPW2. Deleted corp #2 via ! (confirmed Y).
[2026-02-04] Access Manager: Edit entry 0 (All day Multiplayer Access) viewed; left mode/time unchanged (0, 12:00 AM). Report Manager: High Score Mode prompt viewed, left at On demand.
