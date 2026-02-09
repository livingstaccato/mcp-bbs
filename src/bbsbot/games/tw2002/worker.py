"""Bot worker process entry point for swarm management.

Runs a single bot instance and reports status to swarm manager.
"""

from __future__ import annotations

import asyncio
import os

import click
import httpx
from pathlib import Path
import time

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
        # Hijack support (paused automation only; Session reader pump always runs)
        self._hijacked: bool = False
        self._hijack_event: asyncio.Event = asyncio.Event()
        self._hijack_event.set()  # not hijacked by default
        # "Step" support: allow a bounded number of hijack checkpoints to pass.
        # The trading loop calls await_if_hijacked() twice per turn (top-of-loop + pre-action),
        # so one user "Step" grants 2 checkpoint passes by default.
        self._hijack_step_tokens: int = 0
        # Notify manager on screen changes so dashboard activity tracks screens.
        self._screen_change_event: asyncio.Event = asyncio.Event()
        self._screen_change_task: asyncio.Task | None = None
        self._last_seen_screen_hash: str = ""

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
            # Always prefer game_state credits (source of truth) over cached current_credits
            # Fallback to current_credits only if game_state unavailable
            credits = 0
            if self.game_state and self.game_state.credits:
                credits = self.game_state.credits
            elif self.current_credits:
                credits = self.current_credits

            # Determine turns_max from config if available
            # 0 = auto-detect server maximum (persistent mode)
            turns_max = getattr(self.config, 'session', {})
            if hasattr(turns_max, 'max_turns_per_session'):
                turns_max = turns_max.max_turns_per_session
            else:
                turns_max = 0  # Default: auto-detect server max

            # CRITICAL FIX: Use CURRENT screen for activity detection, not stale game_state
            # This ensures activity always matches what's actually on screen
            activity = "INITIALIZING"
            current_screen = ""
            current_context = "unknown"

            # Get current screen from session
            if hasattr(self, 'session') and self.session:
                try:
                    current_screen = self.session.get_screen()
                except Exception:
                    current_screen = ""

            # Detect REAL-TIME context from current screen
            if current_screen.strip():
                from bbsbot.games.tw2002.orientation.detection import detect_context
                current_context = detect_context(current_screen)

                # Map detected context to human-readable activity
                if current_context == "sector_command":
                    activity = "EXPLORING"
                elif current_context in ("port_menu", "port_trading"):
                    activity = "TRADING"
                elif current_context in ("bank", "ship_shop", "hardware_shop"):
                    activity = "SHOPPING"
                elif current_context == "combat":
                    activity = "BATTLING"
                elif current_context == "corporate_listings":
                    activity = "CORPORATE_LISTINGS_MENU"
                elif current_context in ("planet_command", "citadel_command"):
                    activity = "ON_PLANET"
                elif current_context == "pause":
                    activity = "PAUSED"
                elif current_context == "menu":
                    # Check if it's game selection menu (sector is None means not in game yet)
                    if not self.current_sector or self.current_sector == 0:
                        activity = "GAME_SELECTION_MENU"
                    else:
                        activity = "IN_GAME_MENU"
                elif current_context == "unknown":
                    # Fallback: check if in game
                    in_game = self.current_sector and self.current_sector > 0
                    activity = "IN_GAME" if in_game else "LOGGING_IN"
                else:
                    # Any other context, show it verbatim
                    activity = current_context.upper()
            else:
                # No screen content - must be connecting/disconnected
                if hasattr(self, 'session') and self.session and self.session.is_connected():
                    activity = "CONNECTING"
                else:
                    activity = "DISCONNECTED"

            # Orient progress tracking for debugging
            orient_step = getattr(self, '_orient_step', 0)
            orient_max = getattr(self, '_orient_max', 0)
            orient_phase = getattr(self, '_orient_phase', '')

            # CRITICAL: Do NOT override activity with "ORIENTING" if we know the context
            # Only show ORIENTING if context is actually "unknown"
            in_game = self.current_sector and self.current_sector > 0
            if orient_phase and current_context == "unknown" and in_game:
                # We're orienting AND don't know what screen we're on
                if orient_step > 0 and orient_max > 0:
                    activity = f"ORIENTING: Step {orient_step}/{orient_max}"
                else:
                    phase_names = {
                        "starting": "Initializing",
                        "gather": "Gathering state",
                        "safe_state": "Finding safe prompt",
                        "blank_wake": "Waking connection",
                        "failed": "Recovering",
                    }
                    phase_display = phase_names.get(orient_phase, orient_phase.title())
                    activity = f"ORIENTING: {phase_display}"

            # Extract character/ship info from game state
            username = None
            ship_level = None
            ship_name = None

            if self.game_state:
                username = getattr(self.game_state, "player_name", None) or self.character_name
                ship_level = getattr(self.game_state, "ship_type", None)
                ship_name = getattr(self.game_state, "ship_name", None)
            else:
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

            # Check if AI strategy is thinking (waiting for LLM response)
            if self.strategy and hasattr(self.strategy, '_is_thinking') and self.strategy._is_thinking:
                activity = "THINKING"

            # Override with AI reasoning if available
            if self.ai_activity:
                activity = self.ai_activity
                self.ai_activity = None  # Clear after reporting

            # Hijack mode always takes priority
            if self._hijacked:
                activity = "HIJACKED"

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
        if not self._hijacked:
            return
        if self._hijack_step_tokens > 0:
            self._hijack_step_tokens -= 1
            return
        await self._hijack_event.wait()

    async def set_hijacked(self, enabled: bool) -> None:
        """Enable/disable hijack mode (pause automation only)."""
        if enabled == self._hijacked:
            return
        self._hijacked = enabled
        if enabled:
            # Clear any queued steps when entering hijack mode.
            self._hijack_step_tokens = 0

        if enabled:
            self._hijack_event.clear()
        else:
            self._hijack_event.set()

    async def request_step(self, checkpoints: int = 2) -> None:
        """Allow automation to pass a limited number of hijack checkpoints.

        This is designed to be used while hijacked. If not hijacked, it's a no-op.

        Args:
            checkpoints: Number of await_if_hijacked() calls to allow without blocking.
                         The default (2) permits one loop iteration to plan + act.
        """
        if not self._hijacked:
            return
        # Cap to avoid unbounded growth if a client misbehaves.
        self._hijack_step_tokens = min(self._hijack_step_tokens + max(0, int(checkpoints)), 100)

    def attach_screen_change_reporter(self, min_interval_s: float = 0.8) -> None:
        """Report status when the visible screen changes (throttled).

        This keeps `activity_context` in the swarm dashboard aligned with what the bot
        is actually seeing, without relying solely on periodic polling.
        """
        if self._screen_change_task is not None:
            return
        if not getattr(self, "session", None):
            return

        def _watch(snapshot: dict, raw: bytes) -> None:
            try:
                sh = snapshot.get("screen_hash") or ""
                if not sh:
                    return
                if sh == self._last_seen_screen_hash:
                    return
                self._last_seen_screen_hash = sh
                self._screen_change_event.set()
            except Exception:
                return

        # Only report on real updates; raw may be empty in timeout reads.
        self.session.add_watch(_watch, interval_s=0.0)

        async def _loop() -> None:
            last_sent = 0.0
            while True:
                await self._screen_change_event.wait()
                self._screen_change_event.clear()
                now = time.monotonic()
                delay = (last_sent + float(min_interval_s)) - now
                if delay > 0:
                    await asyncio.sleep(delay)
                try:
                    await self.report_status()
                except Exception:
                    pass
                last_sent = time.monotonic()

        self._screen_change_task = asyncio.create_task(_loop())

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
        if self._screen_change_task is not None:
            self._screen_change_task.cancel()
            try:
                await self._screen_change_task
            except asyncio.CancelledError:
                pass
            self._screen_change_task = None
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
    completed_ok = False

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

        # Start reporting immediately so the manager doesn't mark "no heartbeat"
        # during long login/menu sequences.
        await worker.report_status()
        await worker.start_status_reporter(interval=5.0)

        # Optional: connect terminal bridge (best-effort).
        try:
            from bbsbot.swarm.term_bridge import TermBridge

            term_bridge = TermBridge(worker, bot_id=bot_id, manager_url=manager_url)
            term_bridge.attach_session()
            await term_bridge.start()
        except Exception as e:
            logger.warning(f"Terminal bridge disabled: {e}")

        # Push status updates on screen changes (throttled).
        worker.attach_screen_change_reporter(min_interval_s=0.8)

        # Login sequence
        logger.info("Starting login sequence")
        username = config_obj.connection.username or bot_id
        # If a config doesn't explicitly set a character password, default to username.
        # This matches the common convention used elsewhere in this repo and avoids
        # repeatedly failing at `prompt.character_password` for existing characters.
        explicit_char_pw = (config_dict or {}).get("connection", {}).get("character_password")
        explicit_char_cfg_pw = (config_dict or {}).get("character", {}).get("password")
        character_password = explicit_char_pw or explicit_char_cfg_pw or username
        await worker.login_sequence(
            game_password=config_obj.connection.game_password,
            character_password=character_password,
            username=username,
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

        # Report post-login status (reporter already running)
        await worker.report_status()

        # Create character state for trading loop
        char_state = CharacterState(name=bot_id)

        # Run trading loop using cli_impl (handles orient→strategy cycle)
        from bbsbot.games.tw2002.cli_impl import run_trading_loop

        await run_trading_loop(worker, config_obj, char_state)
        completed_ok = True

    except Exception as e:
        logger.error(f"Bot worker error: {e}", exc_info=True)
        # Report detailed error to manager
        await worker.report_error(e, exit_reason="exception")
    finally:
        # Stop periodic reporter first (prevents stale updates during shutdown)
        await worker.stop_status_reporter()
        # Only mark completed if we actually completed; never overwrite error state with FINISHED.
        if completed_ok:
            try:
                final_status = {
                    "state": "completed",
                    "activity_context": "COMPLETED",
                    "sector": worker.current_sector or 0,
                    "credits": worker.current_credits or 0,
                    "turns_executed": worker.turns_used,
                    "exit_reason": "completed",
                }
                if worker.game_state:
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
