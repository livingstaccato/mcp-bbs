"""Context detection and recovery - identify and escape from any state."""

from __future__ import annotations

import asyncio
import re
from typing import TYPE_CHECKING

from .models import OrientationError, QuickState

if TYPE_CHECKING:
    from bbsbot.games.tw2002.bot import TradingBot


# Context categories for quick checks
SAFE_CONTEXTS = {"sector_command", "planet_command", "citadel_command", "stardock"}
ACTION_CONTEXTS = {
    "port_menu",
    "port_trading",
    "bank",
    "ship_shop",
    "hardware_shop",
    "combat",
    "message_system",
    "tavern",
    "grimy_trader",
    "gambling",
    "computer_menu",
    "cim_mode",
    "course_plotter",
    "underground",
    "corporate_listings",
}
TRANSITION_CONTEXTS = {"pause", "more", "confirm", "port_report", "eavesdrop"}
NAVIGATION_CONTEXTS = {"warping", "autopilot"}
DANGER_CONTEXTS = {"combat", "death"}
INFO_CONTEXTS = {"computer_menu", "cim_mode", "port_report", "course_plotter"}


def detect_context(screen: str) -> str:
    """Detect game context from screen content.

    Returns one of the CONTEXT constants above. This is the core "where am I"
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
    lines = [l.strip() for l in screen.split("\n") if l.strip()]
    if not lines:
        return "unknown"

    last_line = lines[-1].lower()
    last_lines = "\n".join(lines[-5:]).lower()
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
    if re.search(r"\[\d+\]\s*\(\?", last_line):
        return "sector_command"
    # Also check for "Command" at start of line with sector number
    if re.search(r"command.*\[\d+\]", last_line, re.IGNORECASE):
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
    # Haggle prompt: "Your offer [471] ?"
    if "your offer" in last_line or "counter" in last_line or "final price" in last_line:
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
    if "computer" in last_lines and (
        "navigation" in last_lines or "displays" in last_lines or "miscellaneous" in last_lines
    ):
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
    # Pause screens - only match ACTUAL pause prompts, not decorative [Pause] banners
    # CRITICAL: Must come BEFORE menu detection to avoid misidentifying pauses as menus
    # Real pause prompts have [Pause] near bottom with minimal other text
    # Game menus have [Pause] at top with lots of menu text below
    lines_lower = [l.lower() for l in lines if l.strip()]
    if len(lines_lower) > 0:
        # Check last 3 lines for pause prompt (not in first 5 lines which could be banners)
        last_3_lines = "\n".join(lines_lower[-3:])
        if "[pause]" in last_3_lines or "[any key]" in last_3_lines:
            # Make sure it's not a game selection menu with [Pause] banner art
            # Game menus have: "trade wars", "selection", "supports up to", menu options
            is_game_menu = (
                "enter your choice" in last_line
                or "==--" in full_screen
                or "trade wars" in full_screen
                or "supports up to" in full_screen
                or "selection (" in last_line
                or ("t - play" in full_screen and "x - exit" in full_screen)
            )
            if not is_game_menu:
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

    # === CORPORATE LISTINGS MENU ===
    # Handle the TW2002 Corporate Listings menu that appears early in game
    if "corporate listings" in full_screen and "which listing" in last_line:
        return "corporate_listings"

    # === GENERIC MENU ===
    if "selection" in last_line.lower() or "enter your choice" in last_line.lower():
        return "menu"
    # Don't match normal sector command prompts (Command [TL=...]:)
    if "command" not in last_line.lower() and "?" in last_line and ":" in last_line:
        return "menu"

    return "unknown"


async def where_am_i(bot: TradingBot, timeout_ms: int = 50) -> QuickState:
    """Fast state check - quickly determine where we are.

    This is the FAST "where am I" function. It checks the current screen
    buffer first (instant, no I/O), only doing a read if the buffer is empty.

    For full state gathering, use orient() instead.

    Args:
        bot: TradingBot instance
        timeout_ms: Max time to wait for screen data (only used if buffer is empty)

    Returns:
        QuickState with context and basic info
    """
    if not getattr(bot, "session", None) or not bot.session.is_connected():
        return QuickState(context="unknown", suggested_action="reconnect")

    snap = bot.session.snapshot()
    screen = snap.get("screen", "")
    prompt_id = (snap.get("prompt_detected") or {}).get("prompt_id", "")

    # If buffer is empty, block briefly for the next update to populate it.
    if not screen.strip():
        await bot.session.wait_for_update(timeout_ms=timeout_ms)
        snap = bot.session.snapshot()
        screen = snap.get("screen", "")
        prompt_id = (snap.get("prompt_detected") or {}).get("prompt_id", "")

    # Detect context (screen heuristics first).
    context = detect_context(screen)

    # If prompt detection has high-confidence IDs, prefer them over heuristics.
    # This avoids "unknown" loops where recovery spams Enter/Space on an input prompt.
    if prompt_id:
        if prompt_id == "prompt.port_haggle":
            context = "port_trading"
        elif prompt_id.startswith("prompt.port_") or prompt_id.startswith("prompt.hardware_"):
            # Port buy/sell flows can look like generic menus to the heuristic detector.
            # Treat as port_trading so recovery exits with Q if needed.
            context = "port_trading"
        elif prompt_id in ("prompt.port_menu",):
            context = "port_menu"
        elif prompt_id in (
            "prompt.sector_command",
            "prompt.command_generic",
            "prompt.planet_command",
            "prompt.citadel_command",
        ):
            # Keep these stable prompts authoritative.
            context = "sector_command" if "sector" in prompt_id or "command_generic" in prompt_id else context

    # Capture diagnostic data for stuck bot analysis
    if hasattr(bot, "diagnostic_buffer"):
        bot.diagnostic_buffer["recent_screens"].append(screen[:1000])
        if len(bot.diagnostic_buffer["recent_screens"]) > bot.diagnostic_buffer["max_history"]:
            bot.diagnostic_buffer["recent_screens"] = bot.diagnostic_buffer["recent_screens"][
                -bot.diagnostic_buffer["max_history"] :
            ]

        bot.diagnostic_buffer["recent_prompts"].append(f"{context}|{prompt_id}")
        if len(bot.diagnostic_buffer["recent_prompts"]) > bot.diagnostic_buffer["max_history"]:
            bot.diagnostic_buffer["recent_prompts"] = bot.diagnostic_buffer["recent_prompts"][
                -bot.diagnostic_buffer["max_history"] :
            ]

    # Extract sector from screen if possible
    sector = None
    # Try prompt format: [123] - use findall and take LAST match
    # because screen buffer may contain old sector info at top
    sector_matches = re.findall(r"\[(\d+)\]\s*\(\?", screen)
    if sector_matches:
        sector = int(sector_matches[-1])  # Take LAST match (current prompt)
    else:
        # Try "Sector 123" format - also take last match
        sector_matches = re.findall(r"sector\s+(\d+)", screen, re.IGNORECASE)
        if sector_matches:
            sector = int(sector_matches[-1])

    # Determine safety and suggested action
    is_safe = context in SAFE_CONTEXTS
    is_danger = context in DANGER_CONTEXTS

    # Suggest action based on context
    suggested_action = None
    if context == "pause" or context == "more":
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
    bot: TradingBot,
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
        (" ", 0.3),  # Space for pause/more
        ("Q", 0.3),  # Q to exit menus
        ("N", 0.3),  # N for Y/N prompts
        ("\x1b", 0.3),  # Escape key
        # More aggressive
        ("Q", 0.3),  # Q again
        (" ", 0.3),  # Space
        ("\x1b", 0.5),  # Escape
        ("Q", 0.5),  # Q with longer wait
        # Really aggressive - still no Enter
        (" ", 0.5),
        ("\x1b", 0.5),  # Multiple escapes
        ("\x1b", 0.3),
    ]

    print("\n[Recovery] Attempting to recover to safe state...")

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
            bot.loop_detection.reset()
            return state

        # Handle specific contexts
        if state.context == "death":
            print("  [Recovery] ✗ Ship destroyed - need to restart")
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
            print("  [Recovery] ⚠ In combat - attempting retreat")
            # Try R for retreat
            await bot.session.send("R")
            await asyncio.sleep(0.5)
            attempt += 1
            continue

        if state.context == "computer_menu":
            print("  [Recovery] Exiting computer menu (Q+Enter)...")
            await bot.session.send("Q\r")
            await asyncio.sleep(0.5)
            attempt += 1
            continue

        if state.context == "warping":
            # Mid-warp - just wait for it to complete, don't send keys that trigger more warps
            print("  [Recovery] Waiting for warp to complete...")
            await asyncio.sleep(1.0)
            attempt += 1
            continue

        if state.context == "autopilot":
            # Autopilot engaged - try to stop it
            print("  [Recovery] Autopilot engaged - trying to stop...")
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
            print("  [Recovery] Confirm prompt - sending N...")
            await bot.session.send("N")
            await asyncio.sleep(0.3)
            attempt += 1
            continue

        if state.context in ("port_menu", "port_trading"):
            # Port flows:
            # - If we're on a haggle screen and can't afford the transaction, abort out of the trade.
            # - Otherwise, try to exit back to a safe prompt.
            if state.prompt_id == "prompt.port_haggle" and re.search(
                r"(?i)you\\s+only\\s+have\\s+([\\d,]+)\\s+credits", state.screen or ""
            ):
                print("  [Recovery] Port haggle with low credits - exiting trade (Q+Enter)...")
                await bot.session.send("Q\r")
                await asyncio.sleep(0.5)
                attempt += 1
                continue

            # Generic exit: Q then Enter (some port screens require Enter to confirm exit).
            print("  [Recovery] Port screen - sending Q+Enter to exit...")
            await bot.session.send("Q\r")
            await asyncio.sleep(0.5)
            attempt += 1
            continue

        if state.context == "corporate_listings":
            # Corporate listings menu - send Q to quit
            print("  [Recovery] Corporate listings - sending Q to exit...")
            await bot.session.send("Q")
            await asyncio.sleep(0.5)
            attempt += 1
            continue

        if state.context == "menu":
            # Check if this is ACTUALLY the game selection menu by looking for game titles
            # Don't just rely on sector=None, as in-game menus can also have unparseable sectors
            screen_lower = screen.lower() if screen else ""
            is_game_selection = (
                state.sector is None
                and hasattr(bot, "last_game_letter")
                and bot.last_game_letter
                and (
                    "trade wars" in screen_lower
                    or "supports up to" in screen_lower
                    or "- play" in screen_lower
                    or "game selection" in screen_lower
                )
            )

            if is_game_selection:
                print(f"  [Recovery] Game selection menu - sending {bot.last_game_letter} to enter game...")
                await bot.session.send(bot.last_game_letter + "\r")
                await asyncio.sleep(1.0)
                attempt += 1
                continue
            # Generic in-game menu (or unknown menu) - try Enter to continue
            print("  [Recovery] In-game menu - sending Enter to continue...")
            await bot.session.send("\r")
            await asyncio.sleep(0.5)
            attempt += 1
            continue

        if state.context == "unknown":
            # Unknown state - be very conservative to avoid triggering warps
            # Track if we're changing sectors (which means we're navigating accidentally)
            if attempt == 0:
                print("  [Recovery] Unknown state - clearing input buffer with Escape...")
                await bot.session.send("\x1b")  # Escape to clear buffer
                await asyncio.sleep(0.5)
                attempt += 1
                continue
            elif attempt == 1:
                # Try Q to exit any menu
                print("  [Recovery] Trying Q to exit menu...")
                await bot.session.send("Q")
                await asyncio.sleep(0.5)
                attempt += 1
                continue
            elif attempt == 2:
                # Try space (for pause screens)
                print("  [Recovery] Trying space...")
                await bot.session.send(" ")
                await asyncio.sleep(0.5)
                attempt += 1
                continue
            elif attempt < 6:
                # Wait longer - we might be in a warp or transition
                print("  [Recovery] Waiting for state to settle...")
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
