#!/usr/bin/env python3
"""Play TW2002 to win - automated trading and wealth building.

This script plays the game actively:
1. Find profitable trade routes
2. Execute trades to build wealth
3. Navigate between ports
4. Handle encounters
5. If character dies, create new one and continue

Now supports configuration via YAML file and the new systems:
- Multi-character management with knowledge sharing
- Configurable trading strategies
- D command optimization (only scan new sectors)
- Banking, upgrades, and combat avoidance
"""

import argparse
import asyncio
import contextlib
import random
import re
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

from bbsbot.games.tw2002.bot import TradingBot
from bbsbot.games.tw2002.config import BotConfig, load_config
from bbsbot.games.tw2002.multi_character import MultiCharacterManager

if TYPE_CHECKING:
    from bbsbot.games.tw2002.character import CharacterState


class PortInfo(BaseModel):
    """Information about a port."""

    sector: int
    buying: list[str] = Field(default_factory=list)  # What port buys (we can sell)
    selling: list[str] = Field(default_factory=list)  # What port sells (we can buy)
    port_type: str = ""

    model_config = ConfigDict(extra="ignore")


class GameSession(BaseModel):
    """Track game session state."""

    credits: int = 0
    turns_left: int = 0
    sector: int = 0
    holds: int = 20
    cargo: dict = Field(default_factory=dict)
    known_ports: dict = Field(default_factory=dict)
    death_count: int = 0
    total_profit: int = 0
    trades_completed: int = 0

    model_config = ConfigDict(extra="ignore")


