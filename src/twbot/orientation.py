"""Orientation system for TW2002 bot.

Three-layer approach:
1. Safety - Reach a known stable state
2. Context - Gather comprehensive game state
3. Navigation - Plan routes using knowledge

Usage:
    state = await bot.orient()  # Returns GameState
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from time import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .bot import TradingBot


# =============================================================================
# GameState - Complete snapshot after orientation
# =============================================================================

@dataclass
class GameState:
    """Complete snapshot of game state after orientation."""

    # Context - where are we in the game UI?
    context: str  # "sector_command" | "planet_command" | "citadel_command" |
                  # "port_menu" | "combat" | "menu" | "unknown"
    sector: int | None = None

    # Resources
    credits: int | None = None
    turns_left: int | None = None

    # Ship status
    holds_total: int | None = None
    holds_free: int | None = None
    fighters: int | None = None
    shields: int | None = None
    ship_type: str | None = None

    # Player status
    alignment: int | None = None
    experience: int | None = None
    corp_id: int | None = None
    player_name: str | None = None

    # Sector info (from current view)
    has_port: bool = False
    port_class: str | None = None  # "BBS", "SSB", "SBB", etc.
    has_planet: bool = False
    planet_names: list[str] = field(default_factory=list)
    warps: list[int] = field(default_factory=list)
    traders_present: list[str] = field(default_factory=list)
    hostile_fighters: int = 0

    # Meta
    raw_screen: str = ""
    prompt_id: str | None = None
    timestamp: float = field(default_factory=time)

    def is_safe(self) -> bool:
        """Are we at a stable command prompt?"""
        return self.context in ("sector_command", "planet_command", "citadel_command")

    def can_warp(self) -> bool:
        """Can we leave this sector?"""
        return self.context == "sector_command" and len(self.warps) > 0

    def summary(self) -> str:
        """One-line summary for logging."""
        loc = f"Sector {self.sector}" if self.sector else "Unknown"
        return f"[{self.context}] {loc} | Credits: {self.credits} | Turns: {self.turns_left}"


# =============================================================================
# OrientationError - Raised when we can't establish safe state
# =============================================================================

class OrientationError(Exception):
    """Raised when orientation fails to establish safe state."""

    def __init__(self, message: str, screen: str, attempts: int):
        super().__init__(message)
        self.screen = screen
        self.attempts = attempts


# =============================================================================
# SectorKnowledge - Layered knowledge storage
# =============================================================================

@dataclass
class SectorInfo:
    """What we know about a sector."""
    warps: list[int] = field(default_factory=list)
    has_port: bool = False
    port_class: str | None = None
    has_planet: bool = False
    planet_names: list[str] = field(default_factory=list)
    last_visited: float | None = None
    last_scanned: float | None = None  # When D command was last run here


class SectorKnowledge:
    """Layered sector knowledge: discovery -> cache -> twerk (optional)."""

    def __init__(
        self,
        knowledge_dir: Path | None = None,
        character_name: str = "unknown",
        twerk_data_dir: Path | None = None,
    ):
        self.knowledge_dir = knowledge_dir
        self.character_name = character_name
        self.twerk_data_dir = twerk_data_dir

        # In-memory discovered knowledge
        self._sectors: dict[int, SectorInfo] = {}

        # Load cached knowledge if available
        if knowledge_dir:
            self._load_cache()

        # Load twerk data if available
        self._twerk_sectors: dict[int, list[int]] | None = None
        if twerk_data_dir:
            self._load_twerk()

    def _cache_path(self) -> Path | None:
        """Path to character's knowledge cache file."""
        if not self.knowledge_dir:
            return None
        return self.knowledge_dir / f"{self.character_name}_sectors.json"

    def _load_cache(self) -> None:
        """Load cached knowledge from disk."""
        path = self._cache_path()
        if not path or not path.exists():
            return

        try:
            data = json.loads(path.read_text())
            for sector_str, info in data.get("sectors", {}).items():
                sector = int(sector_str)
                self._sectors[sector] = SectorInfo(
                    warps=info.get("warps", []),
                    has_port=info.get("has_port", False),
                    port_class=info.get("port_class"),
                    has_planet=info.get("has_planet", False),
                    planet_names=info.get("planet_names", []),
                    last_visited=info.get("last_visited"),
                    last_scanned=info.get("last_scanned"),
                )
        except (json.JSONDecodeError, KeyError) as e:
            print(f"Warning: Failed to load sector cache: {e}")

    def _save_cache(self) -> None:
        """Save knowledge to disk."""
        path = self._cache_path()
        if not path:
            return

        path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "sectors": {
                str(sector): {
                    "warps": info.warps,
                    "has_port": info.has_port,
                    "port_class": info.port_class,
                    "has_planet": info.has_planet,
                    "planet_names": info.planet_names,
                    "last_visited": info.last_visited,
                    "last_scanned": info.last_scanned,
                }
                for sector, info in self._sectors.items()
            },
            "last_updated": time(),
        }

        path.write_text(json.dumps(data, indent=2))

    def _load_twerk(self) -> None:
        """Load sector data from twerk if available."""
        if not self.twerk_data_dir:
            return

        try:
            from twerk.parsers import parse_sectors

            sectors_path = self.twerk_data_dir / "twsect.dat"
            if sectors_path.exists():
                sectors = parse_sectors(sectors_path)
                self._twerk_sectors = {
                    s.sector_id: list(s.warps) for s in sectors if s.warps
                }
        except ImportError:
            pass  # twerk not available
        except Exception as e:
            print(f"Warning: Failed to load twerk sector data: {e}")

    def get_warps(self, sector: int) -> list[int] | None:
        """Get known warps from a sector. Returns None if unknown."""
        # Priority 1: Discovery (most recent/accurate)
        if sector in self._sectors and self._sectors[sector].warps:
            return self._sectors[sector].warps

        # Priority 2: Twerk (if available)
        if self._twerk_sectors and sector in self._twerk_sectors:
            return self._twerk_sectors[sector]

        return None

    def get_sector_info(self, sector: int) -> SectorInfo | None:
        """Get full sector info if known."""
        return self._sectors.get(sector)

    def record_observation(self, state: GameState) -> None:
        """Record what we observed in current sector."""
        if state.sector is None:
            return

        sector = state.sector
        if sector not in self._sectors:
            self._sectors[sector] = SectorInfo()

        info = self._sectors[sector]
        info.warps = state.warps
        info.has_port = state.has_port
        info.port_class = state.port_class
        info.has_planet = state.has_planet
        info.planet_names = state.planet_names
        info.last_visited = time()

        # Persist to disk
        self._save_cache()

    def find_path(self, start: int, end: int, max_hops: int = 100) -> list[int] | None:
        """BFS pathfinding using known sectors."""
        if start == end:
            return [start]

        visited = {start}
        queue = [(start, [start])]

        while queue:
            current, path = queue.pop(0)

            if len(path) > max_hops:
                continue

            warps = self.get_warps(current)
            if warps is None:
                continue

            for next_sector in warps:
                if next_sector == end:
                    return path + [next_sector]

                if next_sector not in visited:
                    visited.add(next_sector)
                    queue.append((next_sector, path + [next_sector]))

        return None  # No path found with current knowledge

    def known_sector_count(self) -> int:
        """How many sectors do we have warp data for?"""
        count = len(self._sectors)
        if self._twerk_sectors:
            count = max(count, len(self._twerk_sectors))
        return count

    def needs_scan(self, sector: int, rescan_hours: float = 0) -> bool:
        """Check if a sector needs to be scanned with D command.

        Args:
            sector: Sector to check
            rescan_hours: Hours after which to rescan (0 = never rescan)

        Returns:
            True if sector should be scanned
        """
        info = self._sectors.get(sector)
        if info is None or info.last_scanned is None:
            return True

        if rescan_hours <= 0:
            return False

        hours_since = (time() - info.last_scanned) / 3600
        return hours_since >= rescan_hours

    def mark_scanned(self, sector: int) -> None:
        """Mark a sector as having been scanned with D command.

        Args:
            sector: Sector that was scanned
        """
        if sector not in self._sectors:
            self._sectors[sector] = SectorInfo()

        self._sectors[sector].last_scanned = time()
        self._save_cache()

    def get_scanned_sectors(self) -> set[int]:
        """Get all sectors that have been scanned.

        Returns:
            Set of sector numbers that have been scanned
        """
        return {
            sector for sector, info in self._sectors.items()
            if info.last_scanned is not None
        }


