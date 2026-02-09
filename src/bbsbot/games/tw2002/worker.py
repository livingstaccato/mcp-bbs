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
            # 0 = auto-detect server maximum (persistent mode)
            turns_max = getattr(self.config, 'session', {})
            if hasattr(turns_max, 'max_turns_per_session'):
                turns_max = turns_max.max_turns_per_session
            else:
                turns_max = 0  # Default: auto-detect server max

            # Map game context to human-readable activity
            # CRITICAL: Only use game_state.context if we're actually IN THE GAME (sector > 0)
            # Otherwise we show stale activities like "EXPLORING" when stuck at login
            activity = "INITIALIZING"
            in_game = self.current_sector and self.current_sector > 0

            if self.game_state and in_game:
                # Bot is IN the game - use context for activity
                context = getattr(self.game_state, "context", None)
                if context:
                    if context == "combat":
                        activity = "BATTLING"
                    elif context in ("port_trading", "bank", "ship_shop", "port_menu"):
                        activity = "TRADING"
                    elif context in ("navigation", "warp", "sector_command", "planet_command", "citadel_command"):
                        activity = "EXPLORING"
                    elif "menu" in context.lower() or "selection" in context.lower():
                        activity = "IN_GAME_MENU"
                    else:
                        activity = context.upper()
                else:
                    activity = "IN_GAME"
            else:
                # Bot NOT in game yet - must be in login/connection phase
                if hasattr(self, 'session') and self.session:
                    # Check orientation phase for more specific status
                    orient_phase = getattr(self, '_orient_phase', '')
                    if orient_phase:
                        activity = f"LOGIN_{orient_phase.upper()}"
                    else:
                        activity = "LOGGING_IN"
                else:
                    activity = "CONNECTING"

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
            # ONLY show "ORIENTING" if actually in game (sector > 0)
            orient_step = getattr(self, '_orient_step', 0)
            orient_max = getattr(self, '_orient_max', 0)
            orient_phase = getattr(self, '_orient_phase', '')
            if orient_phase and in_game:
                # Bot is in game AND orienting - show orient status
                if orient_step > 0 and orient_max > 0:
                    activity = f"ORIENTING: Step {orient_step}/{orient_max}"
                else:
                    # Map phase names to readable strings
                    phase_names = {
                        "starting": "Initializing",
                        "gather": "Gathering state",
                        "safe_state": "Finding safe prompt",
                        "blank_wake": "Waking connection",
                        "failed": "Recovering",  # Transient issue, bot recovers
                    }
                    phase_display = phase_names.get(orient_phase, orient_phase.title())
                    activity = f"ORIENTING: {phase_display}"
            elif orient_phase and not in_game:
                # Bot orienting during login - show LOGIN status, not ORIENTING
                activity = "LOGGING_IN"

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

            # Always send credits, even if 0 (only skip if negative sentinel)
            status_data["credits"] = max(0, credits)  # Never send -1

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

        # If this is a loop/orientation error, run diagnostics
        error_str = str(error).lower()
        if any(x in error_str for x in ["loop", "menu", "orientation", "stuck"]):
            try:
                from bbsbot.diagnostics.stuck_bot_analyzer import StuckBotAnalyzer
                from bbsbot.llm.manager import LLMManager
                from bbsbot.llm.config import LLMConfig, OllamaConfig
                import json
                from pathlib import Path

                llm_config = LLMConfig(
                    provider="ollama",
                    ollama=OllamaConfig(model="gemma3", timeout_seconds=30),
                )
                analyzer = StuckBotAnalyzer(LLMManager(llm_config))

                # Get loop history from loop detector
                loop_history = []
                if hasattr(self, 'loop_detection') and hasattr(self.loop_detection, 'alternation_history'):
                    loop_history = self.loop_detection.alternation_history

                diagnosis = await analyzer.analyze_stuck_bot(
                    bot_id=self.bot_id,
                    error_type=type(error).__name__,
                    recent_screens=self.diagnostic_buffer.get("recent_screens", []),
                    recent_prompts=self.diagnostic_buffer.get("recent_prompts", []),
                    loop_history=loop_history,
                    exit_reason=exit_reason,
                )

                # Log diagnostic results
                logger.info("llm_diagnosis", bot_id=self.bot_id, diagnosis=diagnosis)

                # Save to diagnostic log file
                diagnostic_file = Path(f"logs/diagnostics/{self.bot_id}_diagnosis.json")
                diagnostic_file.parent.mkdir(parents=True, exist_ok=True)
                with open(diagnostic_file, "w") as f:
                    json.dump({
                        "timestamp": time.time(),
                        "bot_id": self.bot_id,
                        "error": str(error),
                        "diagnosis": diagnosis,
                    }, f, indent=2)

                print(f"  🔍 LLM Diagnosis saved to: {diagnostic_file}")

            except Exception as diag_error:
                logger.warning(f"Diagnostic analysis failed: {diag_error}")

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
                # Don't use turns_left (it's 0 at completion), keep existing turns_max
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
