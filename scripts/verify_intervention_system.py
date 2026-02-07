#!/usr/bin/env python3
"""Automatic verification of intervention system across multiple games.

This script:
1. Connects to localhost:2002
2. Discovers available games
3. Tests intervention system on each game
4. Reports results and anomalies detected
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from bbsbot.games.tw2002 import TradingBot
from bbsbot.games.tw2002.config import BotConfig
from bbsbot.games.tw2002.connection import connect
from bbsbot.games.tw2002.io import send_input, wait_and_respond
from bbsbot.logging import get_logger

logger = get_logger(__name__)


class InterventionVerifier:
    """Verifies intervention system across multiple games."""

    def __init__(self):
        self.results: list[dict[str, Any]] = []
        self.games_tested = 0
        self.interventions_triggered = 0
        self.anomalies_detected = 0

    async def discover_games(self, bot: TradingBot) -> list[dict[str, Any]]:
        """Discover available games on the server.

        Returns:
            List of game dicts with keys: letter, name, players, status
        """
        logger.info("Discovering available games...")

        games = []

        try:
            # Navigate to game selection menu
            for _ in range(10):
                input_type, prompt_id, screen, kv_data = await wait_and_respond(
                    bot, timeout_ms=5000
                )

                # Check if we're at a game selection menu
                if "menu_selection" in prompt_id or "select game" in screen.lower():
                    # Parse game list from screen
                    lines = screen.split("\n")
                    for line in lines:
                        # Look for lines like "A) Trade Wars 2002 - Game 1 (5 players)"
                        if ")" in line and any(
                            game in line.lower()
                            for game in ["trade wars", "tw", "game"]
                        ):
                            parts = line.split(")")
                            if len(parts) >= 2:
                                letter = parts[0].strip()
                                name = parts[1].strip()
                                games.append(
                                    {
                                        "letter": letter,
                                        "name": name,
                                        "raw_line": line.strip(),
                                    }
                                )

                    if games:
                        logger.info(f"Discovered {len(games)} games")
                        return games

                # Handle login prompts
                if "login_name" in prompt_id:
                    await send_input(bot, "verifier", input_type)
                elif "login_pass" in prompt_id or "password" in prompt_id:
                    await send_input(bot, "verify123", input_type)
                elif input_type == "any_key":
                    await send_input(bot, "", input_type)

        except Exception as e:
            logger.error(f"Failed to discover games: {e}")

        return games

    async def verify_game(
        self, game_letter: str, game_name: str, max_turns: int = 50
    ) -> dict[str, Any]:
        """Verify intervention system on a specific game.

        Args:
            game_letter: Game selection letter (A, B, C, etc.)
            game_name: Human-readable game name
            max_turns: Maximum turns to play

        Returns:
            Dict with verification results
        """
        logger.info(f"\n{'='*80}")
        logger.info(f"Testing game {game_letter}: {game_name}")
        logger.info(f"{'='*80}")

        result = {
            "game_letter": game_letter,
            "game_name": game_name,
            "success": False,
            "turns_played": 0,
            "interventions": [],
            "anomalies": [],
            "opportunities": [],
            "error": None,
        }

        bot = None
        try:
            # Create bot with intervention enabled
            config = BotConfig.from_yaml(
                Path(__file__).parent.parent / "config" / "tw2002_bot.yaml"
            )
            config.trading.ai_strategy.intervention.enabled = True
            config.trading.ai_strategy.intervention.min_priority = "medium"
            config.trading.ai_strategy.intervention.cooldown_turns = 3
            config.session.max_turns_per_session = max_turns

            bot = TradingBot(config=config)

            # Connect and login
            await connect(bot)
            logger.info("Connected to server")

            # Navigate to game
            await self._navigate_to_game(bot, game_letter)
            logger.info(f"Entered game {game_letter}")

            # Play the game with intervention monitoring
            turns = 0
            while turns < max_turns:
                try:
                    # Get intervention status
                    if hasattr(bot, "strategy") and hasattr(
                        bot.strategy, "_intervention_trigger"
                    ):
                        trigger = bot.strategy._intervention_trigger
                        if trigger and trigger.enabled:
                            # Log current intervention state
                            anomalies = trigger.detector.recent_anomalies
                            opportunities = trigger.detector.recent_opportunities

                            if anomalies:
                                result["anomalies"].extend(
                                    [a.model_dump() for a in anomalies]
                                )
                                logger.info(
                                    f"Turn {turns}: Detected {len(anomalies)} anomalies"
                                )

                            if opportunities:
                                result["opportunities"].extend(
                                    [o.model_dump() for o in opportunities]
                                )
                                logger.info(
                                    f"Turn {turns}: Detected {len(opportunities)} opportunities"
                                )

                    # Take a turn
                    await bot._cycle()
                    turns += 1
                    result["turns_played"] = turns

                    if turns % 10 == 0:
                        logger.info(f"Completed {turns} turns")

                except Exception as e:
                    logger.error(f"Error on turn {turns}: {e}")
                    result["error"] = str(e)
                    break

            result["success"] = True
            logger.info(f"\nCompleted {turns} turns in game {game_letter}")

        except Exception as e:
            logger.error(f"Failed to verify game {game_letter}: {e}")
            result["error"] = str(e)

        finally:
            if bot and bot.session:
                try:
                    await bot.session.disconnect()
                except Exception:
                    pass

        return result

    async def _navigate_to_game(self, bot: TradingBot, game_letter: str) -> None:
        """Navigate from main menu to selected game.

        Args:
            bot: Bot instance
            game_letter: Game selection letter
        """
        for step in range(20):
            input_type, prompt_id, screen, kv_data = await wait_and_respond(
                bot, timeout_ms=5000
            )

            # Check if we're in the game (command prompt)
            if "command" in prompt_id.lower() or "sector_command" in prompt_id:
                logger.info("Reached game command prompt")
                return

            # Handle various prompts
            if "menu_selection" in prompt_id or "select game" in screen.lower():
                await send_input(bot, game_letter, input_type)
            elif "login_name" in prompt_id:
                await send_input(bot, "verifier", input_type)
            elif "login_pass" in prompt_id or "password" in prompt_id.lower():
                await send_input(bot, "verify123", input_type)
            elif "new_character" in prompt_id.lower() or "start a new" in screen.lower():
                await send_input(bot, "Y", input_type)
            elif "ansi" in prompt_id.lower():
                await send_input(bot, "Y", input_type)
            elif "name" in prompt_id.lower() and "ship" not in prompt_id.lower():
                await send_input(bot, f"Verify{game_letter}", input_type)
            elif "ship" in prompt_id.lower() and "name" in prompt_id.lower():
                await send_input(bot, f"Verifier-{game_letter}", input_type)
            elif "confirm" in prompt_id.lower() or "(y/n)" in screen.lower():
                await send_input(bot, "Y", input_type)
            elif input_type == "any_key":
                await send_input(bot, "", input_type)
            elif "tw_game_menu" in prompt_id:
                await send_input(bot, "T", input_type)  # T to play
            else:
                logger.debug(f"Step {step}: {prompt_id}")

        raise RuntimeError("Failed to navigate to game")

    async def run_verification(self, max_games: int = 5, turns_per_game: int = 50) -> None:
        """Run full verification suite.

        Args:
            max_games: Maximum number of games to test
            turns_per_game: Turns to play per game
        """
        logger.info("="*80)
        logger.info("INTERVENTION SYSTEM VERIFICATION")
        logger.info("="*80)
        logger.info(f"Target: localhost:2002")
        logger.info(f"Max games: {max_games}")
        logger.info(f"Turns per game: {turns_per_game}")
        logger.info("="*80)

        # Discover games
        bot = TradingBot()
        try:
            await connect(bot)
            games = await self.discover_games(bot)
            await bot.session.disconnect()
        except Exception as e:
            logger.error(f"Failed to discover games: {e}")
            return

        if not games:
            logger.error("No games discovered!")
            return

        logger.info(f"\nFound {len(games)} games:")
        for game in games:
            logger.info(f"  {game['letter']}: {game['name']}")

        # Test each game
        games_to_test = games[:max_games]
        for game in games_to_test:
            result = await self.verify_game(
                game["letter"], game["name"], turns_per_game
            )
            self.results.append(result)

            if result["success"]:
                self.games_tested += 1
                self.interventions_triggered += len(result.get("interventions", []))
                self.anomalies_detected += len(result.get("anomalies", []))

            # Small delay between games
            await asyncio.sleep(2)

        # Print summary
        self._print_summary()

    def _print_summary(self) -> None:
        """Print verification summary."""
        logger.info("\n" + "="*80)
        logger.info("VERIFICATION SUMMARY")
        logger.info("="*80)
        logger.info(f"Games tested: {self.games_tested}")
        logger.info(f"Interventions triggered: {self.interventions_triggered}")
        logger.info(f"Anomalies detected: {self.anomalies_detected}")
        logger.info("")

        # Per-game results
        for result in self.results:
            status = "✓" if result["success"] else "✗"
            logger.info(
                f"{status} {result['game_letter']}: {result['game_name']} "
                f"({result['turns_played']} turns)"
            )

            if result.get("anomalies"):
                anomaly_types = {}
                for a in result["anomalies"]:
                    atype = a.get("type", "unknown")
                    anomaly_types[atype] = anomaly_types.get(atype, 0) + 1
                logger.info(f"  Anomalies: {anomaly_types}")

            if result.get("opportunities"):
                opp_types = {}
                for o in result["opportunities"]:
                    otype = o.get("type", "unknown")
                    opp_types[otype] = opp_types.get(otype, 0) + 1
                logger.info(f"  Opportunities: {opp_types}")

            if result.get("error"):
                logger.info(f"  Error: {result['error']}")

        logger.info("="*80)

        # Save detailed results
        results_file = Path(__file__).parent.parent / "verification_results.json"
        with open(results_file, "w") as f:
            json.dump(
                {
                    "timestamp": time.time(),
                    "summary": {
                        "games_tested": self.games_tested,
                        "interventions_triggered": self.interventions_triggered,
                        "anomalies_detected": self.anomalies_detected,
                    },
                    "results": self.results,
                },
                f,
                indent=2,
            )
        logger.info(f"Detailed results saved to: {results_file}")


async def main():
    """Main entry point."""
    verifier = InterventionVerifier()
    await verifier.run_verification(max_games=3, turns_per_game=30)


if __name__ == "__main__":
    asyncio.run(main())