# =============================================================================
# Context Detection - Identify current prompt/state
# =============================================================================

def _detect_context(screen: str) -> str:
    """Detect game context from screen content.

    Returns one of the CONTEXT constants below. This is the core "where am I"
    logic that powers fail-safe recovery.

    SAFE STATES (can issue commands):
        sector_command  - At sector prompt, ready for navigation/actions
        planet_command  - On planet surface, can interact
        citadel_command - At citadel prompt
        stardock        - At StarDock facility

    ACTION STATES (mid-transaction):
        port_menu       - At port trading menu
        port_trading    - In buy/sell transaction
        bank            - At bank interface
        ship_shop       - At ship purchasing
        hardware_shop   - Buying ship upgrades
        combat          - In combat situation
        message_system  - Reading/writing messages

    TRANSITION STATES (need to press key/continue):
        pause           - [Pause] screen
        more            - Pagination prompt
        confirm         - Y/N confirmation pending

    NAVIGATION STATES:
        warping         - Moving between sectors
        autopilot       - Autopilot engaged

    OTHER:
        login           - At login prompts
        menu            - Generic menu
        death           - Ship destroyed
        unknown         - Can't determine
    """
    lines = [l.strip() for l in screen.split('\n') if l.strip()]
    if not lines:
        return "unknown"

    last_line = lines[-1].lower()
    last_lines = '\n'.join(lines[-5:]).lower()
    full_screen = screen.lower()

    # === DEATH STATE (highest priority - need to recognize immediately) ===
    if "ship destroyed" in full_screen or "been killed" in full_screen:
        return "death"
    if "start over from scratch" in full_screen:
        return "death"

    # === SAFE COMMAND STATES ===
    # These are stable states where we can issue commands

    # Sector command prompt: "Command [TL=00:00:00]:[123] (?=Help)? :"
    # Computer command prompt: "Computer command [TL=00:00:00]:[123] (?=Help)?"
    if "command" in last_line and "?" in last_line:
        if "computer" in last_line:
            return "computer_menu"
        if "planet" in last_line:
            return "planet_command"
        if "citadel" in last_line:
            return "citadel_command"
        return "sector_command"

    # Alternative sector command detection - look for the prompt format pattern
    # e.g., "[123] (?=Help)?" or just "[123]" with help text
    if re.search(r'\[\d+\]\s*\(\?', last_line):
        return "sector_command"
    # Also check for "Command" at start of line with sector number
    if re.search(r'command.*\[\d+\]', last_line, re.IGNORECASE):
        return "sector_command"

    # StarDock - special facility
    if "stardock" in last_lines and "enter your choice" in last_line:
        return "stardock"

    # === COMBAT STATE ===
    if "attack" in last_lines and ("fighters" in last_lines or "shields" in last_lines):
        return "combat"
    if "combat" in last_lines and ("fire" in last_lines or "retreat" in last_lines):
        return "combat"

    # === PORT STATES ===
    # Port menu: "Enter your choice [T] ?"
    if "[t]" in last_line and "?" in last_line:
        return "port_menu"
    if "enter your choice" in last_line and "port" in last_lines:
        return "port_menu"

    # Port trading: buying/selling commodities
    if "how many" in last_line and "units" in last_line:
        return "port_trading"
    if "offer" in last_line and "price" in last_line:
        return "port_trading"
    if "fuel ore" in last_lines or "organics" in last_lines or "equipment" in last_lines:
        if "buy" in last_lines or "sell" in last_lines:
            return "port_trading"

    # === FINANCIAL STATES ===
    # Bank
    if "bank" in last_lines and ("deposit" in last_lines or "withdraw" in last_lines):
        return "bank"

    # Ship shop
    if "ship" in last_lines and "purchase" in last_lines:
        return "ship_shop"

    # Hardware/upgrades
    if "hardware" in last_lines and "buy" in last_lines:
        return "hardware_shop"

    # === MESSAGE SYSTEM ===
    if "message" in last_lines and ("read" in last_lines or "send" in last_lines):
        return "message_system"
    if "subspace" in last_lines and "message" in last_lines:
        return "message_system"

    # === COMPUTER / CIM ===
    if "computer" in last_lines and ("navigation" in last_lines or "displays" in last_lines or "miscellaneous" in last_lines):
        return "computer_menu"
    if "cim" in last_lines or "interrogation" in last_lines:
        return "cim_mode"
    if "course plotter" in last_lines or "plot course" in last_lines:
        return "course_plotter"
    if "port report" in last_lines and "sector" in last_lines:
        return "port_report"

    # === TAVERN ===
    if "tavern" in last_lines or "lost trader" in last_lines:
        return "tavern"
    if "grimy" in last_lines and ("trader" in last_lines or "man" in last_lines):
        return "grimy_trader"
    if "tri-cron" in last_lines or "tricron" in last_lines:
        return "gambling"
    if "eavesdrop" in last_lines or "corner table" in last_lines:
        return "eavesdrop"

    # === UNDERGROUND ===
    if "underground" in last_lines and ("password" in last_lines or "secret" in last_lines):
        return "underground"

    # === NAVIGATION STATES ===
    # Warping - only check last line to avoid false positives from scrollback
    # The actual warp message appears on the current line when warping
    if "warping to sector" in last_line:
        return "warping"
    if "autopilot" in last_lines and "engaged" in last_lines:
        return "autopilot"
    if "stop in this sector" in last_line:
        return "autopilot"

    # === TRANSITION STATES ===
    # Pause screens
    if "[pause]" in last_line or "[any key]" in last_line:
        return "pause"
    if "press" in last_line and ("key" in last_line or "enter" in last_line):
        return "pause"

    # Pagination
    if "-- more --" in last_line or "[more]" in last_line or "<more>" in last_line:
        return "more"

    # Y/N confirmation
    if "(y/n)" in last_line or "[y/n]" in last_line:
        return "confirm"

    # === LOGIN STATES ===
    if "enter your name" in last_line or "password:" in last_line:
        return "login"
    if "create new character" in last_lines:
        return "login"

    # === GENERIC MENU ===
    if "selection" in last_line or "enter your choice" in last_line:
        return "menu"
    if "?" in last_line and ":" in last_line:
        return "menu"

    return "unknown"


