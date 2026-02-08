"""Swarm manager for controlling multiple bot instances.

Provides central coordination for spawning, monitoring, and controlling
multiple trading bots through a REST API and WebSocket interface.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import psutil
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
import uvicorn

from bbsbot.logging import get_logger

logger = get_logger(__name__)


@dataclass
class BotStatus:
    """Status of a single bot instance."""

    bot_id: str
    pid: int
    config: str
    state: str  # running, paused, completed, error, stopped
    sector: int = 0
    credits: int = 0
    turns_executed: int = 0
    uptime_seconds: float = 0
    last_update_time: float = field(default_factory=time.time)
    error_message: str | None = None


@dataclass
class SwarmStatus:
    """Overall swarm status."""

    total_bots: int
    running: int
    paused: int
    completed: int
    errors: int
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
        """Initialize swarm manager.

        Args:
            max_bots: Maximum number of concurrent bots
            state_file: File to persist swarm state
            health_check_interval: Seconds between health checks
        """
        self.max_bots = max_bots
        self.state_file = state_file
        self.health_check_interval = health_check_interval
        self.start_time = time.time()

        self.bots: dict[str, BotStatus] = {}
        self.processes: dict[str, subprocess.Popen] = {}
        self.websocket_clients: set[WebSocket] = set()

        self.app = FastAPI(title="BBSBot Swarm Manager")
        self._setup_routes()

        # Load saved state if exists
        self._load_state()

    def _setup_routes(self) -> None:
        """Setup FastAPI routes."""

        @self.app.get("/health")
        async def health_check():
            return {"status": "ok"}

        @self.app.post("/swarm/spawn")
        async def spawn(config_path: str, bot_id: str | None = None):
            try:
                if bot_id is None:
                    bot_id = f"bot_{len(self.bots):03d}"
                bot_id = await self.spawn_bot(config_path, bot_id)
                return {"bot_id": bot_id, "pid": self.bots[bot_id].pid}
            except Exception as e:
                return JSONResponse(
                    {"error": str(e)}, status_code=400
                )

        @self.app.post("/swarm/spawn-batch")
        async def spawn_batch(config_paths: list[str]):
            try:
                bot_ids = await self.spawn_swarm(config_paths)
                return {
                    "bot_ids": bot_ids,
                    "count": len(bot_ids),
                }
            except Exception as e:
                return JSONResponse(
                    {"error": str(e)}, status_code=400
                )

        @self.app.get("/swarm/status")
        async def status():
            return asdict(self.get_swarm_status())

        @self.app.get("/bot/{bot_id}/status")
        async def bot_status(bot_id: str):
            if bot_id not in self.bots:
                return JSONResponse(
                    {"error": f"Bot {bot_id} not found"},
                    status_code=404,
                )
            return asdict(self.bots[bot_id])

        @self.app.post("/bot/{bot_id}/pause")
        async def pause(bot_id: str):
            if bot_id not in self.bots:
                return JSONResponse(
                    {"error": f"Bot {bot_id} not found"},
                    status_code=404,
                )
            self.bots[bot_id].state = "paused"
            return {"bot_id": bot_id, "state": "paused"}

        @self.app.post("/bot/{bot_id}/resume")
        async def resume(bot_id: str):
            if bot_id not in self.bots:
                return JSONResponse(
                    {"error": f"Bot {bot_id} not found"},
                    status_code=404,
                )
            self.bots[bot_id].state = "running"
            return {"bot_id": bot_id, "state": "running"}

        @self.app.delete("/bot/{bot_id}")
        async def kill(bot_id: str):
            if bot_id not in self.bots:
                return JSONResponse(
                    {"error": f"Bot {bot_id} not found"},
                    status_code=404,
                )
            await self.kill_bot(bot_id)
            return {"killed": bot_id}

        @self.app.post("/bot/{bot_id}/set-goal")
        async def set_goal(bot_id: str, goal: str):
            if bot_id not in self.bots:
                return JSONResponse(
                    {"error": f"Bot {bot_id} not found"},
                    status_code=404,
                )
            # TODO: Send goal change to bot via IPC
            return {"bot_id": bot_id, "goal": goal}

        @self.app.websocket("/ws/swarm")
        async def websocket_endpoint(websocket: WebSocket):
            """Real-time swarm updates."""
            await websocket.accept()
            self.websocket_clients.add(websocket)
            try:
                while True:
                    # Keep connection alive, receive pings
                    await websocket.receive_text()
            except WebSocketDisconnect:
                self.websocket_clients.remove(websocket)
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
                self.websocket_clients.discard(websocket)

    async def spawn_bot(
        self, config_path: str, bot_id: str
    ) -> str:
        """Spawn a single bot process.

        Args:
            config_path: Path to bot config file
            bot_id: Unique bot identifier

        Returns:
            bot_id of spawned bot

        Raises:
            RuntimeError: If max bots reached or spawn fails
        """
        if len(self.bots) >= self.max_bots:
            raise RuntimeError(f"Max bots ({self.max_bots}) reached")

        if not Path(config_path).exists():
            raise RuntimeError(f"Config not found: {config_path}")

        logger.info(f"Spawning bot: {bot_id} with config {config_path}")

        # Spawn bot worker subprocess
        cmd = [
            "python",
            "-m",
            "bbsbot.games.tw2002.worker",
            "--config",
            config_path,
            "--bot-id",
            bot_id,
        ]

        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.bots[bot_id] = BotStatus(
                bot_id=bot_id,
                pid=process.pid,
                config=config_path,
                state="running",
            )
            self.processes[bot_id] = process

            logger.info(f"Bot {bot_id} spawned with PID {process.pid}")

            # Notify WebSocket clients
            await self._broadcast_status()

            return bot_id

        except Exception as e:
            logger.error(f"Failed to spawn bot {bot_id}: {e}")
            raise RuntimeError(f"Failed to spawn bot: {e}")

    async def spawn_swarm(self, config_paths: list[str]) -> list[str]:
        """Spawn multiple bots from config list.

        Args:
            config_paths: List of config file paths

        Returns:
            List of bot_ids
        """
        bot_ids = []
        for i, config in enumerate(config_paths):
            bot_id = f"bot_{len(self.bots):03d}"
            try:
                await self.spawn_bot(config, bot_id)
                bot_ids.append(bot_id)
            except Exception as e:
                logger.error(
                    f"Failed to spawn bot {i} with {config}: {e}"
                )
            # Stagger startup
            await asyncio.sleep(0.5)

        return bot_ids

    async def kill_bot(self, bot_id: str) -> None:
        """Terminate a bot process.

        Args:
            bot_id: Bot to kill
        """
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
        """Get overall swarm metrics.

        Returns:
            SwarmStatus with aggregated metrics
        """
        bots = list(self.bots.values())

        return SwarmStatus(
            total_bots=len(bots),
            running=sum(1 for b in bots if b.state == "running"),
            paused=sum(1 for b in bots if b.state == "paused"),
            completed=sum(
                1 for b in bots if b.state == "completed"
            ),
            errors=sum(1 for b in bots if b.state == "error"),
            total_credits=sum(b.credits for b in bots),
            total_turns=sum(b.turns_executed for b in bots),
            uptime_seconds=time.time() - self.start_time,
            bots=[asdict(b) for b in bots],
        )

    async def _monitor_processes(self) -> None:
        """Monitor bot processes for crashes or completion."""
        while True:
            for bot_id, process in list(self.processes.items()):
                if process.poll() is not None:  # Process exited
                    exit_code = process.returncode
                    logger.warning(
                        f"Bot {bot_id} exited with code {exit_code}"
                    )
                    self.bots[bot_id].state = (
                        "error" if exit_code != 0 else "completed"
                    )
                    del self.processes[bot_id]
                    await self._broadcast_status()

            # Check for timeout (no update > 60s)
            now = time.time()
            for bot in self.bots.values():
                if bot.state == "running":
                    if now - bot.last_update_time > 60:
                        logger.warning(f"Bot {bot.bot_id} timeout")
                        bot.state = "error"
                        bot.error_message = "No status update (timeout)"

            await asyncio.sleep(self.health_check_interval)

    async def _broadcast_status(self) -> None:
        """Broadcast status to all connected WebSocket clients."""
        status = self.get_swarm_status()
        message = json.dumps(asdict(status))

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
                bot_id: asdict(bot)
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
                logger.info(f"Loaded state from {self.state_file}")
                # TODO: Restore bot info (skip running processes)
        except Exception as e:
            logger.error(f"Failed to load state: {e}")

    async def run(self, host: str = "localhost", port: int = 8000):
        """Run the manager server.

        Args:
            host: Host to bind to
            port: Port to bind to
        """
        logger.info(f"Starting swarm manager on {host}:{port}")

        # Start monitoring task
        asyncio.create_task(self._monitor_processes())

        # Periodically save state
        async def save_periodically():
            while True:
                await asyncio.sleep(60)
                self._save_state()

        asyncio.create_task(save_periodically())

        # Run server
        config = uvicorn.Config(
            self.app,
            host=host,
            port=port,
            log_level="info",
        )
        server = uvicorn.Server(config)
        await server.serve()


if __name__ == "__main__":
    import sys

    manager = SwarmManager()
    asyncio.run(manager.run())
