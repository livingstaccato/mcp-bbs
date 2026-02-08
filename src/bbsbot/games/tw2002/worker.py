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

            await self._http_client.post(
                f"{self.manager_url}/bot/{self.bot_id}/status",
                json={
                    "sector": self.current_sector or 0,
                    "credits": credits,
                    "turns_executed": self.turns_used,
                    "state": "running",
                },
            )
        except Exception as e:
            logger.debug(f"Failed to report status: {e}")

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

    async def cleanup(self) -> None:
        """Clean up resources."""
        await self.stop_status_reporter()
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
    finally:
        # Final status report
        await worker.report_status()
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
