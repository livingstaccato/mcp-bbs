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
from collections import deque

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
        # Watchdog: if no progress is observed for too long, force a reconnect.
        self._watchdog_task: asyncio.Task | None = None
        self._last_progress_mono: float = time.monotonic()
        self._last_turns_seen: int = 0
        # Lifecycle state reported to manager (do not overwrite with "running" just because connected).
        self.lifecycle_state: str = "running"

    def _note_progress(self) -> None:
        self._last_progress_mono = time.monotonic()

    def start_watchdog(self, *, stuck_timeout_s: float = 120.0, check_interval_s: float = 5.0) -> None:
        """Start a watchdog that forces recovery if the bot stops making progress.

        Progress signals:
        - turns_used increases
        - screen_hash changes

        If we see neither for `stuck_timeout_s`, we disconnect the session. The outer
        worker loop will reconnect + re-login + continue.
        """
        if self._watchdog_task is not None and not self._watchdog_task.done():
            return

        async def _loop() -> None:
            while True:
                await asyncio.sleep(max(0.5, float(check_interval_s)))
                try:
                    if self._hijacked:
                        # If a human is driving, don't fight them.
                        self._note_progress()
                        continue

                    # Turns progression is authoritative for "still alive".
                    if self.turns_used != self._last_turns_seen:
                        self._last_turns_seen = self.turns_used
                        self._note_progress()

                    idle_for = time.monotonic() - self._last_progress_mono
                    if idle_for < float(stuck_timeout_s):
                        continue

                    # Stuck: report + force reconnect by disconnecting the session.
                    try:
                        self.ai_activity = f"WATCHDOG: STUCK ({int(idle_for)}s)"
                        await self.report_error(
                            RuntimeError(f"watchdog_stuck_{int(idle_for)}s"),
                            exit_reason="watchdog_stuck",
                            fatal=False,
                            state="recovering",
                        )
                        await self.report_status()
                    except Exception:
                        pass

                    try:
                        await self.disconnect()
                    except Exception:
                        pass

                    # Reset timer so we don't spam disconnect loops if reconnect is slow.
                    self._note_progress()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    continue

        self._watchdog_task = asyncio.create_task(_loop())

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
            else:
                # Fallback: semantic extraction from live screens (updated by session watcher / wait_and_respond).
                sem = getattr(self, "last_semantic_data", {}) or {}
                try:
                    sem_credits = sem.get("credits")
                    if sem_credits is not None:
                        credits = int(sem_credits)
                except Exception:
                    pass

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
            # Preserve lifecycle state (recovering/blocked) across periodic status reports.
            actual_state = getattr(self, "lifecycle_state", "running") or "running"
            if actual_state == "running" and not connected:
                actual_state = "disconnected"
            if not connected and actual_state in ("running", "disconnected"):
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
                self._note_progress()
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

    async def report_error(
        self,
        error: Exception,
        exit_reason: str = "exception",
        *,
        fatal: bool = False,
        state: str | None = None,
    ) -> None:
        """Report detailed error information to manager.

        End-state: workers should be resilient and self-heal. Most exceptions are
        reported as `recovering` (not terminal) and the worker keeps running.
        """
        import time
        try:
            report_state = state
            if report_state is None:
                report_state = "error" if fatal else "recovering"
            # Ensure the next report_status() preserves this state.
            self.lifecycle_state = report_state
            await self._http_client.post(
                f"{self.manager_url}/bot/{self.bot_id}/status",
                json={
                    "state": report_state,
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

    # Resolve credentials once from config; retries use the same.
    username = config_obj.connection.username or bot_id
    explicit_char_pw = (config_dict or {}).get("connection", {}).get("character_password")
    explicit_char_cfg_pw = (config_dict or {}).get("character", {}).get("password")
    character_password = explicit_char_pw or explicit_char_cfg_pw or username
    game_password = config_obj.connection.game_password

    # Register with manager (best-effort; don't crash the worker if manager is down).
    try:
        await worker.register_with_manager()
    except Exception:
        pass

    # Start reporting immediately so the manager doesn't mark "no heartbeat".
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

    # Resilience loop: never exit on recoverable errors.
    backoff_s = 1.0
    failures = 0

    class _RecoveryBudget:
        def __init__(self, *, window_s: float = 600.0) -> None:
            self.window_s = float(window_s)
            self._events: dict[str, deque[float]] = {
                "auth": deque(),
                "network": deque(),
                "logic": deque(),
                "watchdog": deque(),
            }
            self._limits: dict[str, int] = {
                "auth": 1,        # unrecoverable; block immediately
                "network": 5,     # 5 in 10m => blocked
                "logic": 5,       # 5 in 10m => blocked
                "watchdog": 3,    # 3 in 10m => blocked
            }

        def note(self, cls: str) -> int:
            now = time.monotonic()
            dq = self._events.setdefault(cls, deque())
            dq.append(now)
            cutoff = now - self.window_s
            while dq and dq[0] < cutoff:
                dq.popleft()
            return len(dq)

        def exceeded(self, cls: str) -> bool:
            limit = int(self._limits.get(cls, 5))
            dq = self._events.get(cls) or deque()
            return len(dq) >= limit

        def reset(self) -> None:
            for dq in self._events.values():
                dq.clear()

    def _classify_exception(e: Exception) -> str:
        msg = str(e).lower()
        et = type(e).__name__.lower()
        if "watchdog_stuck" in msg or "watchdog" in msg:
            return "watchdog"
        if "invalid_password" in msg or "prompt.character_password" in msg:
            return "auth"
        if "connection" in msg or "not connected" in msg or "timeout" in msg:
            return "network"
        if "connectionerror" in et or "timeout" in et:
            return "network"
        return "logic"

    budget = _RecoveryBudget(window_s=600.0)
    blocked_level: dict[str, int] = {"auth": 0, "network": 0, "logic": 0, "watchdog": 0}
    blocked_schedule_s = [300.0, 900.0, 1800.0]  # 5m, 15m, 30m
    rng = __import__("random").Random(1)

    try:
        while True:
            try:
                # Ensure watchdog is running once per process.
                worker.start_watchdog(stuck_timeout_s=120.0, check_interval_s=5.0)

                # (Re)connect if needed.
                if not getattr(worker, "session", None) or not worker.session.is_connected():
                    try:
                        await worker.disconnect()
                    except Exception:
                        pass
                    logger.info(
                        f"Connecting to {config_obj.connection.host}:"
                        f"{config_obj.connection.port}"
                    )
                    worker.ai_activity = "CONNECTING"
                    worker.lifecycle_state = "recovering"
                    await worker.connect(
                        host=config_obj.connection.host,
                        port=config_obj.connection.port,
                    )
                    # Push status updates on screen changes (throttled) once session exists.
                    worker.attach_screen_change_reporter(min_interval_s=0.8)

                # Login (idempotent-ish; may early-return if already in game).
                worker.ai_activity = "LOGGING_IN"
                worker.lifecycle_state = "recovering"
                await worker.login_sequence(
                    game_password=game_password,
                    character_password=character_password,
                    username=username,
                )

                # Initialize knowledge and strategy (safe to re-init across reconnects).
                game_letter = config_obj.connection.game_letter or worker.last_game_letter
                worker.init_knowledge(
                    config_obj.connection.host, config_obj.connection.port, game_letter
                )
                worker.init_strategy()
                worker.lifecycle_state = "running"
                await worker.report_status()

                # Run trading loop; end-state: loop returns only on internal soft-stops,
                # and we immediately restart rather than exiting the worker.
                from bbsbot.games.tw2002.character import CharacterState
                from bbsbot.games.tw2002.cli_impl import run_trading_loop

                char_state = CharacterState(name=bot_id)
                worker.ai_activity = "RUNNING"
                worker.lifecycle_state = "running"
                await run_trading_loop(worker, config_obj, char_state)

                # If the trading loop returns, treat it as a soft-stop and restart.
                worker.ai_activity = "RESTARTING (soft-stop)"
                await worker.report_status()
                await asyncio.sleep(2.0)

                # Reset backoff after any successful run segment.
                backoff_s = 1.0
                failures = 0
                budget.reset()
                for k in blocked_level:
                    blocked_level[k] = 0

            except asyncio.CancelledError:
                raise
            except Exception as e:
                failures += 1
                logger.error(f"Worker cycle error: {e}", exc_info=True)
                cls = _classify_exception(e)
                budget.note(cls)

                # Escalation: stop thrashing; enter blocked with long backoff.
                if cls == "auth" or budget.exceeded(cls):
                    lvl = int(blocked_level.get(cls, 0))
                    blocked_level[cls] = min(lvl + 1, len(blocked_schedule_s) - 1)
                    base_sleep = blocked_schedule_s[min(lvl, len(blocked_schedule_s) - 1)]
                    # Add small deterministic jitter to avoid a herd on the minute.
                    sleep_s = float(base_sleep) * (0.85 + 0.3 * rng.random())
                    worker.ai_activity = f"BLOCKED {int(sleep_s // 60)}m ({cls})"
                    worker.lifecycle_state = "blocked"
                    await worker.report_error(
                        e,
                        exit_reason=f"blocked_{cls}",
                        fatal=False,
                        state="blocked",
                    )
                    try:
                        await worker.report_status()
                    except Exception:
                        pass
                    await asyncio.sleep(sleep_s)
                    # After blocked sleep, keep the process alive and try again.
                    backoff_s = 1.0
                    continue

                # Report as recovering (non-terminal).
                worker.lifecycle_state = "recovering"
                await worker.report_error(e, exit_reason="recovering", fatal=False, state="recovering")

                # Try in-session recovery first (escape menus, get back to safe prompt).
                recovered = False
                try:
                    worker.ai_activity = f"RECOVERING ({type(e).__name__})"
                    await worker.report_status()
                    await worker.recover(max_attempts=20)
                    recovered = True
                except Exception:
                    recovered = False

                # If recovery didn't help, force reconnect.
                if not recovered:
                    try:
                        await worker.disconnect()
                    except Exception:
                        pass

                # Exponential backoff to avoid thrashing the server on persistent failures.
                sleep_s = min(60.0, backoff_s)
                worker.ai_activity = f"BACKOFF {sleep_s:.0f}s (failures={failures})"
                worker.lifecycle_state = "recovering"
                try:
                    await worker.report_status()
                except Exception:
                    pass
                await asyncio.sleep(sleep_s)
                backoff_s = min(60.0, backoff_s * 2.0)
                continue
    finally:
        try:
            await worker.stop_status_reporter()
        except Exception:
            pass
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