# Context categories for quick checks
SAFE_CONTEXTS = {"sector_command", "planet_command", "citadel_command", "stardock"}
ACTION_CONTEXTS = {
    "port_menu", "port_trading", "bank", "ship_shop", "hardware_shop",
    "combat", "message_system", "tavern", "grimy_trader", "gambling",
    "computer_menu", "cim_mode", "course_plotter", "underground"
}
TRANSITION_CONTEXTS = {"pause", "more", "confirm", "port_report", "eavesdrop"}
NAVIGATION_CONTEXTS = {"warping", "autopilot"}
DANGER_CONTEXTS = {"combat", "death"}
INFO_CONTEXTS = {"computer_menu", "cim_mode", "port_report", "course_plotter"}


# =============================================================================
# Fast "Where Am I?" - Quick state check without full orientation
# =============================================================================

@dataclass
class QuickState:
    """Minimal state info from quick check."""
    context: str
    sector: int | None = None
    prompt_id: str | None = None
    screen: str = ""
    is_safe: bool = False
    is_danger: bool = False
    suggested_action: str | None = None

    def __str__(self) -> str:
        loc = f"Sector {self.sector}" if self.sector else "?"
        return f"[{self.context}] {loc}"


async def where_am_i(bot: "TradingBot", timeout_ms: int = 500) -> QuickState:
    """Fast state check - quickly determine where we are.

    This is the FAST "where am I" function. It reads the screen once,
    detects context, and returns immediately. Use this when you need
    to quickly check state without full orientation.

    For full state gathering, use orient() instead.

    Args:
        bot: TradingBot instance
        timeout_ms: Max time to wait for screen data

    Returns:
        QuickState with context and basic info
    """
    try:
        result = await bot.session.read(timeout_ms=timeout_ms, max_bytes=8192)
        screen = result.get("screen", "")
        prompt_detected = result.get("prompt_detected", {})
        prompt_id = prompt_detected.get("prompt_id", "")
    except Exception:
        return QuickState(context="unknown", suggested_action="reconnect")

    # Detect context
    context = _detect_context(screen)

    # Extract sector from screen if possible
    sector = None
    # Try prompt format: [123] - use findall and take LAST match
    # because screen buffer may contain old sector info at top
    sector_matches = re.findall(r'\[(\d+)\]\s*\(\?', screen)
    if sector_matches:
        sector = int(sector_matches[-1])  # Take LAST match (current prompt)
    else:
        # Try "Sector 123" format - also take last match
        sector_matches = re.findall(r'sector\s+(\d+)', screen, re.IGNORECASE)
        if sector_matches:
            sector = int(sector_matches[-1])

    # Determine safety and suggested action
    is_safe = context in SAFE_CONTEXTS
    is_danger = context in DANGER_CONTEXTS

    # Suggest action based on context
    suggested_action = None
    if context == "pause":
        suggested_action = "send_space"
    elif context == "more":
        suggested_action = "send_space"
    elif context == "confirm":
        suggested_action = "send_n_or_check"
    elif context == "death":
        suggested_action = "handle_death"
    elif context == "combat":
        suggested_action = "handle_combat"
    elif context == "unknown":
        suggested_action = "try_orient"
    elif context in ("port_menu", "menu"):
        suggested_action = "send_q_to_exit"

    return QuickState(
        context=context,
        sector=sector,
        prompt_id=prompt_id,
        screen=screen,
        is_safe=is_safe,
        is_danger=is_danger,
        suggested_action=suggested_action,
    )


