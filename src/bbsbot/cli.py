from __future__ import annotations

import asyncio
import inspect
import sys
from typing import Callable

import click

from bbsbot.app import create_app
from bbsbot.cli_swarm import swarm_commands
from bbsbot.settings import Settings


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
def cli() -> None:
    """bbsbot command line interface."""


@cli.command("serve")
@click.option("--watch-socket/--no-watch-socket", default=False, show_default=True)
@click.option("--watch-host", default="127.0.0.1", show_default=True)
@click.option("--watch-port", type=int, default=8765, show_default=True)
@click.option("--watch-protocol", type=click.Choice(["raw", "json"]), default="raw", show_default=True)
@click.option("--watch-clear/--no-watch-clear", default=False, show_default=True)
@click.option("--watch-metadata/--no-watch-metadata", default=False, show_default=True)
@click.option("--watch-include-text/--no-watch-include-text", default=False, show_default=True)
@click.option(
    "--tools",
    type=str,
    default=None,
    help="Comma-separated tool namespaces to expose (e.g., 'bbs' or 'bbs,tw2002'). If not provided, no tools are exposed.",
)
def serve(
    watch_socket: bool,
    watch_host: str,
    watch_port: int,
    watch_protocol: str,
    watch_clear: bool,
    watch_metadata: bool,
    watch_include_text: bool,
    tools: str | None,
) -> None:
    """Run the FastMCP server (stdio transport).

    Specify which tool namespaces to expose with --tools.

    Examples:
        bbsbot serve --tools bbs                 # BBS tools only
        bbsbot serve --tools tw2002              # TW2002 tools only
        bbsbot serve --tools bbs,tw2002          # BBS tools + TW2002 tools
    """
    if watch_socket:
        from bbsbot.watch import watch_settings

        watch_settings.enabled = True
        watch_settings.host = watch_host
        watch_settings.port = watch_port
        watch_settings.protocol = watch_protocol
        watch_settings.send_clear = watch_clear
        watch_settings.metadata = watch_metadata
        watch_settings.include_snapshot_text = watch_include_text

    try:
        app = create_app(Settings(), tool_prefixes=tools)
    except ValueError as e:
        raise click.BadParameter(str(e), param_hint="--tools") from e
    app.run()


@cli.command("watch")
@click.option("--host", default="localhost", show_default=True)
@click.option("--port", type=int, default=23, show_default=True)
@click.option("--cols", type=int, default=80, show_default=True)
@click.option("--rows", type=int, default=25, show_default=True)
@click.option("--term", default="ANSI", show_default=True)
@click.option("--interval", type=float, default=0.25, show_default=True, help="Poll interval in seconds.")
@click.option("--max-bytes", type=int, default=8192, show_default=True)
@click.option("--clear/--no-clear", default=True, show_default=True)
@click.option("--once", is_flag=True, help="Read once and exit.")
@click.option("--learning/--no-learning", default=True, show_default=True)
@click.option("--show-prompt/--no-prompt", default=True, show_default=True)
@click.option("--broadcast/--no-broadcast", default=False, show_default=True)
@click.option("--broadcast-host", default="127.0.0.1", show_default=True)
@click.option("--broadcast-port", type=int, default=8765, show_default=True)
@click.option("--broadcast-protocol", type=click.Choice(["raw", "json"]), default="raw", show_default=True)
@click.option("--broadcast-clear/--no-broadcast-clear", default=False, show_default=True)
def watch(
    host: str,
    port: int,
    cols: int,
    rows: int,
    term: str,
    interval: float,
    max_bytes: int,
    clear: bool,
    once: bool,
    learning: bool,
    show_prompt: bool,
    broadcast: bool,
    broadcast_host: str,
    broadcast_port: int,
    broadcast_protocol: str,
    broadcast_clear: bool,
) -> None:
    """Watch the live screen output from a BBS session."""
    from bbsbot.core.session_manager import SessionManager
    from bbsbot.watch import WatchManager, watch_settings

    settings = Settings()

    async def _run() -> None:
        watch_manager: WatchManager | None = None
        if broadcast:
            watch_settings.enabled = True
            watch_settings.host = broadcast_host
            watch_settings.port = broadcast_port
            watch_settings.protocol = broadcast_protocol
            watch_settings.send_clear = broadcast_clear
            watch_manager = WatchManager()
            await watch_manager.start()

        manager = SessionManager()
        session_id = await manager.create_session(
            host=host,
            port=port,
            cols=cols,
            rows=rows,
            term=term,
            send_newline=True,
            reuse=True,
        )
        session = await manager.get_session(session_id)
        if learning:
            await manager.enable_learning(session_id, settings.knowledge_root, namespace="tw2002")
        if watch_manager is not None:
            watch_manager.attach_session(session)

        try:
            while True:
                snapshot = await session.read(int(interval * 1000), max_bytes)
                if clear:
                    click.echo("\x1b[2J\x1b[H", nl=False)
                screen = snapshot.get("screen", "")
                click.echo(screen)
                if show_prompt and (detected := snapshot.get("prompt_detected")):
                    click.echo("")
                    click.echo(f"[prompt] {detected.get('prompt_id')} ({detected.get('input_type')})")
                if once:
                    break
        finally:
            await manager.close_all_sessions()
            if watch_manager is not None:
                await watch_manager.stop()

    asyncio.run(_run())


