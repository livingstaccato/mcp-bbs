# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Example: Simple game bot using the extracted framework.

This demonstrates how a future game can leverage the framework patterns
extracted from TW2002 to minimize boilerplate code.
"""

from bbsbot.core import (
    BaseErrorDetector,
    BotBase,
    InputSender,
    PromptWaiter,
)
from bbsbot.terminal import extract_menu_options


class SimpleGameErrorDetector(BaseErrorDetector):
    """Example error detector for a simple game."""

    def __init__(self):
        super().__init__()
        # Register game-specific error patterns
        self.add_error_pattern("invalid_command", ["invalid command", "unknown command"])
        self.add_error_pattern("no_access", ["access denied", "permission denied"])
        self.add_error_pattern("game_over", ["game over", "you died"])


class SimpleGameBot(BotBase):
    """Example bot for a hypothetical simple BBS game.

    This shows how much simpler future games can be by using
    the framework patterns we extracted from TW2002.
    """

    def __init__(self, character_name: str = "Player"):
        super().__init__(character_name)
        self.error_detector = SimpleGameErrorDetector()
        self.score = 0

    async def login(self, username: str, password: str) -> None:
        """Simple login sequence using framework utilities."""
        waiter = PromptWaiter(self.session)
        sender = InputSender(self.session)

        # Wait for username prompt
        result = await waiter.wait_for_prompt(expected_prompt_id="username", timeout_ms=5000)
        await sender.send_input(username, result["input_type"])

        # Wait for password prompt
        result = await waiter.wait_for_prompt(expected_prompt_id="password", timeout_ms=5000)
        await sender.send_input(password, result["input_type"])

        # Wait for main menu
        result = await waiter.wait_for_prompt(expected_prompt_id="main_menu", timeout_ms=10000)

        print(f"✓ Logged in as {username}")

    async def navigate_menu(self) -> None:
        """Navigate game menu using framework utilities."""
        waiter = PromptWaiter(self.session)
        sender = InputSender(self.session)

        # Wait for menu
        result = await waiter.wait_for_prompt(expected_prompt_id="main_menu", timeout_ms=5000)

        # Extract menu options using framework utility
        options = extract_menu_options(result["screen"])
        print(f"Available options: {options}")

        # Select first option
        if options:
            key, description = options[0]
            print(f"Selecting: {description}")
            await sender.send_input(key, result["input_type"])

    async def run(self) -> None:
        """Main game loop - subclass implements game-specific logic."""
        try:
            # Login
            await self.login("testuser", "testpass")

            # Play game
            for turn in range(5):
                print(f"\n--- Turn {turn + 1} ---")
                await self.navigate_menu()

                # Check for errors using framework detector
                waiter = PromptWaiter(self.session)
                result = await waiter.wait_for_prompt(timeout_ms=5000)

                error = self.error_detector.detect_error(result["screen"])
                if error:
                    print(f"⚠️  Error detected: {error}")
                    break

                # Check for loops using inherited method
                if self.is_looping(result["prompt_id"]):
                    print(f"⚠️  Stuck in loop at {result['prompt_id']}")
                    break

            print(f"\n✓ Game complete! Final score: {self.score}")

        finally:
            await self.disconnect()


async def main():
    """Example usage."""
    bot = SimpleGameBot(character_name="Hero")

    # Connect using inherited method
    await bot.connect(host="localhost", port=2323, namespace="simple_game")

    # Run game
    await bot.run()


if __name__ == "__main__":
    # This is just an example - won't actually run without a real BBS
    print(__doc__)
    print("\nThis example demonstrates the framework patterns.")
    print("To run against a real BBS, uncomment the line below:")
    print("# asyncio.run(main())")