async def recover_to_safe_state(
    bot: "TradingBot",
    max_attempts: int = 20,
) -> QuickState:
    """Attempt to recover to a safe state from any situation.

    This is the fail-safe recovery function. It will try various
    escape sequences to get back to a command prompt.

    Args:
        bot: TradingBot instance
        max_attempts: Maximum recovery attempts

    Returns:
        QuickState after recovery

    Raises:
        OrientationError if recovery fails
    """
    # Recovery key sequences - avoid Enter which can trigger warps
    recovery_sequences = [
        # Gentle escapes - NO ENTER to avoid triggering warps
        (" ", 0.3),      # Space for pause/more
        ("Q", 0.3),      # Q to exit menus
        ("N", 0.3),      # N for Y/N prompts
        ("\x1b", 0.3),   # Escape key
        # More aggressive
        ("Q", 0.3),      # Q again
        (" ", 0.3),      # Space
        ("\x1b", 0.5),   # Escape
        ("Q", 0.5),      # Q with longer wait
        # Really aggressive - still no Enter
        (" ", 0.5),
        ("\x1b", 0.5),   # Multiple escapes
        ("\x1b", 0.3),
    ]

    print(f"\n[Recovery] Attempting to recover to safe state...")

    last_state = None
    attempt = 0

    while attempt < max_attempts:
        # Check current state
        state = await where_am_i(bot)
        last_state = state

        print(f"  [{attempt}] {state.context} (sector: {state.sector})")

        # Success!
        if state.is_safe:
            print(f"  [Recovery] ✓ Reached safe state: {state.context}")
            # Clear loop detection counter after successful recovery
            bot.loop_detection.clear()
            return state

        # Handle specific contexts
        if state.context == "death":
            print(f"  [Recovery] ✗ Ship destroyed - need to restart")
            # Press space to acknowledge death
            await bot.session.send(" ")
            await asyncio.sleep(1.0)
            # This should take us to character restart
            raise OrientationError(
                "Ship destroyed during recovery",
                screen=state.screen,
                attempts=attempt,
            )

        if state.context == "combat":
            print(f"  [Recovery] ⚠ In combat - attempting retreat")
            # Try R for retreat
            await bot.session.send("R")
            await asyncio.sleep(0.5)
            attempt += 1
            continue

        if state.context == "computer_menu":
            print(f"  [Recovery] Exiting computer menu (Q+Enter)...")
            await bot.session.send("Q\r")
            await asyncio.sleep(0.5)
            attempt += 1
            continue

        if state.context == "warping":
            # Mid-warp - just wait for it to complete, don't send keys that trigger more warps
            print(f"  [Recovery] Waiting for warp to complete...")
            await asyncio.sleep(1.0)
            attempt += 1
            continue

        if state.context == "autopilot":
            # Autopilot engaged - try to stop it
            print(f"  [Recovery] Autopilot engaged - trying to stop...")
            await bot.session.send("\r")  # Enter often stops autopilot
            await asyncio.sleep(1.0)
            attempt += 1
            continue

        if state.context in ("pause", "more"):
            # Press space to continue
            print(f"  [Recovery] {state.context} - pressing space...")
            await bot.session.send(" ")
            await asyncio.sleep(0.5)
            attempt += 1
            continue

        if state.context == "confirm":
            # Y/N prompt - usually N is safer
            print(f"  [Recovery] Confirm prompt - sending N...")
            await bot.session.send("N")
            await asyncio.sleep(0.3)
            attempt += 1
            continue

        if state.context in ("port_menu", "port_trading"):
            # Port menu - try Q then Enter to fully exit
            print(f"  [Recovery] Port menu - sending Q+Enter to exit...")
            await bot.session.send("Q\r")  # Q to quit menu, Enter to confirm
            await asyncio.sleep(0.5)
            attempt += 1
            continue

        if state.context == "menu":
            # Generic menu - try Q to exit
            print(f"  [Recovery] Menu - sending Q to exit...")
            await bot.session.send("Q")
            await asyncio.sleep(0.5)
            attempt += 1
            continue

        if state.context == "unknown":
            # Unknown state - be very conservative to avoid triggering warps
            # Track if we're changing sectors (which means we're navigating accidentally)
            if attempt == 0:
                print(f"  [Recovery] Unknown state - clearing input buffer with Escape...")
                await bot.session.send("\x1b")  # Escape to clear buffer
                await asyncio.sleep(0.5)
                attempt += 1
                continue
            elif attempt == 1:
                # Try Q to exit any menu
                print(f"  [Recovery] Trying Q to exit menu...")
                await bot.session.send("Q")
                await asyncio.sleep(0.5)
                attempt += 1
                continue
            elif attempt == 2:
                # Try space (for pause screens)
                print(f"  [Recovery] Trying space...")
                await bot.session.send(" ")
                await asyncio.sleep(0.5)
                attempt += 1
                continue
            elif attempt < 6:
                # Wait longer - we might be in a warp or transition
                print(f"  [Recovery] Waiting for state to settle...")
                await asyncio.sleep(1.0)
                attempt += 1
                continue
            # After that, fall through to normal recovery sequence but skip Enter/numbers

        # Use recovery sequence
        if attempt < len(recovery_sequences):
            key, delay = recovery_sequences[attempt]
            key_name = repr(key).replace("'", "")
            print(f"    → Sending {key_name}")
            await bot.session.send(key)
            await asyncio.sleep(delay)
        else:
            # Cycle through basic escapes
            key, delay = recovery_sequences[attempt % len(recovery_sequences[:4])]
            await bot.session.send(key)
            await asyncio.sleep(delay)

        attempt += 1

    # Failed to recover
    raise OrientationError(
        f"Failed to recover to safe state after {max_attempts} attempts",
        screen=last_state.screen if last_state else "",
        attempts=max_attempts,
    )


