"""Swarm manager for controlling multiple bot instances.

Provides central coordination for spawning, monitoring, and controlling
multiple trading bots through a REST API and WebSocket interface.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import time
from pydantic import BaseModel, Field
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

from bbsbot.api import log_routes, swarm_routes
from bbsbot.api import term_routes
from bbsbot.defaults import MANAGER_HOST, MANAGER_PORT
from bbsbot.log_service import LogService
from bbsbot.logging import get_logger

logger = get_logger(__name__)


class BotStatus(BaseModel):
    """Status of a single bot instance."""

    bot_id: str
    pid: int
    config: str
    state: str  # queued, running, completed, error, stopped
    sector: int = 0
    credits: int = -1  # -1 = uninitialized, 0+ = valid
    turns_executed: int = 0
    turns_max: int = 500  # Max turns for this session
    uptime_seconds: float = 0
    last_update_time: float = Field(default_factory=time.time)
    completed_at: float | None = None  # Timestamp when bot completed
    error_message: str | None = None
    # Activity tracking
    last_action: str | None = None        # "TRADING", "EXPLORING", "BATTLING", etc
    last_action_time: float = 0           # timestamp of last action
    activity_context: str | None = None   # current game context
    # Error tracking
    error_type: str | None = None         # Exception class name (e.g., "TimeoutError")
    error_timestamp: float | None = None  # When error occurred
    exit_reason: str | None = None        # "target_reached", "out_of_turns", "login_failed", etc
    # Action feed (last 10 actions)
    recent_actions: list[dict] = Field(default_factory=list)
    # Character/game info for dashboard display
    username: str | None = None          # Character name
    ship_name: str | None = None         # Current ship name
    ship_level: str | None = None        # Ship class/level (Fighter, Trader, etc)
    port_location: int | None = None     # Current port sector
    # Hijack/MCP control tracking
    is_hijacked: bool = False            # Whether bot is under MCP control
    hijacked_at: float | None = None     # Timestamp when hijack started
    hijacked_by: str | None = None       # Who/what hijacked it (e.g., "mcp", "user")


class SwarmStatus(BaseModel):
    """Overall swarm status."""

    total_bots: int
    running: int
    completed: int
    errors: int
    stopped: int
    total_credits: int
    total_turns: int
    uptime_seconds: float
    bots: list[dict]


class SwarmManager:
    """Central manager for bot swarm."""

    def __init__(
        self,
        max_bots: int = 200,
        state_file: str = "swarm_state.json",
        health_check_interval: int = 10,
    ):
        self.max_bots = max_bots
        self.state_file = state_file
        self.health_check_interval = health_check_interval
        self.start_time = time.time()

        self.bots: dict[str, BotStatus] = {}
        self.processes: dict[str, subprocess.Popen] = {}
        self.websocket_clients: set[WebSocket] = set()
        self.log_service = LogService()

        self.app = FastAPI(title="BBSBot Swarm Manager")
        self._setup_routes()
        self._setup_dashboard()
        self._load_state()

    def _setup_dashboard(self) -> None:
        """Mount web dashboard static files and route."""
        web_dir = Path(__file__).parent / "web"
        static_dir = web_dir / "static"

        if static_dir.is_dir():
            self.app.mount(
                "/static",
                StaticFiles(directory=str(static_dir)),
                name="static",
            )

        dashboard_html = web_dir / "dashboard.html"

        @self.app.get("/dashboard", response_class=HTMLResponse)
        async def dashboard():
            if dashboard_html.exists():
                return dashboard_html.read_text()
            return HTMLResponse("<h1>Dashboard not found</h1>", status_code=404)

    def _setup_routes(self) -> None:
        """Setup FastAPI routes via sub-routers and WebSocket."""
        self.app.include_router(swarm_routes.setup(self))
        self.app.include_router(log_routes.setup(self.log_service))
        self.app.include_router(term_routes.setup(self))

        @self.app.websocket("/ws/swarm")
        async def websocket_endpoint(websocket: WebSocket):
            """Real-time swarm updates."""
            await websocket.accept()
            self.websocket_clients.add(websocket)
            try:
                while True:
                    await websocket.receive_text()
            except WebSocketDisconnect:
                self.websocket_clients.remove(websocket)
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
                self.websocket_clients.discard(websocket)

    async def spawn_bot(self, config_path: str, bot_id: str) -> str:
        """Spawn a single bot process."""
        if len(self.bots) >= self.max_bots:
            raise RuntimeError(f"Max bots ({self.max_bots}) reached")

        if not Path(config_path).exists():
            raise RuntimeError(f"Config not found: {config_path}")

        logger.info(f"Spawning bot: {bot_id} with config {config_path}")

        cmd = [
            "uv", "run", "python", "-m",
            "bbsbot.games.tw2002.worker",
            "--config", config_path,
            "--bot-id", bot_id,
        ]

        try:
            log_dir = Path("logs/workers")
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / f"{bot_id}.log"
            log_handle = open(log_file, "w")

            process = subprocess.Popen(
                cmd,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
            )

            if bot_id in self.bots:
                # Update pre-registered queued bot
                self.bots[bot_id].pid = process.pid
                self.bots[bot_id].state = "running"
                self.bots[bot_id].last_update_time = time.time()
            else:
                self.bots[bot_id] = BotStatus(
                    bot_id=bot_id,
                    pid=process.pid,
                    config=config_path,
                    state="running",
                )
            self.processes[bot_id] = process

            logger.info(f"Bot {bot_id} spawned with PID {process.pid}")
            await self._broadcast_status()
            return bot_id

        except Exception as e:
            logger.error(f"Failed to spawn bot {bot_id}: {e}")
            raise RuntimeError(f"Failed to spawn bot: {e}")

    async def spawn_swarm(
        self,
        config_paths: list[str],
        group_size: int = 5,
        group_delay: float = 60.0,
    ) -> list[str]:
        """Spawn multiple bots in staggered groups.

        Args:
            config_paths: List of config file paths for each bot.
            group_size: Number of bots to spawn simultaneously per group.
            group_delay: Seconds to wait between groups (allows logins to complete).
        """
        bot_ids = []
        total = len(config_paths)

        # Pre-register all bots as queued so they appear in dashboard immediately
        base_index = len(self.bots)
        for i, config in enumerate(config_paths):
            bot_id = f"bot_{base_index + i:03d}"
            if bot_id not in self.bots:
                self.bots[bot_id] = BotStatus(
                    bot_id=bot_id,
                    pid=0,
                    config=config,
                    state="queued",
                )
        await self._broadcast_status()

        for group_start in range(0, total, group_size):
            group_end = min(group_start + group_size, total)
            group_configs = config_paths[group_start:group_end]
            group_num = (group_start // group_size) + 1
            total_groups = (total + group_size - 1) // group_size

            logger.info(
                f"Spawning group {group_num}/{total_groups}: "
                f"bots {group_start + 1}-{group_end} of {total}"
            )

            # Spawn all bots in this group concurrently
            for i, config in enumerate(group_configs):
                bot_id = f"bot_{base_index + group_start + i:03d}"
                try:
                    await self.spawn_bot(config, bot_id)
                    bot_ids.append(bot_id)
                except Exception as e:
                    logger.error(f"Failed to spawn {bot_id} with {config}: {e}")

            # Wait between groups to let logins complete before next batch
            if group_end < total:
                logger.info(
                    f"Group {group_num} done ({len(group_configs)} spawned). "
                    f"Waiting {group_delay}s before next group..."
                )
                await asyncio.sleep(group_delay)

        logger.info(f"Swarm spawn complete: {len(bot_ids)}/{total} bots started")
        return bot_ids

    async def kill_bot(self, bot_id: str) -> None:
        """Terminate a bot process."""
        if bot_id not in self.processes:
            return

        process = self.processes[bot_id]
        try:
            process.terminate()
            process.wait(timeout=5)
            logger.info(f"Bot {bot_id} terminated")
        except subprocess.TimeoutExpired:
            process.kill()
            logger.warning(f"Bot {bot_id} force-killed")

        self.bots[bot_id].state = "stopped"
        del self.processes[bot_id]
        await self._broadcast_status()

    def get_swarm_status(self) -> SwarmStatus:
        """Get overall swarm metrics."""
        bots = list(self.bots.values())
        return SwarmStatus(
            total_bots=len(bots),
            running=sum(1 for b in bots if b.state == "running"),
            completed=sum(1 for b in bots if b.state == "completed"),
            errors=sum(1 for b in bots if b.state in ("error", "disconnected")),
            stopped=sum(1 for b in bots if b.state == "stopped"),
            total_credits=sum(b.credits for b in bots),
            total_turns=sum(b.turns_executed for b in bots),
            uptime_seconds=time.time() - self.start_time,
            bots=[b.model_dump() for b in bots],
        )

    async def _monitor_processes(self) -> None:
        """Monitor bot processes for crashes or completion."""
        while True:
            for bot_id, process in list(self.processes.items()):
                if process.poll() is not None:
                    exit_code = process.returncode
                    logger.warning(f"Bot {bot_id} exited with code {exit_code}")
                    bot = self.bots[bot_id]
                    if exit_code == 0:
                        bot.state = "completed"
                        bot.completed_at = time.time()
                        if not bot.exit_reason:
                            bot.exit_reason = "target_reached"
                    else:
                        bot.state = "error"
                        if not bot.exit_reason:
                            bot.exit_reason = f"exit_code_{exit_code}"
                        if not bot.error_message:
                            bot.error_message = f"Process exited with code {exit_code}"
                    del self.processes[bot_id]
                    await self._broadcast_status()

            now = time.time()
            for bot in self.bots.values():
                if bot.state in ("running",) and now - bot.last_update_time > 60:
                    logger.warning(f"Bot {bot.bot_id} heartbeat timeout (no status update in 60s)")
                    bot.state = "error"
                    bot.error_message = "No heartbeat in 60s - bot process may have crashed or is stuck"
                    bot.error_type = "HeartbeatTimeout"
                    bot.exit_reason = "heartbeat_timeout"
                    import time as time_module
                    bot.error_timestamp = time_module.time()

            await asyncio.sleep(self.health_check_interval)

    async def _broadcast_status(self) -> None:
        """Broadcast status to all connected WebSocket clients."""
        status = self.get_swarm_status()
        message = json.dumps(status.model_dump())

        disconnected = set()
        for client in self.websocket_clients:
            try:
                await client.send_text(message)
            except Exception:
                disconnected.add(client)

        self.websocket_clients -= disconnected

    def _save_state(self) -> None:
        """Save swarm state to file."""
        state = {
            "timestamp": time.time(),
            "bots": {
                bot_id: bot.model_dump()
                for bot_id, bot in self.bots.items()
            },
        }
        with open(self.state_file, "w") as f:
            json.dump(state, f, indent=2)

    def _load_state(self) -> None:
        """Load swarm state from file if exists."""
        if not Path(self.state_file).exists():
            return
        try:
            with open(self.state_file) as f:
                state = json.load(f)
                # Load bots from previous state
                for bot_id, bot_data in state.get("bots", {}).items():
                    if bot_id not in self.bots:
                        # Loaded bots have no process handle - if they were
                        # "running" before the manager crashed, mark them
                        # "stopped" since we can't verify their actual state.
                        saved_state = bot_data.get("state", "stopped")
                        if saved_state in ("running", "disconnected"):
                            saved_state = "stopped"
                        # Reconstruct BotStatus from saved data
                        self.bots[bot_id] = BotStatus(
                            bot_id=bot_data.get("bot_id", bot_id),
                            pid=bot_data.get("pid", 0),
                            config=bot_data.get("config", ""),
                            state=saved_state,
                            sector=bot_data.get("sector", 0),
                            credits=bot_data.get("credits", 0),
                            turns_executed=bot_data.get("turns_executed", 0),
                            turns_max=bot_data.get("turns_max", 500),
                            uptime_seconds=bot_data.get("uptime_seconds", 0),
                            last_update_time=bot_data.get("last_update_time", time.time()),
                            completed_at=bot_data.get("completed_at"),
                            error_message=bot_data.get("error_message"),
                            last_action=bot_data.get("last_action"),
                            last_action_time=bot_data.get("last_action_time", 0),
                            activity_context=bot_data.get("activity_context"),
                            error_type=bot_data.get("error_type"),
                            error_timestamp=bot_data.get("error_timestamp"),
                            exit_reason=bot_data.get("exit_reason"),
                            recent_actions=bot_data.get("recent_actions", []),
                            username=bot_data.get("username"),
                            ship_name=bot_data.get("ship_name"),
                            ship_level=bot_data.get("ship_level"),
                            port_location=bot_data.get("port_location"),
                        )
                logger.info(f"Loaded {len(state.get('bots', {}))} bots from {self.state_file}")
        except Exception as e:
            logger.error(f"Failed to load state: {e}")

    async def run(self, host: str = MANAGER_HOST, port: int = MANAGER_PORT):
        """Run the manager server."""
        logger.info(f"Starting swarm manager on {host}:{port}")

        asyncio.create_task(self._monitor_processes())

        async def save_periodically():
            while True:
                await asyncio.sleep(60)
                self._save_state()

        asyncio.create_task(save_periodically())

        config = uvicorn.Config(
            self.app, host=host, port=port, log_level="info",
        )
        server = uvicorn.Server(config)
        await server.serve()


if __name__ == "__main__":
    manager = SwarmManager()
    asyncio.run(manager.run())