@cli.command("script")
@click.argument("name")
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def script(name: str, args: tuple[str, ...]) -> None:
    """Run a bundled legacy script by name."""
    module_name = f"bbsbot.commands.scripts.{name}"
    try:
        module = __import__(module_name, fromlist=["main"])
    except ModuleNotFoundError as exc:
        raise click.ClickException(f"Unknown script: {name}") from exc

    main: Callable[[], object] | None = getattr(module, "main", None)

    sys_argv = [f"bbsbot script {name}", *args]
    sys.argv = sys_argv

    if main is None:
        import runpy

        runpy.run_module(module_name, run_name="__main__")
        return

    if inspect.iscoroutinefunction(main):
        asyncio.run(main())
    else:
        main()


@cli.group("tw2002")
def tw2002_group() -> None:
    """Trade Wars 2002 commands."""


@tw2002_group.command("check")
@click.option("--host", default="localhost", show_default=True, help="BBS host to check")
@click.option("--port", default=2002, type=int, show_default=True, help="BBS port to check")
@click.option("--timeout", default=5, type=int, show_default=True, help="Connection timeout in seconds")
def tw2002_check(host: str, port: int, timeout: int) -> None:
    """Verify TW2002 server is reachable and responding."""
    from bbsbot.games.tw2002.cli import run_health_check

    run_health_check(host, port, timeout)


@tw2002_group.command("bot")
@click.option("-c", "--config", "config_path", type=click.Path(path_type=str))
@click.option("--generate-config", is_flag=True)
@click.option("--host", type=str)
@click.option("--port", type=int)
@click.option("-v", "--verbose", is_flag=True)
@click.option(
    "--strategy",
    type=click.Choice(["profitable_pairs", "opportunistic", "twerk_optimized", "ai_strategy"]),
)
@click.option("--target-credits", type=int)
@click.option("--max-turns", type=int)
@click.option("--watch", is_flag=True, help="Print live screens as the bot runs.")
@click.option("--watch-interval", type=float, default=0.0, show_default=True)
@click.option("--watch-clear/--no-watch-clear", default=True, show_default=True)
@click.option("--watch-socket", is_flag=True, help="Broadcast ANSI screens over TCP for spying.")
@click.option("--watch-socket-host", default="127.0.0.1", show_default=True)
@click.option("--watch-socket-port", type=int, default=8765, show_default=True)
@click.option("--watch-socket-protocol", type=click.Choice(["raw", "json"]), default="raw", show_default=True)
@click.option("--watch-socket-clear/--no-watch-socket-clear", default=False, show_default=True)
def tw2002_bot(
    config_path: str | None,
    generate_config: bool,
    host: str | None,
    port: int | None,
    verbose: bool,
    strategy: str | None,
    target_credits: int | None,
    max_turns: int | None,
    watch: bool,
    watch_interval: float,
    watch_clear: bool,
    watch_socket: bool,
    watch_socket_host: str,
    watch_socket_port: int,
    watch_socket_protocol: str,
    watch_socket_clear: bool,
) -> None:
    """Run the TW2002 trading bot."""
    from bbsbot.games.tw2002.cli import run_bot_cli

    run_bot_cli(
        config_path=config_path,
        generate_config=generate_config,
        host=host,
        port=port,
        verbose=verbose,
        strategy=strategy,
        target_credits=target_credits,
        max_turns=max_turns,
        watch=watch,
        watch_interval=watch_interval,
        watch_clear=watch_clear,
        watch_socket=watch_socket,
        watch_socket_host=watch_socket_host,
        watch_socket_port=watch_socket_port,
        watch_socket_protocol=watch_socket_protocol,
        watch_socket_clear=watch_socket_clear,
    )


@tw2002_group.command("play")
@click.option("--mode", type=click.Choice(["full", "intelligent", "trading", "1000turns"]))
def tw2002_play(mode: str | None) -> None:
    """Run a bundled TW2002 play script."""
    if not mode:
        raise click.ClickException("--mode is required")

    match mode:
        case "full":
            script("play_tw2002_full", ())
        case "intelligent":
            script("play_tw2002_intelligent", ())
        case "trading":
            script("play_tw2002_trading", ())
        case "1000turns":
            script("play_tw2002_1000turns", ())
        case _:
            raise click.ClickException(f"Unknown mode: {mode}")