# =============================================================================
# Screen Parsing - Extract data from display output
# =============================================================================

def _parse_display_screen(screen: str) -> dict:
    """Parse the output of 'D' (display) command.

    Returns dict with parsed values (may have None for unparsed fields).
    """
    result = {}

    # Credits: "Credits          : 1,234,567"
    credits_match = re.search(r'credits\s*:\s*([\d,]+)', screen, re.IGNORECASE)
    if credits_match:
        result['credits'] = int(credits_match.group(1).replace(',', ''))

    # Turns left: "Turns left       : 500"
    turns_match = re.search(r'turns\s+left\s*:\s*(\d+)', screen, re.IGNORECASE)
    if turns_match:
        result['turns_left'] = int(turns_match.group(1))

    # Fighters: "Fighters         : 100"
    fighters_match = re.search(r'fighters\s*:\s*([\d,]+)', screen, re.IGNORECASE)
    if fighters_match:
        result['fighters'] = int(fighters_match.group(1).replace(',', ''))

    # Shields: "Shields          : 500"
    shields_match = re.search(r'shields\s*:\s*([\d,]+)', screen, re.IGNORECASE)
    if shields_match:
        result['shields'] = int(shields_match.group(1).replace(',', ''))

    # Holds: "Total Holds      : 50" and "Holds w/Goods    : 10"
    total_holds_match = re.search(r'total\s+holds\s*:\s*(\d+)', screen, re.IGNORECASE)
    if total_holds_match:
        result['holds_total'] = int(total_holds_match.group(1))

    holds_used_match = re.search(r'holds\s+w/goods\s*:\s*(\d+)', screen, re.IGNORECASE)
    if holds_used_match and 'holds_total' in result:
        result['holds_free'] = result['holds_total'] - int(holds_used_match.group(1))

    # Ship type: "Ship type        : Merchant Cruiser"
    ship_match = re.search(r'ship\s+type\s*:\s*(.+)', screen, re.IGNORECASE)
    if ship_match:
        result['ship_type'] = ship_match.group(1).strip()

    # Alignment: "Alignment        : 500 (Good)"
    align_match = re.search(r'alignment\s*:\s*(-?\d+)', screen, re.IGNORECASE)
    if align_match:
        result['alignment'] = int(align_match.group(1))

    # Experience: "Experience       : 1000"
    exp_match = re.search(r'experience\s*:\s*([\d,]+)', screen, re.IGNORECASE)
    if exp_match:
        result['experience'] = int(exp_match.group(1).replace(',', ''))

    # Corp: "Corporation      : 1"
    corp_match = re.search(r'corporation\s*:\s*(\d+)', screen, re.IGNORECASE)
    if corp_match:
        result['corp_id'] = int(corp_match.group(1))

    # Current sector: "Current Sector   : 123"
    sector_match = re.search(r'current\s+sector\s*:\s*(\d+)', screen, re.IGNORECASE)
    if sector_match:
        result['sector'] = int(sector_match.group(1))

    return result


