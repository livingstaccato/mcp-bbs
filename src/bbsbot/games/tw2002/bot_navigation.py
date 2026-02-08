"""Navigation and orientation methods for TradingBot."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from bbsbot.games.tw2002 import connection, io, login, orientation

if TYPE_CHECKING:
    from bbsbot.games.tw2002.orientation import GameState, QuickState
    from bbsbot.games.tw2002.bot_core import TradingBot


# Mix-in methods for TradingBot navigation
def _init_navigation_mixin(bot: TradingBot) -> None:
    """Initialize navigation methods on bot instance."""
    # These are added dynamically via bot.py


async def init_knowledge(
    bot: TradingBot,
    host: str = "localhost",
    port: int = 2002,
    game_letter: str | None = None,
) -> None:
    """Initialize sector knowledge for this character/server/game.

    Args:
        bot: TradingBot instance
        host: BBS host
        port: BBS port
        game_letter: Game selection letter (A, B, C, etc.) to scope data per-game on same BBS
    """
    from bbsbot.games.tw2002.orientation import SectorKnowledge

    # Include game_letter in path to separate data for different games on same BBS
    if game_letter:
        knowledge_dir = bot.knowledge_root / "tw2002" / f"{host}_{port}_game{game_letter}"
    else:
        knowledge_dir = bot.knowledge_root / "tw2002" / f"{host}_{port}"

    bot.sector_knowledge = SectorKnowledge(
        knowledge_dir=knowledge_dir,
        character_name=bot.character_name,
        twerk_data_dir=bot.twerk_data_dir,
    )
    game_info = f"_game{game_letter}" if game_letter else ""
    print(f"  [Knowledge] Initialized for {bot.character_name} @ {host}:{port}{game_info}")
    print(f"  [Knowledge] Known sectors: {bot.sector_knowledge.known_sector_count()}")


async def orient_full(bot: TradingBot, force_scan: bool = False) -> GameState:
    """Run full orientation sequence.

    1. Safety - Reach a known stable state
    2. Context - Gather comprehensive game state (D command if needed)
    3. Navigation - Record observations for future pathfinding

    Args:
        bot: TradingBot instance
        force_scan: If True, always run D command regardless of scan state

    Returns:
        Complete GameState

    Raises:
        OrientationError if unable to establish safe state
    """
    from time import time as _time

    t0 = _time()
    should_scan = force_scan or bot.needs_scan()

    if should_scan:
        bot.game_state = await orientation.orient(bot, bot.sector_knowledge)
        # Mark as scanned after successful orient
        if bot.game_state.sector:
            bot.mark_scanned(bot.game_state.sector)
    else:
        # Fast path: skip D command, just check context
        quick_state = await orientation.where_am_i(bot)
        if quick_state.is_safe:
            # Extract semantic data for credits and other state
            # The session read already captured kv_data during where_am_i()
            try:
                result = await bot.session.read(timeout_ms=10, max_bytes=1024)
                kv_data = result.get("kv_data", {})
            except Exception:
                kv_data = {}

            # Merge kv_data with last_semantic_data for completeness
            merged_kv = dict(bot.last_semantic_data)
            merged_kv.update({k: v for k, v in kv_data.items() if v is not None})

            # Use cached knowledge
            from bbsbot.games.tw2002.orientation import GameState
            bot.game_state = GameState(
                context=quick_state.context,
                sector=quick_state.sector,
                raw_screen=quick_state.screen,
                prompt_id=quick_state.prompt_id,
                # Extract critical state from semantic data
                credits=merged_kv.get('credits'),
                turns_left=merged_kv.get('turns_left'),
                fighters=merged_kv.get('fighters'),
                shields=merged_kv.get('shields'),
            )
            # Fill in from knowledge if available
            if bot.sector_knowledge and quick_state.sector:
                info = bot.sector_knowledge.get_sector_info(quick_state.sector)
                if info:
                    bot.game_state.warps = info.warps
                    bot.game_state.has_port = info.has_port
                    bot.game_state.port_class = info.port_class
                    bot.game_state.has_planet = info.has_planet
                    bot.game_state.planet_names = info.planet_names
            fast_ms = (_time() - t0) * 1000
            print(f"  [Orient] Fast path: {bot.game_state.summary()} [{fast_ms:.0f}ms]")
        else:
            # Not safe, need full orient
            bot.game_state = await orientation.orient(bot, bot.sector_knowledge)
            if bot.game_state.sector:
                bot.mark_scanned(bot.game_state.sector)

    # Sync legacy state tracking
    if bot.game_state.sector:
        bot.current_sector = bot.game_state.sector
        bot.sectors_visited.add(bot.game_state.sector)
    if bot.game_state.credits:
        bot.current_credits = bot.game_state.credits

    # Update combat tracking
    if bot._combat:
        bot._combat.update_from_state(bot.game_state)

    return bot.game_state


async def go_to_computer(bot: TradingBot) -> bool:
    """Navigate to Computer menu from sector command.

    Returns:
        True if successfully at Computer menu
    """
    state = await orientation.where_am_i(bot)
    if state.context != "sector_command":
        print(f"  [Computer] Not at sector command (at {state.context})")
        return False

    await bot.session.send("C")
    await asyncio.sleep(0.5)

    state = await orientation.where_am_i(bot)
    return state.context == "computer_menu"


async def go_to_cim(bot: TradingBot) -> bool:
    """Navigate to CIM (Computer Interrogation Mode).

    CIM provides machine-readable data dumps for:
    - Port data (zero-turn port enumeration)
    - Sector data (universe mapping)
    - Ship data (scanner results)

    Returns:
        True if successfully in CIM mode
    """
    # First get to computer menu
    if not await go_to_computer(bot):
        return False

    # Enter CIM mode (^ character or ALT-200)
    await bot.session.send("^")
    await asyncio.sleep(0.3)

    state = await orientation.where_am_i(bot)
    return state.context == "cim_mode"


async def get_port_report(bot: TradingBot) -> str:
    """Get human-readable port report from Computer menu.

    Returns:
        Port report text or empty string on failure
    """
    if not await go_to_computer(bot):
        return ""

    # Request port report
    await bot.session.send("R")
    await asyncio.sleep(1.0)

    result = await bot.session.read(timeout_ms=2000, max_bytes=16384)
    screen = result.get("screen", "")

    # Return to safe state
    await orientation.recover_to_safe_state(bot)

    return screen


async def plot_course(bot: TradingBot, destination: int) -> bool:
    """Use course plotter to plan route (zero turns).

    Args:
        destination: Target sector number

    Returns:
        True if course was successfully plotted
    """
    if not await go_to_computer(bot):
        return False

    # Access course plotter
    await bot.session.send("F")
    await asyncio.sleep(0.5)

    # Enter destination
    await bot.session.send(f"{destination}\r")
    await asyncio.sleep(1.0)

    # Read result
    result = await bot.session.read(timeout_ms=2000, max_bytes=8192)
    screen = result.get("screen", "")

    # Check if path was found
    success = "path" in screen.lower() or "route" in screen.lower()

    # Return to safe state
    await orientation.recover_to_safe_state(bot)

    return success


async def go_to_stardock(bot: TradingBot) -> bool:
    """Navigate to StarDock (must be in StarDock sector).

    Returns:
        True if successfully at StarDock
    """
    state = await orientation.where_am_i(bot)
    if state.context != "sector_command":
        return False

    # Try to enter StarDock
    await bot.session.send("S")
    await asyncio.sleep(0.5)

    state = await orientation.where_am_i(bot)
    return state.context == "stardock"


async def go_to_tavern(bot: TradingBot) -> bool:
    """Navigate to Lost Trader's Tavern (must be at StarDock).

    Returns:
        True if successfully at Tavern
    """
    state = await orientation.where_am_i(bot)

    # If not at StarDock, try to get there
    if state.context != "stardock":
        if not await go_to_stardock(bot):
            return False

    # Enter Tavern
    await bot.session.send("T")
    await asyncio.sleep(0.5)

    state = await orientation.where_am_i(bot)
    return state.context == "tavern"


async def ask_grimy_trader(bot: TradingBot, topic: str) -> str:
    """Ask Grimy Trader for information.

    Args:
        topic: One of "TRADER", "FEDERATION", "MAFIA"

    Returns:
        Information received or empty string on failure
    """
    if not await go_to_tavern(bot):
        return ""

    # Talk to Grimy Trader
    await bot.session.send("T")
    await asyncio.sleep(0.5)

    # Ask about topic
    await bot.session.send(f"{topic}\r")
    await asyncio.sleep(1.0)

    result = await bot.session.read(timeout_ms=2000, max_bytes=8192)
    screen = result.get("screen", "")

    # Return to safe state
    await orientation.recover_to_safe_state(bot)

    return screen


def find_path_from_knowledge(bot: TradingBot, destination: int) -> list[int] | None:
    """Find path from current sector to destination.

    Uses sector knowledge (discovery + cache + optional twerk).

    Returns:
        List of sectors to traverse, or None if unknown
    """
    if not bot.sector_knowledge:
        return None
    if not bot.current_sector:
        return None
    return bot.sector_knowledge.find_path(bot.current_sector, destination)


def is_safe(bot: TradingBot) -> bool:
    """Quick check if we're in a safe state based on last game_state."""
    from bbsbot.games.tw2002.orientation import SAFE_CONTEXTS
    if not bot.game_state:
        return False
    return bot.game_state.context in SAFE_CONTEXTS


def is_in_danger(bot: TradingBot) -> bool:
    """Quick check if we're in a dangerous state."""
    from bbsbot.games.tw2002.orientation import DANGER_CONTEXTS
    if not bot.game_state:
        return False
    return bot.game_state.context in DANGER_CONTEXTS
