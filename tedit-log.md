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