def _parse_sector_display(screen: str) -> dict:
    """Parse sector display (what you see at sector command prompt).

    Returns dict with sector info.
    """
    result = {
        'warps': [],
        'has_port': False,
        'port_class': None,
        'has_planet': False,
        'planet_names': [],
        'traders_present': [],
        'hostile_fighters': 0,
    }

    # Sector number from prompt: "Command [TL=00:00:00]:[1234] (?=Help)?"
    sector_match = re.search(r'\[(\d+)\]\s*\(\?', screen)
    if sector_match:
        result['sector'] = int(sector_match.group(1))

    # Warps: "Warps to Sector(s) : 1 - 2 - 3" or "Warps to Sector(s) :  (1) - (2)"
    warps_match = re.search(r'warps?\s+to\s+sector\(?s?\)?\s*:\s*(.+)', screen, re.IGNORECASE)
    if warps_match:
        warp_line = warps_match.group(1)
        # Extract all numbers, ignoring parentheses
        warps = re.findall(r'\d+', warp_line)
        result['warps'] = [int(w) for w in warps]

    # Port: "Ports   : Trading Port (BBS)"
    port_match = re.search(r'ports?\s*:\s*(.+)', screen, re.IGNORECASE)
    if port_match:
        port_line = port_match.group(1).strip()
        if port_line and port_line.lower() not in ('none', '-'):
            result['has_port'] = True
            # Extract class: (BBS), (SSB), etc.
            class_match = re.search(r'\(([A-Z]{3})\)', port_line)
            if class_match:
                result['port_class'] = class_match.group(1)

    # Planets: "Planets : Terra (Class M)"
    planet_match = re.search(r'planets?\s*:\s*(.+)', screen, re.IGNORECASE)
    if planet_match:
        planet_line = planet_match.group(1).strip()
        if planet_line and planet_line.lower() not in ('none', '-'):
            result['has_planet'] = True
            # Extract planet names
            names = re.findall(r'([A-Za-z][A-Za-z0-9\s\']+?)(?:\s*\(|,|$)', planet_line)
            result['planet_names'] = [n.strip() for n in names if n.strip()]

    # Traders: "Traders : Captain Bob"
    traders_match = re.search(r'traders?\s*:\s*(.+)', screen, re.IGNORECASE)
    if traders_match:
        trader_line = traders_match.group(1).strip()
        if trader_line and trader_line.lower() not in ('none', '-'):
            # Split by comma or 'and'
            names = re.split(r',|\band\b', trader_line)
            result['traders_present'] = [n.strip() for n in names if n.strip()]

    # Fighters: "Fighters: 1000 (hostile)"
    fighters_match = re.search(r'fighters?\s*:\s*([\d,]+).*hostile', screen, re.IGNORECASE)
    if fighters_match:
        result['hostile_fighters'] = int(fighters_match.group(1).replace(',', ''))

    return result


