#!/usr/bin/env python3
"""Multi-bot coordinated TW2002 gameplay.

Spawns 5 coordinated bots that:
- Run simultaneously with separate connections
- Share knowledge via shared state
- Execute different roles (trader, scout, etc.)
- Run continuously until stopped
"""

import asyncio
import json
import logging
import os
import signal
import sys
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from bbsbot.paths import default_knowledge_root
from bbsbot.core.session_manager import SessionManager
from bbsbot.tw2002.config import BotConfig, load_config
from bbsbot.tw2002.bot import TradingBot
from bbsbot.tw2002.multi_character import MultiCharacterManager
from bbsbot.tw2002.character import CharacterState
from bbsbot.tw2002 import login, orientation, io, trading

logger = logging.getLogger(__name__)


class BotRole(Enum):
    """Different bot roles for coordination."""
    TRADER = "trader"           # Primary trader
    HAULER = "hauler"          # High-capacity trader
    BANKER = "banker"           # Trader who banks frequently
    UPGRADER = "upgrader"       # Trader who upgrades ship
    EXPLORER = "explorer"       # Trader who explores new routes


@dataclass
class SharedState:
    """Shared state for bot coordination."""

    # Coordination data
    profitable_routes: list[dict] = field(default_factory=list)
    danger_sectors: set[int] = field(default_factory=set)
    port_locations: dict[int, dict] = field(default_factory=dict)
    unexplored_sectors: set[int] = field(default_factory=set)

    # Bot status
    active_bots: dict[str, dict] = field(default_factory=dict)

    # Stats
    total_credits: int = 0
    total_trades: int = 0
    sectors_mapped: int = 0

    # Corporation
    corporation_name: str = "BotArmy"
    corporation_created: bool = False

    # File path for persistence
    state_file: Path | None = None

    def save(self):
        """Save shared state to disk."""
        if not self.state_file:
            return

        data = {
            "profitable_routes": self.profitable_routes,
            "danger_sectors": list(self.danger_sectors),
            "port_locations": self.port_locations,
            "unexplored_sectors": list(self.unexplored_sectors),
            "active_bots": self.active_bots,
            "total_credits": self.total_credits,
            "total_trades": self.total_trades,
            "sectors_mapped": self.sectors_mapped,
            "timestamp": time.time(),
        }

        self.state_file.write_text(json.dumps(data, indent=2))

    @classmethod
    def load(cls, state_file: Path) -> "SharedState":
        """Load shared state from disk."""
        state = cls(state_file=state_file)

        if not state_file.exists():
            return state

        try:
            data = json.loads(state_file.read_text())
            state.profitable_routes = data.get("profitable_routes", [])
            state.danger_sectors = set(data.get("danger_sectors", []))
            state.port_locations = data.get("port_locations", {})
            state.unexplored_sectors = set(data.get("unexplored_sectors", []))
            state.active_bots = data.get("active_bots", {})
            state.total_credits = data.get("total_credits", 0)
            state.total_trades = data.get("total_trades", 0)
            state.sectors_mapped = data.get("sectors_mapped", 0)
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Failed to load shared state: {e}")

        return state


