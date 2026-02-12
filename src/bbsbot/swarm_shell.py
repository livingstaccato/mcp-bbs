# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Interactive REPL shell for swarm management."""

from __future__ import annotations

import cmd

from rich.console import Console

from bbsbot.cli_swarm import (
    ensure_manager_running,
    kill_impl,
    pause_impl,
    resume_impl,
    set_goal_impl,
    spawn_impl,
    status_impl,
    watch_impl,
)

console = Console()


class SwarmShell(cmd.Cmd):
    """Interactive REPL for swarm management."""

    intro = "BBSBot Swarm Shell - Type 'help' for commands, 'exit' to quit"
    prompt = "(swarm) "

    def preloop(self) -> None:
        if not ensure_manager_running():
            console.print("[red]Cannot start shell - manager unavailable[/red]")

    def do_status(self, arg: str) -> None:
        """Show status: status [bot_id]"""
        status_impl(arg.strip() or None)

    def do_spawn(self, arg: str) -> None:
        """Spawn bot: spawn <config> [bot_id]"""
        args = arg.split()
        if not args:
            console.print("[yellow]Usage: spawn <config> [bot_id][/yellow]")
            return
        spawn_impl(args[0], args[1] if len(args) > 1 else None)

    def do_kill(self, arg: str) -> None:
        """Kill bot: kill <bot_id>"""
        if not arg.strip():
            console.print("[yellow]Usage: kill <bot_id>[/yellow]")
            return
        kill_impl(arg.strip(), confirm=False)

    def do_pause(self, arg: str) -> None:
        """Pause bot: pause <bot_id>"""
        if not arg.strip():
            console.print("[yellow]Usage: pause <bot_id>[/yellow]")
            return
        pause_impl(arg.strip())

    def do_resume(self, arg: str) -> None:
        """Resume bot: resume <bot_id>"""
        if not arg.strip():
            console.print("[yellow]Usage: resume <bot_id>[/yellow]")
            return
        resume_impl(arg.strip())

    def do_goal(self, arg: str) -> None:
        """Set goal: goal <bot_id> <goal>"""
        args = arg.split()
        if len(args) < 2:
            console.print("[yellow]Usage: goal <bot_id> <goal>[/yellow]")
            return
        set_goal_impl(args[0], args[1])

    def do_watch(self, arg: str) -> None:
        """Watch live status (Ctrl+C to stop)"""
        watch_impl()

    def do_exit(self, arg: str) -> bool:
        """Exit shell"""
        return True

    def do_quit(self, arg: str) -> bool:
        """Exit shell"""
        return True

    do_EOF = do_exit