# =============================================================================
# Layer 1: Safety - Reach a known stable state
# =============================================================================

async def _wait_for_screen_stability(
    bot: TradingBot,
    stability_ms: int = 100,
    max_wait_ms: int = 2000,
    read_interval_ms: int = 50,
) -> str:
    """Wait until screen content stops changing (handles baud rate rendering).

    At low baud rates, characters arrive one at a time. This function reads
    repeatedly until the screen content hasn't changed for `stability_ms`.

    Args:
        bot: TradingBot instance
        stability_ms: How long screen must be unchanged to be considered stable
        max_wait_ms: Maximum total time to wait
        read_interval_ms: How often to poll the screen

    Returns:
        Stable screen content
    """
    last_screen = ""
    last_change_time = time()
    start_time = time()

    while True:
        elapsed_ms = (time() - start_time) * 1000
        if elapsed_ms > max_wait_ms:
            break

        try:
            result = await bot.session.read(timeout_ms=read_interval_ms, max_bytes=8192)
            screen = result.get("screen", "")
        except Exception:
            screen = last_screen

        if screen != last_screen:
            last_screen = screen
            last_change_time = time()
        else:
            # Screen unchanged - check if stable long enough
            stable_ms = (time() - last_change_time) * 1000
            if stable_ms >= stability_ms and last_screen.strip():
                break

        await asyncio.sleep(read_interval_ms / 1000)

    return last_screen


