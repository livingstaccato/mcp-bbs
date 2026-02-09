"""CLI for swarm management.

Provides command-line interface to control the swarm manager.
Integrates into the main bbsbot CLI as `bbsbot swarm <cmd>`.
"""

from __future__ import annotations

import asyncio
import glob
import json
import subprocess
import time
from pathlib import Path

import click
import httpx
from rich.console import Console
from rich.table import Table

from bbsbot.defaults import MANAGER_URL

console = Console()


def ensure_manager_running(manager_url: str = MANAGER_URL) -> bool:
    """Start the swarm manager if it isn't already running."""
    try:
        if httpx.get(f"{manager_url}/health", timeout=2).status_code == 200:
            return True
    except Exception:
        pass

    console.print("[yellow]Starting manager...[/yellow]")
    subprocess.Popen(
        ["uv", "run", "python", "-m", "bbsbot.manager"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    for _ in range(20):
        time.sleep(0.5)
        try:
            if httpx.get(f"{manager_url}/health", timeout=1).status_code == 200:
                console.print("[green]Manager started[/green]")
                return True
        except Exception:
            continue

    console.print("[red]Failed to start manager[/red]")
    return False


def format_uptime(seconds: float) -> str:
    """Format uptime in human readable format."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    elif seconds < 3600:
        return f"{seconds / 60:.1f}m"
    else:
        return f"{seconds / 3600:.1f}h"


def format_credits(credits: int) -> str:
    """Format credits with thousands separator."""
    return f"{credits:,}"


# ── Implementation functions (usable from aliases and shell) ──


def spawn_impl(config: str, bot_id: str | None = None) -> None:
    """Spawn a single bot."""
    if not ensure_manager_running():
        return
    if not Path(config).exists():
        console.print(f"[red]Error: Config not found: {config}")
        return

    with httpx.Client() as client:
        try:
            response = client.post(
                f"{MANAGER_URL}/swarm/spawn",
                params={"config_path": config, "bot_id": bot_id or ""},
            )
            data = response.json()
            if response.status_code == 200:
                console.print(
                    f"[green]✓[/green] Spawned bot: "
                    f"[cyan]{data['bot_id']}[/cyan] (PID: {data['pid']})"
                )
            else:
                console.print(f"[red]Error: {data.get('error', 'Unknown')}")
        except Exception as e:
            console.print(f"[red]Error: {e}")


def spawn_swarm_impl(
    count: int = 111,
    pattern: str = "config/test_matrix/*.yaml",
    stagger: float = 0.5,
) -> None:
    """Spawn multiple bots."""
    if not ensure_manager_running():
        return
    configs = glob.glob(pattern)[:count]
    if not configs:
        console.print(f"[red]Error: No configs found matching: {pattern}")
        return

    console.print(
        f"[cyan]Spawning {len(configs)} bots with "
        f"{stagger}s stagger...[/cyan]"
    )

    with httpx.Client() as client:
        try:
            response = client.post(
                f"{MANAGER_URL}/swarm/spawn-batch",
                json={"config_paths": configs},
            )
            data = response.json()
            if response.status_code == 200:
                console.print(
                    f"[green]✓[/green] Spawned "
                    f"[cyan]{data['count']}[/cyan] bots"
                )
                for bid in data["bot_ids"][:5]:
                    console.print(f"  - {bid}")
                if len(data["bot_ids"]) > 5:
                    console.print(
                        f"  ... and {len(data['bot_ids']) - 5} more"
                    )
            else:
                console.print(f"[red]Error: {data.get('error', 'Unknown')}")
        except Exception as e:
            console.print(f"[red]Error: {e}")


def status_impl(bot_id: str | None = None) -> None:
    """Show swarm or single-bot status."""
    if not ensure_manager_running():
        return
    with httpx.Client() as client:
        try:
            if bot_id:
                response = client.get(
                    f"{MANAGER_URL}/bot/{bot_id}/status"
                )
                if response.status_code == 200:
                    bot = response.json()
                    console.print(f"\n[cyan]Bot Status: {bot['bot_id']}[/cyan]")
                    console.print(f"  PID: {bot['pid']}")
                    console.print(f"  State: {bot['state']}")
                    console.print(f"  Sector: {bot['sector']}")
                    console.print(
                        f"  Credits: {format_credits(bot['credits'])}"
                    )
                    console.print(f"  Turns: {bot['turns_executed']}")
                else:
                    console.print(
                        f"[red]Error: {response.json().get('error')}"
                    )
            else:
                response = client.get(f"{MANAGER_URL}/swarm/status")
                data = response.json()

                console.print("\n[cyan]Swarm Status[/cyan]")
                console.print(
                    f"  Running: [green]{data['running']}[/green] / "
                    f"{data['total_bots']}"
                )
                console.print(
                    f"  Completed: [green]{data['completed']}[/green]"
                )
                console.print(f"  Errors: [red]{data['errors']}[/red]")
                console.print(
                    f"  Total Credits: "
                    f"[cyan]{format_credits(data['total_credits'])}[/cyan]"
                )
                console.print(
                    f"  Total Turns: "
                    f"[cyan]{data['total_turns']:,}[/cyan]"
                )
                console.print(
                    f"  Uptime: "
                    f"[cyan]{format_uptime(data['uptime_seconds'])}[/cyan]"
                )

                if data["bots"]:
                    table = Table(title="Bot Details", show_header=True, show_footer=False)
                    table.add_column("ID", style="cyan")
                    table.add_column("User")
                    table.add_column("State")
                    table.add_column("Activity")
                    table.add_column("Ship")
                    table.add_column("Sec", justify="right")
                    table.add_column("Credits", justify="right")
                    table.add_column("Turns", justify="right")

                    for bot in sorted(
                        data["bots"],
                        key=lambda b: b["bot_id"],
                    )[:20]:
                        state_color = {
                            "running": "green",
                            "paused": "yellow",
                            "completed": "blue",
                            "error": "red",
                        }.get(bot["state"], "white")

                        # Extract just the number from bot_id
                        bot_num = bot["bot_id"].split("-")[-1] if "-" in bot["bot_id"] else bot["bot_id"]

                        # Format activity context
                        activity = bot.get("activity_context", "").upper() if bot.get("activity_context") else "—"
                        if activity == "—":
                            activity = "—"

                        # Format ship info (ship_name or ship_level)
                        ship = bot.get("ship_name") or bot.get("ship_level") or "—"

                        # Format username
                        username = bot.get("username") or "—"

                        table.add_row(
                            bot_num,
                            username,
                            f"[{state_color}]{bot['state']}[/{state_color}]",
                            activity,
                            ship,
                            str(bot["sector"]),
                            format_credits(bot["credits"]),
                            str(bot["turns_executed"]),
                        )

                    if len(data["bots"]) > 20:
                        console.print(
                            f"\n... and {len(data['bots']) - 20} more bots"
                        )
                    console.print(table)

        except Exception as e:
            console.print(f"[red]Error: {e}")


def pause_impl(bot_id: str) -> None:
    """Pause a running bot."""
    if not ensure_manager_running():
        return
    with httpx.Client() as client:
        try:
            response = client.post(
                f"{MANAGER_URL}/bot/{bot_id}/pause"
            )
            if response.status_code == 200:
                console.print(f"[green]✓[/green] Paused bot: {bot_id}")
            else:
                console.print(
                    f"[red]Error: {response.json().get('error')}"
                )
        except Exception as e:
            console.print(f"[red]Error: {e}")


def resume_impl(bot_id: str) -> None:
    """Resume a paused bot."""
    if not ensure_manager_running():
        return
    with httpx.Client() as client:
        try:
            response = client.post(
                f"{MANAGER_URL}/bot/{bot_id}/resume"
            )
            if response.status_code == 200:
                console.print(f"[green]✓[/green] Resumed bot: {bot_id}")
            else:
                console.print(
                    f"[red]Error: {response.json().get('error')}"
                )
        except Exception as e:
            console.print(f"[red]Error: {e}")


def kill_impl(bot_id: str, confirm: bool = True) -> None:
    """Terminate a bot."""
    if not ensure_manager_running():
        return
    if confirm and not click.confirm(f"Kill bot {bot_id}?"):
        return
    with httpx.Client() as client:
        try:
            response = client.delete(
                f"{MANAGER_URL}/bot/{bot_id}"
            )
            if response.status_code == 200:
                console.print(f"[green]✓[/green] Killed bot: {bot_id}")
            else:
                console.print(
                    f"[red]Error: {response.json().get('error')}"
                )
        except Exception as e:
            console.print(f"[red]Error: {e}")


def set_goal_impl(bot_id: str, goal: str) -> None:
    """Set bot goal."""
    if not ensure_manager_running():
        return
    with httpx.Client() as client:
        try:
            response = client.post(
                f"{MANAGER_URL}/bot/{bot_id}/set-goal",
                params={"goal": goal},
            )
            if response.status_code == 200:
                console.print(
                    f"[green]✓[/green] Set {bot_id} goal to: {goal}"
                )
            else:
                console.print(
                    f"[red]Error: {response.json().get('error')}"
                )
        except Exception as e:
            console.print(f"[red]Error: {e}")


def watch_impl() -> None:
    """Watch swarm status in real-time (WebSocket)."""
    if not ensure_manager_running():
        return
    console.print("[cyan]Connecting to swarm manager...[/cyan]")

    try:
        import websockets

        async def watch_swarm() -> None:
            uri = MANAGER_URL.replace("http", "ws") + "/ws/swarm"
            async with websockets.connect(uri) as websocket:
                console.print(
                    "[green]✓[/green] Connected to swarm manager"
                )
                console.print(
                    "[yellow]Press Ctrl+C to stop[/yellow]\n"
                )
                while True:
                    message = await websocket.recv()
                    data = json.loads(message)

                    console.clear()
                    console.print(
                        f"[cyan]Swarm Status - "
                        f"Uptime: {format_uptime(data['uptime_seconds'])}"
                        f"[/cyan]\n"
                    )
                    console.print(
                        f"Running: [green]{data['running']}[/green] / "
                        f"{data['total_bots']} | "
                        f"Completed: [cyan]{data['completed']}[/cyan] | "
                        f"Errors: [red]{data['errors']}[/red]\n"
                    )
                    console.print(
                        f"Total Credits: "
                        f"[cyan]{format_credits(data['total_credits'])}[/cyan] | "
                        f"Total Turns: "
                        f"[cyan]{data['total_turns']:,}[/cyan]\n"
                    )

                    if data["bots"]:
                        top_bots = sorted(
                            data["bots"],
                            key=lambda b: b["credits"],
                            reverse=True,
                        )[:10]

                        console.print("[cyan]Top Bots by Credits:[/cyan]")
                        for bot in top_bots:
                            credits = format_credits(bot["credits"])
                            console.print(
                                f"  {bot['bot_id']}: "
                                f"{credits} credits, "
                                f"Sector {bot['sector']}, "
                                f"Turn {bot['turns_executed']}"
                            )

        asyncio.run(watch_swarm())

    except ImportError:
        console.print(
            "[red]Error: websockets library not found[/red]\n"
            "Install with: pip install websockets"
        )
    except KeyboardInterrupt:
        console.print("\n[yellow]Stopped watching[/yellow]")
    except Exception as e:
        console.print(f"[red]Error: {e}")


# ── Click command group ──


@click.group("swarm")
def swarm_commands() -> None:
    """Swarm manager commands."""


@swarm_commands.command()
@click.option("--config", required=True, help="Path to bot config file")
@click.option("--bot-id", default=None, help="Custom bot ID")
def spawn(config: str, bot_id: str | None) -> None:
    """Spawn a single bot."""
    spawn_impl(config, bot_id)


@swarm_commands.command("spawn-swarm")
@click.option("--count", default=111, help="Number of bots to spawn")
@click.option("--pattern", default="config/test_matrix/*.yaml", help="Config file pattern")
@click.option("--stagger", default=0.5, type=float, help="Delay between spawns")
def spawn_swarm(count: int, pattern: str, stagger: float) -> None:
    """Spawn multiple bots (swarm)."""
    spawn_swarm_impl(count, pattern, stagger)


@swarm_commands.command()
@click.option("--bot-id", default=None, help="Show specific bot status")
def status(bot_id: str | None) -> None:
    """Get swarm status."""
    status_impl(bot_id)


@swarm_commands.command()
@click.option("--bot-id", required=True, help="Bot to pause")
def pause(bot_id: str) -> None:
    """Pause a running bot."""
    pause_impl(bot_id)


@swarm_commands.command()
@click.option("--bot-id", required=True, help="Bot to resume")
def resume(bot_id: str) -> None:
    """Resume a paused bot."""
    resume_impl(bot_id)


@swarm_commands.command()
@click.option("--bot-id", required=True, help="Bot to kill")
def kill(bot_id: str) -> None:
    """Terminate a bot."""
    kill_impl(bot_id)


@swarm_commands.command("set-goal")
@click.option("--bot-id", required=True, help="Bot to modify")
@click.option("--goal", required=True, help="New goal")
def set_goal(bot_id: str, goal: str) -> None:
    """Set bot goal."""
    set_goal_impl(bot_id, goal)


@swarm_commands.command()
def watch() -> None:
    """Watch swarm status in real-time (WebSocket)."""
    watch_impl()


@swarm_commands.command()
def monitor() -> None:
    """Live TUI dashboard."""
    if not ensure_manager_running():
        return
    from bbsbot.tui.swarm_monitor import SwarmMonitor

    asyncio.run(SwarmMonitor().run())


@swarm_commands.command("shell")
def swarm_shell() -> None:
    """Interactive REPL for swarm management."""
    from bbsbot.swarm_shell import SwarmShell

    SwarmShell().cmdloop()
