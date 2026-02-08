"""MCP tools for swarm management.

Allows Claude to control the bot swarm through the central manager.
"""

from __future__ import annotations

import glob
from typing import Any

import httpx
from mcp.server import Server

from bbsbot.defaults import MANAGER_URL


def _get_client() -> httpx.Client:
    """Get HTTP client for manager communication."""
    return httpx.Client(timeout=30)


def register_swarm_tools(server: Server) -> None:
    """Register all swarm management tools with MCP server.

    Args:
        server: MCP Server instance
    """

    @server.tool()
    async def tw2002_spawn_bot(config_path: str) -> dict[str, Any]:
        """Spawn a single bot through the swarm manager.

        Args:
            config_path: Path to bot config YAML file

        Returns:
            Bot ID and process info
        """
        with _get_client() as client:
            response = client.post(
                f"{MANAGER_URL}/swarm/spawn",
                params={"config_path": config_path},
            )
            return response.json()

    @server.tool()
    async def tw2002_spawn_swarm(
        count: int = 111,
        pattern: str = "config/test_matrix/*.yaml",
    ) -> dict[str, Any]:
        """Spawn multiple bots (create a swarm).

        Args:
            count: Number of bots to spawn
            pattern: Glob pattern for config files

        Returns:
            List of bot IDs created
        """
        configs = glob.glob(pattern)[:count]

        with _get_client() as client:
            response = client.post(
                f"{MANAGER_URL}/swarm/spawn-batch",
                json={"config_paths": configs},
            )
            return response.json()

    @server.tool()
    async def tw2002_get_swarm_status() -> dict[str, Any]:
        """Get status of all running bots in the swarm.

        Returns:
            Swarm status with aggregated metrics
        """
        with _get_client() as client:
            response = client.get(f"{MANAGER_URL}/swarm/status")
            return response.json()

    @server.tool()
    async def tw2002_get_bot_status(bot_id: str) -> dict[str, Any]:
        """Get status of a specific bot.

        Args:
            bot_id: ID of the bot

        Returns:
            Bot status including sector, credits, turns
        """
        with _get_client() as client:
            response = client.get(
                f"{MANAGER_URL}/bot/{bot_id}/status"
            )
            return response.json()

    @server.tool()
    async def tw2002_pause_bot(bot_id: str) -> dict[str, Any]:
        """Pause a running bot.

        Args:
            bot_id: ID of bot to pause

        Returns:
            Updated bot status
        """
        with _get_client() as client:
            response = client.post(
                f"{MANAGER_URL}/bot/{bot_id}/pause"
            )
            return response.json()

    @server.tool()
    async def tw2002_resume_bot(bot_id: str) -> dict[str, Any]:
        """Resume a paused bot.

        Args:
            bot_id: ID of bot to resume

        Returns:
            Updated bot status
        """
        with _get_client() as client:
            response = client.post(
                f"{MANAGER_URL}/bot/{bot_id}/resume"
            )
            return response.json()

    @server.tool()
    async def tw2002_kill_bot(bot_id: str) -> dict[str, Any]:
        """Terminate a bot process.

        Args:
            bot_id: ID of bot to kill

        Returns:
            Confirmation of termination
        """
        with _get_client() as client:
            response = client.delete(
                f"{MANAGER_URL}/bot/{bot_id}"
            )
            return response.json()

    @server.tool()
    async def tw2002_set_bot_goal(
        bot_id: str, goal: str
    ) -> dict[str, Any]:
        """Change a bot's trading goal.

        Args:
            bot_id: ID of bot to modify
            goal: New goal (e.g., 'exploration', 'profit', 'banking')

        Returns:
            Confirmation of goal change
        """
        with _get_client() as client:
            response = client.post(
                f"{MANAGER_URL}/bot/{bot_id}/set-goal",
                params={"goal": goal},
            )
            return response.json()

    @server.tool()
    async def tw2002_get_top_bots(count: int = 10) -> dict[str, Any]:
        """Get top performing bots by credits earned.

        Args:
            count: Number of top bots to return

        Returns:
            List of top bots with their stats
        """
        with _get_client() as client:
            response = client.get(f"{MANAGER_URL}/swarm/status")
            status = response.json()

            # Sort by credits
            top_bots = sorted(
                status["bots"],
                key=lambda b: b["credits"],
                reverse=True,
            )[:count]

            return {
                "count": len(top_bots),
                "total_credits": status["total_credits"],
                "bots": top_bots,
            }

    @server.tool()
    async def tw2002_get_struggling_bots(
        error_only: bool = False,
    ) -> dict[str, Any]:
        """Get bots that are not performing well.

        Args:
            error_only: Only show bots in error state

        Returns:
            List of struggling bots
        """
        with _get_client() as client:
            response = client.get(f"{MANAGER_URL}/swarm/status")
            status = response.json()

            bots = [
                b
                for b in status["bots"]
                if (error_only and b["state"] == "error")
                or (
                    not error_only
                    and (
                        b["state"] == "error"
                        or (b["turns_executed"] > 0 and b["credits"] <= 0)
                    )
                )
            ]

            return {
                "count": len(bots),
                "bots": sorted(
                    bots, key=lambda b: b["turns_executed"], reverse=True
                ),
            }

    @server.tool()
    async def tw2002_swarm_summary() -> dict[str, Any]:
        """Get a quick summary of swarm performance.

        Returns:
            Summary statistics for the swarm
        """
        with _get_client() as client:
            response = client.get(f"{MANAGER_URL}/swarm/status")
            status = response.json()

            # Calculate statistics
            credits = [b["credits"] for b in status["bots"]]
            avg_credits = (
                sum(credits) / len(credits) if credits else 0
            )

            return {
                "total_bots": status["total_bots"],
                "running": status["running"],
                "completed": status["completed"],
                "errors": status["errors"],
                "total_credits_earned": status["total_credits"],
                "average_credits_per_bot": int(avg_credits),
                "total_turns": status["total_turns"],
                "average_turns_per_bot": (
                    status["total_turns"] // status["total_bots"]
                    if status["total_bots"] > 0
                    else 0
                ),
                "uptime_minutes": status["uptime_seconds"] / 60,
            }