async def _reach_safe_state(
    bot: TradingBot,
    max_attempts: int = 10,
    stability_ms: int = 100,
) -> tuple[str, str, str]:
    """Try to reach a safe state using gentle escapes.

    Uses screen stability detection to handle baud rate rendering delays.

    Returns:
        Tuple of (context, prompt_id, screen)

    Raises:
        OrientationError if unable to reach safe state
    """
    gentle_keys = [" ", "\r", " ", "\r", "Q", " ", "\r", "Q", " ", "\r"]

    last_screen = ""

    for attempt in range(max_attempts):
        # Wait for screen to stabilize (handles baud rate rendering)
        try:
            screen = await _wait_for_screen_stability(
                bot,
                stability_ms=stability_ms,
                max_wait_ms=2000,
            )
            if screen.strip():
                last_screen = screen
        except Exception:
            screen = last_screen

        # Check if we're in a safe state using our context detection
        context = _detect_context(screen)

        if context in ("sector_command", "planet_command", "citadel_command"):
            print(f"  [Orient] Safe state reached: {context}")
            return context, "", screen

        if context == "pause":
            print(f"  [Orient] Dismissing pause screen...")
            await bot.session.send(" ")
            await asyncio.sleep(0.3)
            continue

        if context in ("menu", "port_menu"):
            print(f"  [Orient] In {context}, sending Q to back out...")
            await bot.session.send("Q")
            await asyncio.sleep(0.5)
            continue

        # Unknown or unrecognized - try gentle escape
        if attempt < len(gentle_keys):
            key = gentle_keys[attempt]
            key_name = repr(key).replace("'", "")
            print(f"  [Orient] State '{context}', trying {key_name} ({attempt + 1}/{max_attempts})...")
            await bot.session.send(key)
            await asyncio.sleep(0.3)

    raise OrientationError(
        f"Failed to reach safe state after {max_attempts} attempts",
        screen=last_screen,
        attempts=max_attempts,
    )


# =============================================================================
# Layer 2: Context - Gather comprehensive game state
# =============================================================================

async def _gather_state(
    bot: TradingBot,
    context: str,
    screen: str,
    prompt_id: str,
) -> GameState:
    """Gather comprehensive game state via Display command.

    Args:
        bot: TradingBot instance
        context: Current context (sector_command, etc.)
        screen: Current screen content
        prompt_id: Current prompt ID

    Returns:
        Populated GameState
    """
    # Start with state from current screen
    state = GameState(
        context=context,
        raw_screen=screen,
        prompt_id=prompt_id,
    )

    # Parse sector display (warps, port, etc.)
    sector_info = _parse_sector_display(screen)
    state.sector = sector_info.get('sector')
    state.warps = sector_info.get('warps', [])
    state.has_port = sector_info.get('has_port', False)
    state.port_class = sector_info.get('port_class')
    state.has_planet = sector_info.get('has_planet', False)
    state.planet_names = sector_info.get('planet_names', [])
    state.traders_present = sector_info.get('traders_present', [])
    state.hostile_fighters = sector_info.get('hostile_fighters', 0)

    # Send 'D' for full display
    print(f"  [Orient] Sending D for full status...")
    await bot.session.send("D")
    await asyncio.sleep(0.5)

    # Read display output
    from .io import wait_and_respond
    try:
        _, _, display_screen, _ = await wait_and_respond(bot, timeout_ms=5000)

        # Parse display output
        display_info = _parse_display_screen(display_screen)

        state.credits = display_info.get('credits')
        state.turns_left = display_info.get('turns_left')
        state.fighters = display_info.get('fighters')
        state.shields = display_info.get('shields')
        state.holds_total = display_info.get('holds_total')
        state.holds_free = display_info.get('holds_free')
        state.ship_type = display_info.get('ship_type')
        state.alignment = display_info.get('alignment')
        state.experience = display_info.get('experience')
        state.corp_id = display_info.get('corp_id')

        # Sector from display if not already set
        if state.sector is None:
            state.sector = display_info.get('sector')

        # Update raw screen with full display
        state.raw_screen = display_screen

    except Exception as e:
        print(f"  [Orient] Warning: Display command failed: {e}")

    return state


# =============================================================================
# Main Entry Point
# =============================================================================

async def orient(
    bot: TradingBot,
    knowledge: SectorKnowledge | None = None,
) -> GameState:
    """Complete orientation sequence.

    1. Safety - Reach a known stable state
    2. Context - Gather comprehensive game state
    3. Navigation - Record observations for future pathfinding

    Args:
        bot: TradingBot instance
        knowledge: Optional SectorKnowledge for recording observations

    Returns:
        Complete GameState

    Raises:
        OrientationError if unable to establish safe state
    """
    print("\n[Orientation] Starting...")

    # Layer 1: Safety
    context, prompt_id, screen = await _reach_safe_state(bot)

    # Layer 2: Context
    state = await _gather_state(bot, context, screen, prompt_id)

    # Layer 3: Navigation - Record what we learned
    if knowledge and state.sector:
        knowledge.record_observation(state)
        print(f"  [Orient] Recorded sector {state.sector} to knowledge base")

    print(f"  [Orient] Complete: {state.summary()}")

    return state
