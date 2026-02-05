from __future__ import annotations

import asyncio
import inspect
import sys
from typing import Callable

import click

from bbsbot.app import create_app
from bbsbot.settings import Settings


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
def cli() -> None:
    """bbsbot command line interface."""


@cli.command("serve")
def serve() -> None:
    """Run the FastMCP server (stdio transport)."""
    app = create_app(Settings())
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
) -> None:
    """Watch the live screen output from a BBS session."""
    from bbsbot.core.session_manager import SessionManager

    settings = Settings()

    async def _run() -> None:
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


@tw2002_group.command("bot")
@click.option("-c", "--config", "config_path", type=click.Path(path_type=str))
@click.option("--generate-config", is_flag=True)
@click.option("--host", type=str)
@click.option("--port", type=int)
@click.option("-v", "--verbose", is_flag=True)
@click.option("--strategy", type=click.Choice(["profitable_pairs", "opportunistic", "twerk_optimized"]))
@click.option("--target-credits", type=int)
@click.option("--max-turns", type=int)
@click.option("--watch", is_flag=True, help="Print live screens as the bot runs.")
@click.option("--watch-interval", type=float, default=0.0, show_default=True)
@click.option("--watch-clear/--no-watch-clear", default=True, show_default=True)
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
) -> None:
    """Run the TW2002 trading bot."""
    from bbsbot.tw2002.cli import run_bot_cli

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


def main() -> None:
    cli.main()


if __name__ == "__main__":
    main()