class TradeWarPlayer:
    """Automated TradeWars player."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 2002,
        config: BotConfig | None = None,
    ):
        self.host = host
        self.port = port
        self.config = config or BotConfig()
        self.bot: TradingBot | None = None
        self.session = GameSession()
        self.character_num = 1

        # Multi-character support
        self.multi_char: MultiCharacterManager | None = None
        self.char_state: CharacterState | None = None

    async def start_game(self) -> bool:
        """Connect and login to start playing."""
        print("\n" + "=" * 60, flush=True)
        print(f"STARTING GAME SESSION (Character #{self.character_num})")
        print("=" * 60, flush=True)

        # Initialize multi-character manager if not done
        if self.multi_char is None:
            from bbsbot.paths import default_knowledge_root

            knowledge_root = default_knowledge_root()
            data_dir = knowledge_root / "tw2002" / f"{self.host}_{self.port}"
            self.multi_char = MultiCharacterManager(
                config=self.config,
                data_dir=data_dir,
            )

        # Create character using multi-char manager
        self.char_state = self.multi_char.create_character()
        char_name = self.char_state.name

        # Create bot with config
        self.bot = TradingBot(
            character_name=char_name,
            config=self.config,
        )

        try:
            # Connect
            print(f"\n[Connect] Connecting to {self.host}:{self.port}...", flush=True)
            await self.bot.connect(host=self.host, port=self.port)
            print("  Connected!", flush=True)

            # Initialize sector knowledge
            self.bot.init_knowledge(self.host, self.port)

            # Login with unique name
            print(f"\n[Login] Logging in as {char_name}...", flush=True)
            await self.bot.login_sequence(
                game_password=self.config.connection.game_password,
                character_password=self.config.character.password,
                username=char_name,
            )
            print("  Logged in!", flush=True)

            # Skip full orient() to avoid loop detection issue
            # Just get quick state from where_am_i()
            print("\n[Quick Check] Getting position...", flush=True)
            state = await self.bot.where_am_i()

            # If on planet, leave to sector
            if state.context == "planet_command":
                print("  On planet - leaving to space...", flush=True)
                await self.leave_planet()
                state = await self.bot.where_am_i()

            self.session.sector = state.sector or 1
            # Get detailed state from ship status instead
            self.session.credits = 1000  # Will be updated by get_ship_status
            self.session.turns_left = 250  # Will be updated by get_ship_status

            print(f"  Context: {state.context}", flush=True)
            print(f"  Sector: {self.session.sector}", flush=True)

            return True

        except Exception as e:
            print(f"  ERROR: {e}", flush=True)
            import traceback

            traceback.print_exc()
            return False

    async def leave_planet(self) -> bool:
        """Leave planet and return to sector space."""
        print("    Leaving planet (Q to leave)...")
        # On a planet, Q exits to sector (not L which is for landing)
        await self.bot.session.send("Q")
        await asyncio.sleep(1.0)

        # Handle any prompts
        result = await self.bot.session.read(timeout_ms=2000, max_bytes=8192)
        screen = result.get("screen", "")

        # Handle confirmation prompts
        for _ in range(5):
            screen_lower = screen.lower()
            if "[y/n]" in screen_lower or "(y/n)" in screen_lower:
                await self.bot.session.send("Y")
            elif "press" in screen_lower or "pause" in screen_lower:
                await self.bot.session.send(" ")
            elif "command" in screen_lower and "sector" in screen_lower:
                break
            await asyncio.sleep(0.3)
            result = await self.bot.session.read(timeout_ms=500, max_bytes=4096)
            screen = result.get("screen", "")

        # Check where we are
        state = await self.bot.where_am_i()
        if state.context == "sector_command":
            print("    Left planet - now in sector space", flush=True)
            return True
        else:
            print(f"    Still at: {state.context}", flush=True)
            # Try alternative: send Q again then Enter
            await self.bot.session.send("Q\r")
            await asyncio.sleep(0.5)
            await self.bot.recover()
            state = await self.bot.where_am_i()
            if state.context == "sector_command":
                print("    Left planet after retry", flush=True)
                return True
            return False

    async def get_ship_status(self) -> None:
        """Get current ship status and update session."""
        # Clear loop detection before status check
        self.bot.loop_detection.reset()

        await self.bot.session.send("I")
        await asyncio.sleep(0.8)

        # Read multiple times to get full status screen
        full_screen = ""
        for _ in range(3):
            result = await self.bot.session.read(timeout_ms=1500, max_bytes=8192)
            screen = result.get("screen", "")
            full_screen = screen  # Use latest screen
            if "credits" in screen.lower() or "turns" in screen.lower():
                break
            await asyncio.sleep(0.3)

        # Parse credits
        credit_match = re.search(r"Credits\s*:?\s*([\d,]+)", full_screen, re.IGNORECASE)
        if credit_match:
            self.session.credits = int(credit_match.group(1).replace(",", ""))

        # Parse turns
        turn_match = re.search(r"Turns\s+[Ll]eft\s*:?\s*(\d+)", full_screen)
        if turn_match:
            self.session.turns_left = int(turn_match.group(1))

        # Parse holds
        hold_match = re.search(r"Holds\s*:?\s*(\d+)", full_screen, re.IGNORECASE)
        if hold_match:
            self.session.holds = int(hold_match.group(1))

        # Parse current sector
        sector_match = re.search(r"Sector\s*:?\s*(\d+)", full_screen, re.IGNORECASE)
        if sector_match:
            self.session.sector = int(sector_match.group(1))

        # Press space to continue and clear any prompts
        await self.bot.session.send(" ")
        await asyncio.sleep(0.5)
        await self.bot.session.send(" ")
        await asyncio.sleep(0.3)
        await self.bot.recover()

    async def scan_sector(self) -> dict:
        """Get info about current sector.

        Uses D command optimization - only scans if sector hasn't been scanned
        or if we need fresh data (configurable rescan interval).
        """
        sector = self.session.sector

        # Check if we need to scan (D command optimization)
        needs_scan = True
        if self.bot.sector_knowledge and sector:
            needs_scan = self.bot.needs_scan(sector)
            if not needs_scan:
                # Use cached knowledge
                info = self.bot.sector_knowledge.get_sector_info(sector)
                if info:
                    print(f"  [Using cached info for sector {sector}]", flush=True)
                    return {
                        "has_port": info.has_port,
                        "has_planet": info.has_planet,
                        "warps": info.warps,
                        "raw": "",
                        "from_cache": True,
                    }
                # Cache miss, need to scan
                needs_scan = True

        # Run D command
        await self.bot.session.send("D")
        await asyncio.sleep(0.5)
        result = await self.bot.session.read(timeout_ms=2000, max_bytes=8192)
        screen = result.get("screen", "")

        info = {
            "has_port": False,
            "has_planet": False,
            "warps": [],
            "raw": screen,
            "from_cache": False,
        }

        # Check for port - look for "Commerce" which indicates a trading port
        # or "Class X" port type (but not "no port" or "isn't a port")
        screen_lower = screen.lower()
        if "commerce" in screen_lower or re.search(r"class\s+[1-9]", screen_lower) or "trading port" in screen_lower:
            if "no port" not in screen_lower and "isn't a port" not in screen_lower:
                info["has_port"] = True

        # Check for planet
        if "planet" in screen_lower and "no planet" not in screen_lower:
            info["has_planet"] = True

        # Parse warps
        warp_match = re.search(r"Warps to Sector\(s\)\s*:\s*([\d\s\(\)\-]+)", screen)
        if warp_match:
            warp_text = warp_match.group(1)
            info["warps"] = [int(x) for x in re.findall(r"\d+", warp_text)]

        # Record the observation to store warps, port, planet info
        # LLM HINT: Use record_observation() with a GameState to store sector info properly.
        # mark_scanned() only sets timestamp, doesn't store discovered data.
        # GameState requires 'context' argument even if we only need sector data.
        if sector and self.bot.sector_knowledge:
            from bbsbot.games.tw2002.orientation import GameState

            state = GameState(
                context="sector_command",  # Required field
                sector=sector,
                warps=info["warps"],
                has_port=info["has_port"],
                has_planet=info["has_planet"],
            )
            self.bot.sector_knowledge.record_observation(state)
            self.bot.sector_knowledge.mark_scanned(sector)

        return info

    async def check_port(self) -> PortInfo | None:
        """Check what commodities a port trades."""
        sector = self.session.sector

        # Access port
        await self.bot.session.send("P")
        await asyncio.sleep(1.0)

        result = await self.bot.session.read(timeout_ms=2000, max_bytes=8192)
        screen = result.get("screen", "")

        if "no port" in screen.lower() or "isn't a port" in screen.lower():
            return None

        port = PortInfo(sector=sector)

        # Parse port type from screen
        # Typical format shows what port buys/sells
        screen_lower = screen.lower()

        # Check for buying (port buys = we sell)
        # Check for selling (port sells = we buy)
        if "fuel ore" in screen_lower:
            if "buying" in screen_lower and "fuel" in screen_lower.split("buying")[1][:50]:
                port.buying.append("fuel")
            if "selling" in screen_lower and "fuel" in screen_lower.split("selling")[1][:50]:
                port.selling.append("fuel")

        if "organics" in screen_lower:
            if "buying" in screen_lower:
                port.buying.append("organics")
            if "selling" in screen_lower:
                port.selling.append("organics")

        if "equipment" in screen_lower:
            if "buying" in screen_lower:
                port.buying.append("equipment")
            if "selling" in screen_lower:
                port.selling.append("equipment")

        # Determine port type from class
        type_match = re.search(r"Class\s*(\d+)", screen)
        if type_match:
            port.port_type = f"Class {type_match.group(1)}"

        # Exit port
        await self.bot.session.send("Q")
        await asyncio.sleep(0.3)

        # Store in known ports
        self.session.known_ports[sector] = port

        return port

    async def execute_trade(self) -> int:
        """Execute a trading cycle at current port. Returns profit made."""
        initial_credits = self.session.credits

        # Clear loop detection before trade attempt
        self.bot.loop_detection.reset()

        # Enter port with P command
        await self.bot.session.send("P")
        await asyncio.sleep(1.0)

        result = await self.bot.session.read(timeout_ms=2000, max_bytes=8192)
        screen = result.get("screen", "")
        screen_lower = screen.lower()

        # Check if no port
        if "no port" in screen_lower or "isn't a port" in screen_lower:
            print("    No port here!", flush=True)
            return 0

        # Check if we're at port menu (look for typical port menu indicators)
        if "port" not in screen_lower and "commerce" not in screen_lower:
            print("    Port menu not detected, recovering...", flush=True)
            await self.bot.recover()
            return 0

        # Trade (T) - enter trade mode
        print("    Entering trade menu...", flush=True)
        await self.bot.session.send("T")
        await asyncio.sleep(1.5)  # Wait longer for port menu to load

        # Handle trading prompts with better flow
        trades_made = 0
        max_trade_attempts = 20
        last_screen = ""
        stuck_count = 0
        # LLM HINT: pending_trade tracks if we entered a non-zero quantity.
        # When we skip a commodity (enter 0), TW2002 still shows price screens.
        # Without this flag, the bot accepts prices for skipped commodities.
        pending_trade = False

        for _attempt in range(max_trade_attempts):
            result = await self.bot.session.read(timeout_ms=1500, max_bytes=8192)
            screen = result.get("screen", "")
            screen_lower = screen.lower()

            # Detect stuck state
            if screen == last_screen:
                stuck_count += 1
                if stuck_count >= 3:
                    print("    [Stuck at same screen, breaking out]", flush=True)
                    break
            else:
                stuck_count = 0
            last_screen = screen

            # Check if back at sector command (done) - check LAST LINE for actual prompt
            # Only check after we've done at least 1 trade to avoid premature exit
            lines = [l.strip() for l in screen.split("\n") if l.strip()]
            if lines and trades_made > 0:
                last_line = lines[-1].lower()
                # Sector command prompt format: "Command [TL=00:00:00]:[123] (?=Help)? :"
                if "command" in last_line and "?" in last_line:
                    print("    [Back at sector command]", flush=True)
                    break

            # Check for port menu exit indicator
            if "quit" in screen_lower and "[q]" in screen_lower:
                # At main port menu, exit
                print("    [At port menu, exiting]", flush=True)
                await self.bot.session.send("Q")
                await asyncio.sleep(0.3)
                break

            # Handle quantity prompts - "how many" or "you can afford"
            if "how many" in screen_lower or "you can afford" in screen_lower:
                # Safety check - don't do more than 6 transactions per port visit
                if trades_made >= 6:
                    print(f"    [Max transactions reached ({trades_made}), exiting]")
                    break
                # Extract max amount if shown
                max_match = re.search(r"you can afford\s+(\d+)", screen_lower)
                amount = int(max_match.group(1)) if max_match else self.session.holds

                # LLM HINT: If amount is 0, we're skipping this commodity.
                # Set pending_trade accordingly so we don't accept price for skipped items.
                if amount > 0:
                    pending_trade = True
                    print(f"    Buying/selling {amount} units...", flush=True)
                else:
                    pending_trade = False
                    print("    Skipping (0 units)...", flush=True)

                await self.bot.session.send(f"{amount}\r")
                await asyncio.sleep(0.5)
                if amount > 0:
                    trades_made += 1
                continue

            # Handle "We are" buying/selling (commodity offer)
            if "we are" in screen_lower and ("buying" in screen_lower or "selling" in screen_lower):
                # Port tells us what they want - acknowledge
                await asyncio.sleep(0.3)
                continue

            # Handle price offers - look for credit amounts > 100
            # LLM HINT: Only accept prices if pending_trade is True.
            # This prevents accepting offers for commodities we skipped (entered 0).
            price_match = re.search(r"(\d{3,}[\d,]*)\s*credits", screen, re.IGNORECASE)
            if price_match and pending_trade:
                offered_price = int(price_match.group(1).replace(",", ""))
                if offered_price > 100:  # Actual price, not holds count
                    # Accept the offer (Y)
                    print(f"    Price: {offered_price:,} credits - accepting...", flush=True)
                    await self.bot.session.send("Y")
                    await asyncio.sleep(0.5)
                    pending_trade = False  # Trade complete for this commodity
                    trades_made += 1
                    continue
            elif price_match and not pending_trade:
                # LLM HINT: We see a price but didn't enter quantity. Skip it.
                print("    [Skipping price offer - no pending trade]", flush=True)
                await asyncio.sleep(0.3)
                continue

            # Handle yes/no confirmations
            if "[y/n]" in screen_lower or "(y/n)" in screen_lower:
                # Default to Y for trade confirmations
                print("    Confirming (Y)...")
                await self.bot.session.send("Y")
                await asyncio.sleep(0.3)
                continue

            # Handle single-letter menu choices (common port prompts)
            if re.search(r"\[.\]\s*\w+", screen):
                # Menu with options - check what's available
                await asyncio.sleep(0.3)
                continue

            # Handle press any key / pause
            if "press" in screen_lower or "[pause]" in screen_lower:
                await self.bot.session.send(" ")
                await asyncio.sleep(0.3)
                continue

            # Handle "enter" prompts
            if "enter" in screen_lower and "?" in screen:
                await self.bot.session.send("\r")
                await asyncio.sleep(0.3)
                continue

            # Unrecognized - wait a bit
            await asyncio.sleep(0.3)

        # Exit port if still there - send multiple Q's to escape any nested menu state
        for _ in range(3):
            await self.bot.session.send("Q\r")  # Q + Enter to exit and confirm
            await asyncio.sleep(0.3)

        # Recover to safe state (this also clears loop detection)
        await self.bot.recover()

        # Update credits - try to get fresh status
        try:
            await self.get_ship_status()
        except Exception:
            pass  # Best effort

        profit = self.session.credits - initial_credits

        if trades_made > 0:
            self.session.trades_completed += 1
            self.session.total_profit += profit
            print(f"    [Trade complete: {trades_made} transactions, profit: {profit:,}]", flush=True)

            # Track in character state
            if self.char_state:
                self.char_state.record_trade(profit)

        return profit

    async def warp_to(self, sector: int) -> bool:
        """Warp to a sector via single-hop move."""
        # Clear loop detection before warp
        self.bot.loop_detection.reset()

        # Make sure we're at sector_command first
        state = await self.bot.where_am_i()
        if state.context != "sector_command":
            print(f"    Not at sector command ({state.context}), recovering...")
            await self.bot.recover()

        current_sector = state.sector

        # Use single-hop warp (number only, not M command for direct adjacent warps)
        print(f"    Warping to sector {sector}...", flush=True)
        await self.bot.session.send(f"{sector}\r")
        await asyncio.sleep(1.5)

        # Handle any prompts during warp
        max_prompts = 8
        for i in range(max_prompts):
            result = await self.bot.session.read(timeout_ms=1500, max_bytes=8192)
            screen = result.get("screen", "")
            screen_lower = screen.lower()

            # Debug: show last line of screen
            lines = [l.strip() for l in screen.split("\n") if l.strip()]
            if lines and i < 3:
                print(f"      [warp debug {i}] last line: {lines[-1][:60]}", flush=True)

            # Check if we arrived (sector command prompt)
            if "command" in screen_lower and ("sector" in screen_lower or "?" in screen):
                break

            # Handle auto-warp confirmation
            if "auto-warp" in screen_lower or "engage" in screen_lower:
                await self.bot.session.send("Y")
                await asyncio.sleep(0.5)
                continue

            # Handle density scan results
            if "density" in screen_lower or "scan" in screen_lower:
                await self.bot.session.send(" ")
                await asyncio.sleep(0.3)
                continue

            # Handle encounters
            if "hail" in screen_lower or "attack" in screen_lower:
                # Try to avoid combat
                await self.bot.session.send("I")  # Ignore
                await asyncio.sleep(0.3)
                continue

            # Handle press any key / pause
            if "press" in screen_lower or "pause" in screen_lower:
                await self.bot.session.send(" ")
                await asyncio.sleep(0.3)
                continue

            # Handle yes/no prompts (usually agree)
            if "[y/n]" in screen_lower or "(y/n)" in screen_lower:
                await self.bot.session.send("Y")
                await asyncio.sleep(0.3)
                continue

            # Wait a bit for screen update
            await asyncio.sleep(0.3)

        # Recover to safe state
        await self.bot.recover()

        # Update position
        state = await self.bot.where_am_i()
        new_sector = state.sector

        if new_sector == sector:
            self.session.sector = sector
            print(f"    Arrived at sector {sector}", flush=True)
            return True
        elif new_sector and new_sector != current_sector:
            # We moved somewhere, even if not target
            print(f"    Now at sector {new_sector} (target was {sector})")
            self.session.sector = new_sector
            return True
        else:
            print(f"    Warp failed - still at {current_sector}", flush=True)
            return False

    async def explore_and_trade(self, max_moves: int = 50, target_credits: int = 5_000_000) -> None:
        """Main gameplay loop - explore and trade."""
        print("\n" + "=" * 60, flush=True)
        print(f"STARTING TRADING RUN (Target: {target_credits:,} credits)")
        print("=" * 60, flush=True)

        # Get accurate ship status first
        print("\n[Ship Status] Getting current stats...", flush=True)
        await self.get_ship_status()
        print(f"  Credits: {self.session.credits:,}", flush=True)
        print(f"  Turns: {self.session.turns_left}", flush=True)
        print(f"  Holds: {self.session.holds}", flush=True)
        print(f"  Sector: {self.session.sector}", flush=True)

        moves = 0
        consecutive_no_trade = 0

        while moves < max_moves and self.session.turns_left > 0 and self.session.credits < target_credits:
            moves += 1
            # Clear loop detection at start of each turn
            self.bot.loop_detection.reset()

            print(
                f"\n[Turn {moves}] Sector {self.session.sector}, "
                + f"Credits: {self.session.credits:,}, Turns: {self.session.turns_left}"
            )

            # Check if we hit target
            if self.session.credits >= target_credits:
                print(f"\n🎉 TARGET REACHED: {self.session.credits:,} credits!", flush=True)
                break

            # Scan current sector
            sector_info = await self.scan_sector()
            print(f"  Has port: {sector_info['has_port']}, Warps: {sector_info['warps']}", flush=True)

            # Trade if port available
            if sector_info["has_port"]:
                print("  Trading at port...", flush=True)
                profit = await self.execute_trade()
                print(f"  Profit: {profit:,} credits", flush=True)

                if profit > 0:
                    consecutive_no_trade = 0
                else:
                    consecutive_no_trade += 1
            else:
                consecutive_no_trade += 1

            # Update turns - assume warp costs 1 turn
            self.session.turns_left = max(0, self.session.turns_left - 1)

            # Periodically refresh full status
            if moves % 10 == 0:
                await self.get_ship_status()

            # Choose next sector
            if sector_info["warps"]:
                # Pick a warp - prefer unexplored or random
                unexplored = [w for w in sector_info["warps"] if w not in self.session.known_ports]
                if unexplored and consecutive_no_trade < 3:
                    next_sector = random.choice(unexplored)
                else:
                    # Go to known port or random
                    next_sector = random.choice(sector_info["warps"])

                await self.warp_to(next_sector)
            else:
                print("  No warps available!", flush=True)
                break

            # Check for death
            result = await self.bot.session.read(timeout_ms=500, max_bytes=4096)
            screen = result.get("screen", "").lower()
            if "destroyed" in screen or "killed" in screen or "dead" in screen:
                print("\n*** CHARACTER DIED! ***", flush=True)
                self.session.death_count += 1
                return

            await asyncio.sleep(0.2)

        print(f"\n[Trading run complete] Made {moves} moves", flush=True)

    async def play_session(self) -> None:
        """Play a full session."""
        print("\n" + "=" * 60, flush=True)
        print("TRADEWARS 2002 - PLAY TO WIN", flush=True)
        print(f"Strategy: {self.config.trading.strategy}", flush=True)
        print(f"Target: {self.config.session.target_credits:,} credits", flush=True)
        print("=" * 60, flush=True)

        max_characters = self.config.multi_character.max_characters
        target_credits = self.config.session.target_credits

        while self.character_num <= max_characters:
            # Start game
            if not await self.start_game():
                print(f"\nFailed to start game with character {self.character_num}", flush=True)
                self.character_num += 1
                continue

            # Play until we hit target or run out of turns
            try:
                await self.explore_and_trade(
                    max_moves=self.config.session.max_turns_per_session,
                    target_credits=target_credits,
                )
            except Exception as e:
                print(f"\nError during gameplay: {e}", flush=True)
                import traceback

                traceback.print_exc()

            # Check if died or need to restart
            if self.session.death_count > 0 or self.session.credits < 100:
                reason = "Death" if self.session.death_count > 0 else "Low credits"
                print(f"\n[{reason}] Starting new character...", flush=True)
                self.character_num += 1

                # Handle death with multi-character manager (for knowledge inheritance)
                if self.char_state and self.multi_char and self.session.death_count > 0:
                    self.char_state = self.multi_char.handle_death(self.char_state)
                elif self.char_state and self.multi_char:
                    # Save state if just low credits
                    self.multi_char.save_character(self.char_state)

                # Close old session
                if self.bot and self.bot.session_id:
                    with contextlib.suppress(BaseException):
                        await self.bot.session_manager.close_session(self.bot.session_id)

                # Reset session but keep stats
                old_profit = self.session.total_profit
                old_trades = self.session.trades_completed
                old_deaths = self.session.death_count
                self.session = GameSession()
                self.session.total_profit = old_profit
                self.session.trades_completed = old_trades
                self.session.death_count = old_deaths
            elif self.session.credits >= target_credits:
                print(f"\n🎉🎉🎉 WON THE GAME! {self.session.credits:,} credits! 🎉🎉🎉", flush=True)
                break
            else:
                # Continue playing if we have credits and turns
                if self.session.turns_left > 0:
                    continue
                break

        # Final report
        await self.report()

        # Cleanup
        if self.bot and self.bot.session_id:
            with contextlib.suppress(BaseException):
                await self.bot.session_manager.close_session(self.bot.session_id)

    async def report(self) -> None:
        """Print session report."""
        print("\n" + "=" * 60, flush=True)
        print("SESSION REPORT", flush=True)
        print("=" * 60, flush=True)
        print(f"  Characters used: {self.character_num}", flush=True)
        print(f"  Deaths: {self.session.death_count}", flush=True)
        print(f"  Trades completed: {self.session.trades_completed}", flush=True)
        print(f"  Total profit: {self.session.total_profit:,} credits", flush=True)
        print(f"  Final credits: {self.session.credits:,}", flush=True)
        print(f"  Known ports: {len(self.session.known_ports)}")
        print("=" * 60, flush=True)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Play TW2002 to win - automated trading bot")
    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        help="Path to YAML configuration file",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="localhost",
        help="Server host (default: localhost)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=2002,
        help="Server port (default: 2002)",
    )
    return parser.parse_args()


async def main():
    args = parse_args()

    # Load config
    if args.config:
        config = load_config(args.config)
        # Override host/port from args if specified
        if args.host != "localhost":
            config.connection.host = args.host
        if args.port != 2002:
            config.connection.port = args.port
    else:
        config = BotConfig()
        config.connection.host = args.host
        config.connection.port = args.port

    player = TradeWarPlayer(
        host=config.connection.host,
        port=config.connection.port,
        config=config,
    )
    await player.play_session()


if __name__ == "__main__":
    asyncio.run(main())