@tw2002_group.command("list-resume")
@click.option("--json", "as_json", is_flag=True, help="Output JSON.")
@click.option("--active-within-hours", type=float)
@click.option("--min-credits", type=int)
@click.option("--require-sector", is_flag=True)
@click.option("--name-prefix", type=str)
def tw2002_list_resume(
    as_json: bool,
    active_within_hours: float | None,
    min_credits: int | None,
    require_sector: bool,
    name_prefix: str | None,
) -> None:
    """List resumable TW2002 characters from local state."""
    from bbsbot.paths import default_knowledge_root
    from bbsbot.games.tw2002.resume import as_dict, list_resumable_tw2002

    entries = list_resumable_tw2002(
        default_knowledge_root(),
        active_within_hours=active_within_hours,
        min_credits=min_credits,
        require_sector=require_sector,
        name_prefix=name_prefix,
    )
    if as_json:
        import json

        click.echo(json.dumps(as_dict(entries), indent=2))
        return

    if not entries:
        click.echo("No resumable characters found.")
        return

    for entry in entries:
        host = f"{entry.host}:{entry.port}" if entry.port is not None else entry.host
        click.echo(f"{host}  resumable:{len(entry.resumable)}  dead:{entry.dead}  total:{entry.total}")
        for char in entry.resumable:
            click.echo(
                f"  - {char.name}  credits:{char.credits}  sector:{char.sector}  last_active:{char.last_active}"
            )


@cli.group("replay")
def replay_group() -> None:
    """Replay tools."""


@replay_group.command("raw")
@click.argument("log", type=click.Path(path_type=str))
@click.argument("out", type=click.Path(path_type=str))
def replay_raw(log: str, out: str) -> None:
    """Rebuild raw ANSI stream from JSONL log."""
    from bbsbot.replay.raw import rebuild_raw_stream

    rebuild_raw_stream(log, out)


@replay_group.command("view")
@click.argument("log", type=click.Path(path_type=str))
@click.option("--speed", type=float, default=1.0, show_default=True)
@click.option("--step", is_flag=True)
@click.option("--events", multiple=True, default=["read", "screen"], show_default=True)
def replay_view(log: str, speed: float, step: bool, events: tuple[str, ...]) -> None:
    """Replay a session log in the terminal."""
    from bbsbot.replay.viewer import replay_log

    replay_log(log, speed=speed, step=step, events=list(events))


@cli.command("spy")
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", type=int, default=8765, show_default=True)
@click.option("--encoding", default="cp437", show_default=True, help="Decode bytes before printing (set to '' for raw).")
def spy(host: str, port: int, encoding: str) -> None:
    """Attach to a watch socket and render ANSI output locally."""
    import asyncio
    import sys

    async def _run() -> None:
        reader, writer = await asyncio.open_connection(host, port)
        try:
            while True:
                data = await reader.read(8192)
                if not data:
                    break
                if encoding:
                    text = data.decode(encoding, errors="replace")
                    sys.stdout.write(text)
                    sys.stdout.flush()
                else:
                    sys.stdout.buffer.write(data)
                    sys.stdout.buffer.flush()
        finally:
            writer.close()
            await writer.wait_closed()

    asyncio.run(_run())


@tw2002_group.command("parse-semantic")
@click.option(
    "-i",
    "--input",
    "input_path",
    type=click.Path(dir_okay=False, path_type=str),
    help="Read screen text from a file instead of stdin.",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["kv", "json"]),
    default="kv",
    show_default=True,
    help="Output format for parsed semantic data.",
)
def tw2002_parse_semantic(input_path: str | None, output_format: str) -> None:
    """Parse TW2002 semantic data from screen text (stdin or file)."""
    import json

    from bbsbot.games.tw2002.parsing import extract_semantic_kv

    if input_path:
        with open(input_path, "r", encoding="utf-8") as handle:
            screen = handle.read()
    else:
        screen = sys.stdin.read()

    if not screen.strip():
        raise click.ClickException("No input received. Provide --input or pipe screen text via stdin.")

    data = extract_semantic_kv(screen)
    if output_format == "json":
        click.echo(json.dumps(data, sort_keys=True))
        return

    if not data:
        click.echo("")
        return

    kv = " ".join(f"{key}={data[key]}" for key in sorted(data))
    click.echo(f"semantic {kv}")


@cli.command("tui")
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", type=int, default=8765, show_default=True)
@click.option("--log", "log_path", type=click.Path(path_type=str))
def tui(host: str, port: int, log_path: str | None) -> None:
    """Hybrid live/replay TUI for spying on sessions."""
    from bbsbot.tui import run_tui

    asyncio.run(run_tui(host=host, port=port, log_path=log_path))


cli.add_command(swarm_commands, name="swarm")


@cli.command("s", hidden=True)
@click.option("--bot-id", default=None)
def status_alias(bot_id: str | None) -> None:
    """Alias for swarm status."""
    from bbsbot.cli_swarm import status_impl

    status_impl(bot_id)


@cli.command("sp", hidden=True)
@click.option("--config", required=True)
@click.option("--bot-id", default=None)
def spawn_alias(config: str, bot_id: str | None) -> None:
    """Alias for swarm spawn."""
    from bbsbot.cli_swarm import spawn_impl

    spawn_impl(config, bot_id)


def main() -> None:
    cli.main()


if __name__ == "__main__":
    main()
