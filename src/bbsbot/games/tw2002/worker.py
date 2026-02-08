"""Bot worker process entry point for swarm management.

Runs a single bot instance and reports status to swarm manager.
"""

from __future__ import annotations

import asyncio
import click
import httpx
from pathlib import Path

from bbsbot.games.tw2002.bot import TradingBot
from bbsbot.games.tw2002.config import BotConfig
from bbsbot.logging import get_logger

logger = get_logger(__name__)


class WorkerBot(TradingBot):
    """Bot worker with manager communication."""

    def __init__(self, bot_id: str, config: BotConfig, manager_url: str):
        """Initialize worker bot.

        Args:
            bot_id: Unique bot identifier
            config: Bot configuration
            manager_url: URL of swarm manager
        """
        super().__init__(character_name=f"{config.character.name}_{bot_id}", config=config)
        self.bot_id = bot_id
        self.manager_url = manager_url
        self.client = httpx.AsyncClient(timeout=10)

    async def register_with_manager(self) -> None:
        """Register this bot with the swarm manager."""
        try:
            await self.client.post(
                f"{self.manager_url}/bot/{self.bot_id}/register",
                json={"pid": self.pid},
            )
            logger.info(f"Registered with manager: {self.bot_id}")
        except Exception as e:
            logger.warning(f"Failed to register with manager: {e}")

    async def report_status(self) -> None:
        """Report current status to manager."""
        try:
            await self.client.post(
                f"{self.manager_url}/bot/{self.bot_id}/status",
                json={
                    "sector": self.current_sector,
                    "credits": self.current_credits,
                    "turns_executed": self._current_turn,
                    "state": "running",
                },
            )
        except Exception as e:
            logger.debug(f"Failed to report status: {e}")

    async def run_with_reporting(self, max_turns: int | None = None) -> None:
        """Run bot with periodic status reporting.

        Args:
            max_turns: Maximum turns to execute
        """
        # Register first
        await self.register_with_manager()

        # Run trading loop with status updates
        while True:
            try:
                # Execute next turn
                await self.execute_turn()

                # Report status every 5 turns
                if self._current_turn % 5 == 0:
                    await self.report_status()

                # Check completion
                if (
                    max_turns
                    and self._current_turn >= max_turns
                ):
                    logger.info(f"Completed {max_turns} turns")
                    break

            except KeyboardInterrupt:
                logger.info("Bot interrupted")
                break
            except Exception as e:
                logger.error(f"Error in trading loop: {e}")
                await self.report_status()
                break

        # Final status update
        await self.report_status()
        await self.client.aclose()


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
    default="http://localhost:8000",
    help="Swarm manager URL",
)
async def main(config: str, bot_id: str, manager_url: str) -> None:
    """Run a bot worker process.

    Args:
        config: Path to bot config YAML
        bot_id: Unique bot ID
        manager_url: URL of swarm manager
    """
    try:
        # Load configuration
        config_path = Path(config)
        logger.info(f"Loading config: {config_path}")

        # Parse YAML config
        import yaml

        with open(config_path) as f:
            config_dict = yaml.safe_load(f)

        config_obj = BotConfig(**config_dict)

        # Create and run worker bot
        worker = WorkerBot(bot_id, config_obj, manager_url)

        # Connect to server
        logger.info(
            f"Connecting to {config_obj.connection.host}:"
            f"{config_obj.connection.port}"
        )
        await worker.connect(
            host=config_obj.connection.host,
            port=config_obj.connection.port,
        )

        # Run login and trading loop
        logger.info("Starting login sequence")
        await worker.login_sequence(
            game_password=config_obj.connection.game_password,
            character_password=(
                config_obj.connection.character_password
                or config_obj.character.password
            ),
            username=config_obj.connection.username or config_obj.character.name,
        )

        logger.info("Login successful, starting trading")
        await worker.run_with_reporting(
            max_turns=config_obj.session.max_turns_per_session
        )

    except Exception as e:
        logger.error(f"Bot worker error: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    asyncio.run(main())
