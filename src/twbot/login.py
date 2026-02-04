"""Login sequence handling for TW2002."""

import asyncio

from .io import wait_and_respond, send_input
from .parsing import _extract_game_options, _select_trade_wars_game
from .logging_utils import logger


async def login_sequence(
    bot,
    game_password: str = "game",
    character_password: str = "tim",
    username: str = "claude",
):
    """Complete login sequence from telnet login to game entry.

    This is a reactive approach: detect the prompt, respond appropriately,
    and continue based on what we see next.

    Args:
        bot: TradingBot instance
        game_password: Password for the game
        character_password: Password for the character
        username: Username for login
    """
    print("\n" + "=" * 80)
    print("PHASE 1: Login Sequence")
    print("=" * 80)

    step = 0
    consecutive_same_menu = 0
    last_menu = None
    twgs_menu_attempts = 0

    # Loop until we reach the game
    for _ in range(50):  # Max 50 steps to prevent infinite loops
        step += 1

        try:
            input_type, prompt_id, screen = await wait_and_respond(
                bot, timeout_ms=5000
            )
        except RuntimeError as e:
            if "Stuck in loop" in str(e):
                # Try to escape by sending Q (quit) or ESC
                print(f"\n⚠️  Loop detected: {e}")
                print("    → Attempting to escape with Q")
                await bot.session.send("Q")
                await asyncio.sleep(0.5)
                # Reset loop detection
                bot.loop_detection.clear()
                bot.last_prompt_id = None
                continue
            else:
                raise

        print(f"[{step}] {prompt_id} ({input_type})")

        # Track TWGS menu attempts to try alternate game
        if "twgs_select_game" in prompt_id:
            twgs_menu_attempts += 1
        else:
            twgs_menu_attempts = 0

        # Track if we're stuck in the same menu
        if prompt_id == last_menu:
            consecutive_same_menu += 1
            if consecutive_same_menu >= 2:
                print(f"    ⚠️  Same menu {consecutive_same_menu} times - trying Q to quit")
                await bot.session.send("Q")
                await asyncio.sleep(0.5)
                consecutive_same_menu = 0
                continue
        else:
            consecutive_same_menu = 0
            last_menu = prompt_id

        # Extract key text for decision making
        screen_lower = screen.lower()

        # Handle different prompts
        if "login_name" in prompt_id and "telnet" not in screen_lower:
            # Character name prompt (not telnet login)
            print(f"    → Sending username: {username}")
            await send_input(bot, username, input_type)

        elif "login_name" in prompt_id and "telnet" in screen_lower:
            # Telnet login - just press Enter
            print("    → Skipping telnet login")
            await bot.session.send("\r")
            await asyncio.sleep(0.3)

        elif "twgs_select_game" in prompt_id:
            # Check if this is actually the game selection menu
            options = _extract_game_options(screen)
            if not options:
                # No options found - might be in wrong menu
                print("    ⚠️  No game options found, sending Q to quit")
                await bot.session.send("Q")
                await asyncio.sleep(0.5)
                continue

            # TWGS game selection menu - send JUST the letter, not with \r
            # Try A first time, then try B on retry
            if twgs_menu_attempts >= 3:
                print(f"    → TWGS menu attempt {twgs_menu_attempts}: Trying B (alternate game)")
                await bot.session.send("B")  # Try alternate game
            else:
                game_letter = _select_trade_wars_game(screen)
                print(f"    → Sending {game_letter} to select game (single key, no return)")
                await bot.session.send(game_letter)  # Single key - NO \r
            await asyncio.sleep(0.5)

        elif "private_game_password" in prompt_id:
            # Game password prompt
            print(f"    → Sending game password")
            await send_input(bot, game_password, input_type)

        elif "game_password" in prompt_id:
            # In-game password (character password)
            print(f"    → Sending character password")
            await send_input(bot, character_password, input_type)

        elif "use_ansi_graphics" in prompt_id:
            # ANSI graphics selection
            print("    → Selecting ANSI graphics (y)")
            await bot.session.send("y")
            await asyncio.sleep(0.3)

        elif input_type == "any_key":
            # Pause/pagination prompt
            # If we keep seeing any_key and cycling back, try Enter instead of space
            if prompt_id == "prompt.any_key" and bot.last_prompt_id == "prompt.any_key":
                print("    → any_key loop detected, trying Enter instead")
                await bot.session.send("\r")
            else:
                print("    → Pressing space to continue")
                await send_input(bot, "", input_type)

        elif "menu_selection" in prompt_id:
            # Generic menu selection - check what menu we're at
            if ("game" in screen_lower and "select" in screen_lower) or (
                "my game" in screen_lower or "ai game" in screen_lower
            ):
                # Game selection - if we just tried this and got back here, try different letter
                if "menu_selection_attempts" not in bot.__dict__:
                    bot.menu_selection_attempts = 0

                bot.menu_selection_attempts += 1

                # Try B (AI Game) first if available, then A
                game_options = _extract_game_options(screen)
                # Filter out quit/menu options
                game_options_only = [
                    (letter, desc)
                    for letter, desc in game_options
                    if letter not in ["Q", "X", "!"]
                    and "quit" not in desc.lower()
                    and "back" not in desc.lower()
                ]

                if bot.menu_selection_attempts == 1:
                    # First attempt - use normal selection (single key, no \r)
                    game_letter = _select_trade_wars_game(screen)
                    print(
                        f"    → menu_selection game (attempt {bot.menu_selection_attempts}): "
                        f"Sending {game_letter} (single key)"
                    )
                    await bot.session.send(game_letter)  # Single key - NO \r
                    bot.last_game_letter = game_letter
                elif (
                    bot.menu_selection_attempts == 2
                    and len(game_options_only) > 1
                ):
                    # Second attempt - try the other game
                    other_letter = (
                        game_options_only[1][0]
                        if game_options_only[0][0] == bot.last_game_letter
                        else game_options_only[0][0]
                    )
                    print(
                        f"    → menu_selection game (attempt {bot.menu_selection_attempts}): "
                        f"Trying alternate: {other_letter} (single key)"
                    )
                    await bot.session.send(other_letter)  # Single key - NO \r
                else:
                    # Too many attempts - quit
                    print("    → menu_selection: Too many game selection attempts, quitting")
                    bot.menu_selection_attempts = 0
                    await bot.session.send("Q")

                await asyncio.sleep(0.5)
            else:
                # Unknown menu - quit
                print("    → menu_selection: Unknown menu, sending Q")
                await bot.session.send("Q")
                await asyncio.sleep(0.5)

        elif "command" in prompt_id or "sector_command" in prompt_id:
            # Reached game - command prompt
            print("    ✓ Reached game sector command prompt")
            break

        else:
            # Unknown prompt - just press space/enter
            print(f"    ⚠️  Unknown prompt, sending space")
            await bot.session.send(" ")
            await asyncio.sleep(0.3)

    # Parse initial state
    from .parsing import _parse_sector_from_screen, _parse_credits_from_screen
    bot.current_sector = _parse_sector_from_screen(bot, screen)
    bot.current_credits = _parse_credits_from_screen(bot, screen)
    print(
        f"\n✓ Login complete - Sector {bot.current_sector}, "
        f"Credits: {bot.current_credits:,}"
    )


async def test_login(bot):
    """Test login sequence only.

    Args:
        bot: TradingBot instance

    Returns:
        True if login succeeded, False otherwise
    """
    print("\n" + "=" * 80)
    print("TEST LOGIN - No trading")
    print("=" * 80)

    try:
        from .connection import connect
        await connect(bot)
        await login_sequence(bot)
        print("\n✓ Login test PASSED")
        return True
    except Exception as e:
        print(f"\n✗ Login test FAILED: {e}")
        return False
    finally:
        if bot.session_id:
            await bot.session_manager.close_session(bot.session_id)
