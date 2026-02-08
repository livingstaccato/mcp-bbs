"""Bot worker process entry point for swarm management.

Runs a single bot instance and reports status to swarm manager.
"""

from __future__ import annotations

import asyncio
import os

import click
import httpx
from pathlib import Path

from bbsbot.games.tw2002.bot import TradingBot
from bbsbot.games.tw2002.config import BotConfig
from bbsbot.logging import get_logger

logger = get_logger(__name__)

from bbsbot.defaults import MANAGER_URL as MANAGER_URL_DEFAULT


class WorkerBot(TradingBot):
    """Bot worker with manager communication."""

    def __init__(self, bot_id: str, config: BotConfig, manager_url: str):
        """Initialize worker bot.

        Args:
            bot_id: Unique bot identifier
            config: Bot configuration
            manager_url: URL of swarm manager
        """
        super().__init__(character_name=bot_id, config=config)
        self.bot_id = bot_id
        self.manager_url = manager_url
        self._http_client = httpx.AsyncClient(timeout=10)
        # Activity tracking
        self.current_action: str | None = None
        self.current_action_time: float = 0
        self.recent_actions: list[dict] = []
        self.ai_activity: str | None = None  # AI reasoning for dashboard
        # Hijack support (paused automation + read pump)
        self._hijacked: bool = False
        self._hijack_event: asyncio.Event = asyncio.Event()
        self._hijack_event.set()  # not hijacked by default
        self._hijack_pump_task: asyncio.Task | None = None

    async def register_with_manager(self) -> None:
        """Register this bot with the swarm manager."""
        try:
            await self._http_client.post(
                f"{self.manager_url}/bot/{self.bot_id}/register",
                json={"pid": os.getpid()},
            )
            logger.info(f"Registered with manager: {self.bot_id}")
        except Exception as e:
            logger.warning(f"Failed to register with manager: {e}")

    async def report_status(self) -> None:
        """Report current status to manager."""
        try:
            # Use game_state credits if current_credits not updated
            credits = self.current_credits
            if credits == 0 and self.game_state and self.game_state.credits:
                credits = self.game_state.credits

            # Determine turns_max from config if available
            turns_max = getattr(self.config, 'session', {})
            if hasattr(turns_max, 'max_turns_per_session'):
                turns_max = turns_max.max_turns_per_session
            else:
                turns_max = 500  # Default fallback

            # Map game context to human-readable activity
            activity = "INITIALIZING"
            if self.game_state:
                context = getattr(self.game_state, "context", None)
                if context:
                    if context == "combat":
                        activity = "BATTLING"
                    elif context in ("port_trading", "bank", "ship_shop", "port_menu"):
                        activity = "TRADING"
                    elif context in ("navigation", "warp", "sector_command", "planet_command", "citadel_command"):
                        activity = "EXPLORING"
                    elif "menu" in context.lower() or "selection" in context.lower():
                        # Generic menu/selection context (game picker, character select, etc)
                        activity = "SELECTING"
                    else:
                        activity = context.upper()
                else:
                    # game_state exists but context is None - likely during login
                    activity = "CONNECTING"
            else:
                # No game_state yet - check if we have a session
                if hasattr(self, 'session') and self.session:
                    activity = "LOGGING_IN"

            # Override with AI reasoning if available
            if self.ai_activity:
                activity = self.ai_activity
                self.ai_activity = None  # Clear after reporting

            if self._hijacked:
                activity = "HIJACKED"

            # Extract character/ship info from game state
            # Always include username, ship_level, ship_name even if None
            # This helps the dashboard track character progression
            username = None
            ship_level = None
            ship_name = None

            if self.game_state:
                # Get player name from game state, fall back to character name
                username = getattr(self.game_state, "player_name", None) or self.character_name
                # Get ship type (e.g., "Merchant Cruiser", "Scout Ship")
                ship_level = getattr(self.game_state, "ship_type", None)
                # Get custom ship name (e.g., "SS Enterprise", "The Swift Venture")
                ship_name = getattr(self.game_state, "ship_name", None)
            else:
                # If no game_state yet, still use character_name as fallback username
                username = self.character_name

            # Determine actual state from session connectivity
            connected = (
                hasattr(self, 'session')
                and self.session is not None
                and hasattr(self.session, 'is_connected')
                and self.session.is_connected()
            )
            actual_state = "running" if connected else "disconnected"
            if not connected:
                activity = "DISCONNECTED"

            # Orient progress (set by orientation.py _set_orient_progress)
            orient_step = getattr(self, '_orient_step', 0)
            orient_max = getattr(self, '_orient_max', 0)
            orient_phase = getattr(self, '_orient_phase', '')
            if orient_phase:
                # Show meaningful phase instead of confusing (0/0)
                if orient_step > 0 and orient_max > 0:
                    activity = f"ORIENTING: Step {orient_step}/{orient_max}"
                else:
                    # Map phase names to readable strings
                    phase_names = {
                        "starting": "Initializing",
                        "gather": "Gathering state",
                        "safe_state": "Finding safe prompt",
                        "blank_wake": "Waking connection",
                        "failed": "Failed",
                    }
                    phase_display = phase_names.get(orient_phase, orient_phase.title())
                    activity = f"ORIENTING: {phase_display}"

            # Check if AI strategy is thinking (waiting for LLM response)
            if self.strategy and hasattr(self.strategy, '_is_thinking') and self.strategy._is_thinking:
                activity = "THINKING"

            # Build status update dict
            status_data = {
                "sector": self.current_sector or 0,
                "turns_executed": self.turns_used,
                "turns_max": turns_max,
                "state": actual_state,
                "last_action": self.current_action,
                "last_action_time": self.current_action_time,
                "activity_context": activity,
                "orient_step": orient_step,
                "orient_max": orient_max,
                "orient_phase": orient_phase,
                "recent_actions": self.recent_actions[-10:],  # Last 10 actions
            }

            # Only include credits if > 0 (prevents overwriting good data during reconnect)
            if credits > 0:
                status_data["credits"] = credits

            # Only include username/ship_level/ship_name if they have values
            # This preserves previously-known values in the manager
            if username:
                status_data["username"] = username
            if ship_level and ship_level not in ("0", "None", ""):
                status_data["ship_level"] = ship_level
            if ship_name and ship_name not in ("0", "None", ""):
                status_data["ship_name"] = ship_name

            await self._http_client.post(
                f"{self.manager_url}/bot/{self.bot_id}/status",
                json=status_data,
            )
        except Exception as e:
            logger.debug(f"Failed to report status: {e}")

    async def await_if_hijacked(self) -> None:
        """Block automation while the dashboard is hijacking this bot."""
        await self._hijack_event.wait()

    async def set_hijacked(self, enabled: bool) -> None:
        """Enable/disable hijack mode (pause automation + run read pump)."""
        if enabled == self._hijacked:
            return
        self._hijacked = enabled

        if enabled:
            self._hijack_event.clear()

            async def _pump() -> None:
                # Keep pulling from transport so terminal keeps updating while hijacked.
                try:
                    while self._hijacked and self.session and self.session.is_connected():
                        await self.session.read(timeout_ms=250, max_bytes=8192)
                        await asyncio.sleep(0.05)
                except asyncio.CancelledError:
                    return
                except Exception:
                    return

            self._hijack_pump_task = asyncio.create_task(_pump())
        else:
            self._hijack_event.set()
            if self._hijack_pump_task is not None:
                self._hijack_pump_task.cancel()
                try:
                    await self._hijack_pump_task
                except asyncio.CancelledError:
                    pass
                self._hijack_pump_task = None

    async def start_status_reporter(self, interval: float = 5.0) -> None:
        """Start background task to report status periodically."""
        self._reporting = True

        async def _report_loop():
            while self._reporting:
                await self.report_status()
                await asyncio.sleep(interval)

        self._report_task = asyncio.create_task(_report_loop())

    async def stop_status_reporter(self) -> None:
        """Stop the background status reporter."""
        self._reporting = False
        if hasattr(self, "_report_task"):
            self._report_task.cancel()
            try:
                await self._report_task
            except asyncio.CancelledError:
                pass

    def log_action(self, action: str, sector: int, details: str | None = None, result: str = "pending") -> None:
        """Log a bot action for the action feed."""
        import time
        action_entry = {
            "time": time.time(),
            "action": action,
            "sector": sector,
            "details": details,
            "result": result,
        }
        self.recent_actions.append(action_entry)
        # Keep only last 10 actions
        if len(self.recent_actions) > 10:
            self.recent_actions = self.recent_actions[-10:]

    async def report_error(self, error: Exception, exit_reason: str = "exception") -> None:
        """Report detailed error information to manager."""
        import time
        try:
            await self._http_client.post(
                f"{self.manager_url}/bot/{self.bot_id}/status",
                json={
                    "state": "error",
                    "error_message": str(error),
                    "error_type": type(error).__name__,
                    "error_timestamp": time.time(),
                    "exit_reason": exit_reason,
                    "last_action": self.current_action,
                    "recent_actions": self.recent_actions[-10:],
                },
            )
        except Exception as e:
            logger.debug(f"Failed to report error: {e}")

    async def cleanup(self) -> None:
        """Clean up resources."""
        await self.stop_status_reporter()
        await self.set_hijacked(False)
        await self._http_client.aclose()