class CoordinatedBot:
    """A single bot in the coordinated swarm."""

    def __init__(
        self,
        bot_id: int,
        role: BotRole,
        shared_state: SharedState,
        config: BotConfig,
        data_dir: Path,
    ):
        self.bot_id = bot_id
        self.role = role
        self.shared_state = shared_state
        self.config = config
        self.data_dir = data_dir

        self.character_name = f"{role.value}_{bot_id:02d}"
        self.running = False
        self.session_manager = SessionManager()
        self.session_id: str | None = None
        self.bot: TradingBot | None = None
        self.character: CharacterState | None = None

        # Role-specific behavior counters
        self.actions_count = 0
        self.last_coordination_check = time.time()

    async def connect(self):
        """Connect to game server."""
        host = os.getenv("BBSBOT_TW_HOST", "localhost")
        port = int(os.getenv("BBSBOT_TW_PORT", "2002"))

        logger.info(f"[{self.character_name}] Connecting to {host}:{port}")

        self.session_id = await self.session_manager.create_session(
            host=host,
            port=port,
            cols=80,
            rows=25,
            term="ANSI",
            timeout=10.0,
        )

        self.bot = TradingBot(character_name=self.character_name, config=self.config)
        self.bot.session_id = self.session_id
        self.bot.session = await self.session_manager.get_session(self.session_id)

        knowledge_root = default_knowledge_root()
        await self.session_manager.enable_learning(
            self.session_id,
            knowledge_root,
            namespace="tw2002"
        )

        logger.info(f"[{self.character_name}] Connected successfully")

    async def login_and_setup(self):
        """Login and character setup."""
        logger.info(f"[{self.character_name}] Starting login...")

        character_password = os.getenv("BBSBOT_TW_PASSWORD", self.character_name)
        game_password = os.getenv("BBSBOT_TW_GAME_PASSWORD", "game")

        # Use login module to handle full login flow
        await login.login_sequence(
            self.bot,
            username=self.character_name,
            character_password=character_password,
            game_password=game_password,
        )

        logger.info(f"[{self.character_name}] Login complete")

        # Initialize orientation and sector knowledge
        from bbsbot.tw2002.orientation import SectorKnowledge, GameState
        self.bot.sector_knowledge = SectorKnowledge(self.data_dir)

        # Initialize game state
        self.bot.game_state = await orientation.orient(self.bot, self.bot.sector_knowledge)

        # Initialize trading strategy for ALL bots (they all trade now)
        self.bot.init_strategy()

        logger.info(f"[{self.character_name}] Ready for action")

    async def run_behavior_loop(self):
        """Main behavior loop - trade until out of turns."""
        self.running = True

        try:
            logger.info(f"[{self.character_name}] Starting trading loop")

            # ALL BOTS TRADE - focus on earning credits!
            while self.running:
                # Check coordination
                if time.time() - self.last_coordination_check > 30:
                    await self.coordinate()
                    self.last_coordination_check = time.time()

                # Check if out of turns
                if self.bot.game_state and hasattr(self.bot.game_state, 'turns'):
                    if self.bot.game_state.turns is not None and self.bot.game_state.turns <= 0:
                        logger.info(f"[{self.character_name}] Out of turns! Final credits: {self.bot.current_credits}")
                        break

                # EVERYONE TRADES to earn credits
                try:
                    await self.trading_behavior()
                    self.actions_count += 1

                except Exception as e:
                    logger.warning(f"[{self.character_name}] Trade error: {e}")
                    await asyncio.sleep(3)

                await asyncio.sleep(1)

        except asyncio.CancelledError:
            logger.info(f"[{self.character_name}] Shutting down gracefully")
            raise
        except Exception as e:
            logger.error(f"[{self.character_name}] Fatal error: {e}", exc_info=True)
            raise

    async def coordinate(self):
        """Coordinate with other bots via shared state."""
        # Get turns if available
        turns = None
        if self.bot and self.bot.game_state and hasattr(self.bot.game_state, 'turns'):
            turns = self.bot.game_state.turns

        # Update bot status
        self.shared_state.active_bots[self.character_name] = {
            "role": self.role.value,
            "actions": self.actions_count,
            "sector": self.bot.current_sector if self.bot else None,
            "credits": self.bot.current_credits if self.bot else 0,
            "turns": turns,
            "last_seen": time.time(),
        }

        # Save state
        self.shared_state.save()

        if turns is not None:
            logger.debug(f"[{self.character_name}] Actions: {self.actions_count}, Turns: {turns}")

    async def trading_behavior(self):
        """Use proper trading system with full prompt handling."""
        try:
            # Use the actual trading cycle which handles all prompts correctly
            result = await trading.single_trading_cycle(self.bot)

            if result and result.get("success"):
                profit = result.get("profit", 0)
                if profit > 0:
                    logger.info(f"[{self.character_name}] 💰 Profit: {profit:,} credits")

                # Update shared state
                self.shared_state.total_trades += 1
                if profit > 0:
                    self.shared_state.total_credits += profit

        except Exception as e:
            logger.debug(f"[{self.character_name}] Trade attempt: {e}")

    async def shutdown(self):
        """Graceful shutdown."""
        self.running = False
        if self.session_id:
            await self.session_manager.close_session(self.session_id)
        logger.info(f"[{self.character_name}] Shut down complete")


