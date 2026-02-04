"""Login sequence handling for TW2002."""

import asyncio

from .io import wait_and_respond, send_input
from .parsing import _extract_game_options, _select_trade_wars_game
from .logging_utils import logger


def _check_kv_validation(kv_data: dict | None, prompt_id: str) -> str:
    """Check if extracted K/V data passed validation.

    Returns validation error message if invalid, empty string if valid.
    """
    if not kv_data:
        return ""

    validation = kv_data.get("_validation", {})
    if not validation.get("valid", True):
        errors = validation.get("errors", ["Unknown error"])
        return f"[VALIDATION] {errors[0]}"

    return ""


async def login_sequence(
    bot,
    game_password: str = "game",
    character_password: str = "test",
    username: str = "testbot",
):
    """Complete login sequence from telnet login to game entry.

    Uses the working diagnostic structure: separate navigation from actions
    to avoid loop detection and timing issues with wait_and_respond().

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

    # PHASE 1: Navigate to game selection (menu_selection prompt)
    print("\nNavigating to game selection menu...")
    for _ in range(10):
        step += 1
        try:
            input_type, prompt_id, screen, kv_data = await wait_and_respond(
                bot, timeout_ms=5000
            )
        except RuntimeError as e:
            print(f"✗ Navigation error: {e}")
            raise

        validation_msg = _check_kv_validation(kv_data, prompt_id)
        print(f"  [{step}] {prompt_id} ({input_type}) {validation_msg}")

        screen_lower = screen.lower()

        # Handle prompts until we reach menu_selection
        if "login_name" in prompt_id:
            print(f"      → Sending username")
            await send_input(bot, username, input_type)

        elif "menu_selection" in prompt_id:
            print(f"      ✓ Reached game selection menu!")
            break

        elif input_type == "any_key":
            print("      → Pressing space to continue")
            await send_input(bot, "", input_type)

        else:
            print(f"      ⚠️  Unexpected prompt, pressing space")
            await bot.session.send(" ")
            await asyncio.sleep(0.2)

    # PHASE 2: Send game selection
    print("\nSending game selection...")
    if "menu_selection" in prompt_id:
        game_letter = _select_trade_wars_game(screen)
        print(f"  → Sending {game_letter} (AI Apocalypse)")
        await bot.session.send(game_letter)
        # Reset state before Phase 3 to prevent loop detection false triggers
        bot.loop_detection.clear()
        bot.last_prompt_id = None
        # Increase threshold for game loading phase (intro screens may repeat pause prompt)
        original_threshold = bot.stuck_threshold
        bot.stuck_threshold = 10
        print(f"  ✓ Reset loop detection state")

    # PHASE 3: Wait for game to load and reach command prompt
    print("\nWaiting for game to load...")
    for step_in_phase3 in range(50):
        step += 1
        try:
            # Game loading takes 11+ seconds, need longer timeout
            input_type, prompt_id, screen, kv_data = await wait_and_respond(
                bot, timeout_ms=20000
            )
        except RuntimeError as e:
            print(f"✗ Game load error: {e}")
            raise

        validation_msg = _check_kv_validation(kv_data, prompt_id)
        print(f"  [{step}] {prompt_id} ({input_type}) {validation_msg}")

        screen_lower = screen.lower()

        # Handle prompts while loading
        if "private_game_password" in prompt_id:
            print(f"      → Sending game password")
            await send_input(bot, game_password, input_type)

        elif "game_password" in prompt_id:
            print(f"      → Sending character password")
            await send_input(bot, character_password, input_type)

        elif "use_ansi_graphics" in prompt_id:
            print("      → Selecting ANSI graphics")
            await bot.session.send("y")
            await asyncio.sleep(0.3)

        elif input_type == "any_key":
            print("      → Pressing space (loading)")
            await send_input(bot, "", input_type)

        elif "command" in prompt_id or "sector_command" in prompt_id:
            print(f"      ✓ Reached game!")
            break

        else:
            print(f"      → Pressing space (unknown prompt)")
            await bot.session.send(" ")
            await asyncio.sleep(0.2)

    # Restore threshold after game loading phase
    bot.stuck_threshold = original_threshold

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