async def _run_worker(config: str, bot_id: str, manager_url: str) -> None:
    """Run worker bot async.

    Args:
        config: Path to bot config YAML
        bot_id: Unique bot ID
        manager_url: URL of swarm manager
    """
    from bbsbot.games.tw2002.character import CharacterState

    config_path = Path(config)
    logger.info(f"Loading config: {config_path}")

    import yaml

    with open(config_path) as f:
        config_dict = yaml.safe_load(f)

    config_obj = BotConfig(**config_dict)

    worker = WorkerBot(bot_id, config_obj, manager_url)
    term_bridge = None

    try:
        # Register with manager
        await worker.register_with_manager()

        # Connect to game server
        logger.info(
            f"Connecting to {config_obj.connection.host}:"
            f"{config_obj.connection.port}"
        )
        await worker.connect(
            host=config_obj.connection.host,
            port=config_obj.connection.port,
        )

        # Optional: connect terminal bridge (best-effort).
        try:
            from bbsbot.swarm.term_bridge import TermBridge

            term_bridge = TermBridge(worker, bot_id=bot_id, manager_url=manager_url)
            term_bridge.attach_session()
            await term_bridge.start()
        except Exception as e:
            logger.warning(f"Terminal bridge disabled: {e}")

        # Login sequence
        logger.info("Starting login sequence")
        await worker.login_sequence(
            game_password=config_obj.connection.game_password,
            character_password=(
                config_obj.connection.character_password
                or config_obj.character.password
            ),
            username=config_obj.connection.username or bot_id,
        )
        logger.info(
            f"Login successful - Sector {worker.current_sector}, "
            f"Credits {worker.current_credits}"
        )

        # Initialize knowledge and strategy (must happen after login)
        game_letter = config_obj.connection.game_letter or worker.last_game_letter
        worker.init_knowledge(
            config_obj.connection.host, config_obj.connection.port, game_letter
        )
        worker.init_strategy()

        # Report post-login status and start periodic reporting
        await worker.report_status()
        await worker.start_status_reporter(interval=5.0)

        # Create character state for trading loop
        char_state = CharacterState(name=bot_id)

        # Run trading loop using cli_impl (handles orient→strategy cycle)
        from bbsbot.games.tw2002.cli_impl import run_trading_loop

        await run_trading_loop(worker, config_obj, char_state)

    except Exception as e:
        logger.error(f"Bot worker error: {e}", exc_info=True)
        # Report detailed error to manager
        await worker.report_error(e, exit_reason="exception")
    finally:
        # Stop periodic reporter first (prevents stale updates during shutdown)
        await worker.stop_status_reporter()
        # Report final completed state WITH ALL STATS before disconnecting
        try:
            final_status = {
                "state": "completed",
                "activity_context": "FINISHED",
                "sector": worker.current_sector or 0,
                "credits": worker.current_credits or 0,
                "turns_executed": worker.turns_used,
                "exit_reason": "target_reached",
            }
            # Include game state stats if available
            if worker.game_state:
                final_status["turns_max"] = worker.game_state.turns_left or 0
                if hasattr(worker.game_state, "player_name") and worker.game_state.player_name:
                    final_status["username"] = worker.game_state.player_name
                if hasattr(worker.game_state, "ship_type") and worker.game_state.ship_type:
                    final_status["ship_level"] = worker.game_state.ship_type
                if hasattr(worker.game_state, "ship_name") and worker.game_state.ship_name:
                    final_status["ship_name"] = worker.game_state.ship_name

            await worker._http_client.post(
                f"{worker.manager_url}/bot/{worker.bot_id}/status",
                json=final_status,
            )
        except Exception:
            pass
        # Disconnect BBS session so the node is freed immediately
        try:
            await worker.disconnect()
        except Exception:
            pass
        if term_bridge is not None:
            try:
                await term_bridge.stop()
            except Exception:
                pass
        await worker.cleanup()


@click.command()
@click.option(
    "--config",
    type=click.Path(exists=True),
    required=True,
    help="Path to bot config file",
)
@click.option(
    "--bot-id",
    required=True,
    help="Unique bot identifier",
)
@click.option(
    "--manager-url",
    default=MANAGER_URL_DEFAULT,
    help="Swarm manager URL",
)
def main(config: str, bot_id: str, manager_url: str) -> None:
    """Run a bot worker process."""
    try:
        asyncio.run(_run_worker(config, bot_id, manager_url))
    except Exception as e:
        logger.error(f"Bot worker fatal: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