class MultiBotCoordinator:
    """Coordinates multiple bots."""

    def __init__(self, num_bots: int = 5):
        self.num_bots = num_bots
        self.bots: list[CoordinatedBot] = []
        self.data_dir = Path.home() / ".bbsbot_multibot"
        self.data_dir.mkdir(exist_ok=True)

        # Load config (use default config if no file exists)
        config_path = Path("config/tw2002.yml")
        if config_path.exists():
            self.config = load_config(config_path)
        else:
            # Use default config
            self.config = BotConfig()

        # Shared state
        state_file = self.data_dir / "shared_state.json"
        self.shared_state = SharedState.load(state_file)
        self.shared_state.state_file = state_file

        # Shutdown handling
        self.shutdown_event = asyncio.Event()

    def setup_signal_handlers(self):
        """Setup graceful shutdown on Ctrl+C."""
        def signal_handler(sig, frame):
            logger.info("\n🛑 Shutdown signal received, stopping all bots...")
            self.shutdown_event.set()

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    async def spawn_bots(self):
        """Spawn all coordinated bots - ALL TRADERS!"""
        # All bots are traders now, just with different specialties
        base_roles = [
            BotRole.TRADER,
            BotRole.HAULER,
            BotRole.BANKER,
            BotRole.UPGRADER,
            BotRole.EXPLORER,
        ]

        # Extend roles to match num_bots by cycling
        roles = []
        for i in range(self.num_bots):
            roles.append(base_roles[i % len(base_roles)])

        for i, role in enumerate(roles, 1):
            bot = CoordinatedBot(
                bot_id=i,
                role=role,
                shared_state=self.shared_state,
                config=self.config,
                data_dir=self.data_dir,
            )
            self.bots.append(bot)
            logger.info(f"✓ Created bot #{i}: {bot.character_name} ({role.value})")

    async def run_bot(self, bot: CoordinatedBot):
        """Run a single bot lifecycle."""
        try:
            await bot.connect()
            await bot.login_and_setup()
            await bot.run_behavior_loop()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Bot {bot.character_name} failed: {e}", exc_info=True)
        finally:
            await bot.shutdown()

    async def monitor_and_report(self):
        """Periodically report status."""
        while not self.shutdown_event.is_set():
            await asyncio.sleep(30)

            print("\n" + "="*80)
            print("MULTI-BOT STATUS REPORT")
            print("="*80)

            for bot_name, status in self.shared_state.active_bots.items():
                age = time.time() - status.get("last_seen", time.time())
                print(
                    f"  {bot_name:15s} | "
                    f"Role: {status['role']:10s} | "
                    f"Actions: {status['actions']:4d} | "
                    f"Sector: {status.get('sector', '?'):4s} | "
                    f"Credits: {status.get('credits', 0):8d} | "
                    f"Last seen: {age:.0f}s ago"
                )

            print(f"\n  Total Trades: {self.shared_state.total_trades}")
            print(f"  Total Credits: {self.shared_state.total_credits}")
            print(f"  Sectors Mapped: {self.shared_state.sectors_mapped}")
            print("="*80 + "\n")

    async def run(self):
        """Run the multi-bot system."""
        print("\n" + "="*80)
        print("TRADE WARS 2002 - MULTI-BOT COORDINATED GAMEPLAY")
        print("="*80)
        print(f"\nSpawning {self.num_bots} coordinated bots...")
        print("Press Ctrl+C to stop all bots gracefully\n")

        await self.spawn_bots()

        # Start all bots concurrently
        tasks = [
            asyncio.create_task(self.run_bot(bot))
            for bot in self.bots
        ]

        # Add monitor task
        monitor_task = asyncio.create_task(self.monitor_and_report())

        try:
            # Wait for shutdown signal
            await self.shutdown_event.wait()

            # Cancel all tasks
            for task in tasks + [monitor_task]:
                task.cancel()

            # Wait for clean shutdown
            await asyncio.gather(*tasks, monitor_task, return_exceptions=True)

        except Exception as e:
            logger.error(f"Coordinator error: {e}", exc_info=True)
        finally:
            print("\n✓ All bots shut down successfully\n")


async def main():
    """Main entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    # Allow override via command line
    import sys
    num_bots = int(sys.argv[1]) if len(sys.argv) > 1 else 5

    coordinator = MultiBotCoordinator(num_bots=num_bots)
    coordinator.setup_signal_handlers()
    await coordinator.run()


if __name__ == "__main__":
    asyncio.run(main())
