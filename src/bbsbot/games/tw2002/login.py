"""Login sequence handling for TW2002.

IMPORTANT: See games/tw2002/TWGS_LOGIN_FLOW.md for the complete TWGS flow documentation.

The TWGS login flow is complex:
1. May or may not show login prompt depending on connection type
2. Game selection shows description first, then enters "Show Game Descriptions" mode
3. Must send Q to exit description mode before game actually loads
4. Private games require password
5. Multiple pause screens during game loading
"""

import asyncio

from bbsbot.games.tw2002.io import wait_and_respond, send_input, send_masked_password
from bbsbot.games.tw2002.parsing import _extract_game_options, _select_trade_wars_game
from bbsbot.games.tw2002.logging_utils import logger


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


def _is_description_mode(screen: str) -> bool:
    """Check if we're stuck in 'Show Game Descriptions' mode.

    This happens after selecting a game - TWGS shows description then
    enters a mode where you select MORE games to view descriptions.
    Must send Q to exit this mode.
    """
    screen_lower = screen.lower()
    return (
        "show game descriptions" in screen_lower
        or "select game (q for none)" in screen_lower
        or ("select game" in screen_lower and "q for none" in screen_lower)
    )


def _get_actual_prompt(screen: str) -> str:
    """Analyze the LAST LINES of the screen to determine the actual prompt.

    This is critical because the prompt detector may match stale text anywhere
    in the screen buffer (like old "[Pause]" text from ANSI graphics).
    The actual prompt is always at or near the bottom of the screen.

    Returns a prompt identifier based on last-line content, or empty string if unknown.
    """
    # Get the last 5 non-empty lines
    lines = [l.strip() for l in screen.split('\n') if l.strip()]
    if not lines:
        return ""

    # Join last 5 lines for analysis
    last_lines = '\n'.join(lines[-5:]).lower()
    last_line = lines[-1].lower() if lines else ""

    # Check prompts in priority order (most specific first)

    # Corporate listings - NOT a command prompt, must exit this first!
    if "corporate" in last_lines and "listing" in last_lines:
        return "corporate_listings"
    if "which listing" in last_line:
        return "corporate_listings"

    # Command prompt - we've reached the game!
    if "command" in last_line and "?" in last_line:
        return "command_prompt"

    # Planet command prompt - also indicates we're in the game
    if "planet command" in last_line:
        return "command_prompt"

    # TW2002 pre-game menu
    if "enter your choice:" in last_line or "enter your choice" in last_line:
        return "tw_game_menu"

    # Alias prompt (when chosen name is taken) - check BEFORE name_selection
    # This appears when the BBS name is already in use
    if "alias" in last_line and ("want to use" in last_line or "do you want" in last_line):
        return "alias_prompt"

    # Name/alias confirmation prompt - check EARLY.
    # Guard against stale scrollback: after we've answered, TWGS often echoes "Yes"/"No"
    # on the same line, which should NOT be treated as an active prompt.
    for line in lines[-3:]:
        ll = line.lower()
        if "is what you want?" in ll and "yes" not in ll and "no" not in ll:
            return "name_confirm"

    # Ship/planet naming prompts (new character creation).
    # IMPORTANT: these screens can retain stale "(N)ew Name or (B)BS Name" text
    # at the bottom of the buffer. Prefer the explicit ship/planet prompt text.
    if "what do you want to name your ship" in last_lines:
        return "ship_name_prompt"
    if "what do you want to name your home planet" in last_lines:
        return "planet_name_prompt"

    # Name selection (new character) - only if it's the actual prompt on last line
    # Check last_line first to avoid matching stale buffer content
    if "(n)ew name or (b)bs name" in last_line:
        return "name_selection"
    # Also check last_lines but only if alias prompt wasn't detected
    if "(n)ew name or (b)bs name" in last_lines and "alias" not in last_line:
        return "name_selection"

    # Private game password prompt - MUST check before generic password prompt
    # Variations: "private game", "password is required to enter this game"
    if ("private game" in last_lines or "required to enter this game" in last_lines) and (
        "password" in last_line
    ):
        return "private_game_password"

    # Password prompt (check last line only to avoid matching completed passwords)
    if last_line.startswith("password?"):
        return "password_prompt"

    # New character creation prompt
    if "start a new character" in last_lines and "(type y or n)" in last_lines:
        # Only if not already answered (check for "Yes" on the line)
        for line in lines[-3:]:
            if "(type y or n)" in line.lower() and "yes" not in line.lower():
                return "new_character_prompt"

    # Show today's log?
    if "show today's log" in last_line and "(y/n)" in last_line:
        return "show_log_prompt"

    # Alias input prompt (when BBS name is taken)
    # e.g. "What Alias do you want to use?"
    # IMPORTANT: check LAST LINE only; this phrase can linger in the scrollback buffer.
    if "what alias do you want to use" in last_line:
        return "alias_input"

    # Generic Y/N prompt
    if "(y/n)" in last_line or "(type y or n)" in last_line:
        return "yes_no_prompt"

    # What is your name?
    if "what is your name" in last_line:
        return "what_is_your_name"

    # Use ANSI graphics?
    if "use ansi graphics" in last_line:
        return "use_ansi"

    # [ANY KEY] style prompts
    if "[any key]" in last_line:
        return "any_key"

    # [Pause] - but ONLY if it's on the LAST LINE (not stale buffer)
    if "[pause]" in last_line:
        return "pause"

    # Game selection menu
    if "selection (? for menu):" in last_line:
        return "menu_selection"

    # Description mode
    if "select game (q for none)" in last_line:
        return "description_mode"

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
    # Track disambiguation for generic "Password?" prompts.
    sent_username: bool = False
    last_password_kind: str | None = None  # "game" | "character"
    ambiguous_password_attempts: int = 0

    # PHASE 1: Navigate to game selection (menu_selection prompt)
    print("\nNavigating to game selection menu...")
    for iteration in range(10):
        step += 1
        try:
            # First connection may take up to 90 seconds under heavy server load (90 bots)
            # Use longer timeout on first attempt, shorter on subsequent attempts
            timeout = 90000 if iteration == 0 else 20000
            input_type, prompt_id, screen, kv_data = await wait_and_respond(
                bot, timeout_ms=timeout
            )
        except TimeoutError as e:
            # Print screen on timeout for debugging
            print(f"⚠ Timeout in Phase 1, checking screen content...")
            try:
                timeout_screen = bot.session.snapshot().get("screen", "")
                lines = [l.strip() for l in timeout_screen.split('\n') if l.strip()]
                print(f"      [TIMEOUT DEBUG] Screen ({len(lines)} lines), last 10:")
                for line in lines[-10:]:
                    print(f"        | {line[:75]}")

                # Check if we're actually at game selection screen (robust content-based detection)
                screen_lower = timeout_screen.lower()
                if ("selection" in screen_lower and "for menu" in screen_lower) or \
                   ("<a>" in screen_lower and "<b>" in screen_lower and "game" in screen_lower):
                    print(f"      ✓ Detected game selection screen by content!")
                    # Set variables as if prompt was detected
                    screen = timeout_screen
                    prompt_id = "menu_selection"  # Fake prompt ID for Phase 2 compatibility
                    input_type = "single_key"
                    kv_data = None
                    break  # Exit Phase 1 loop
            except Exception:
                pass
            raise
        except RuntimeError as e:
            print(f"✗ Navigation error: {e}")
            raise

        validation_msg = _check_kv_validation(kv_data, prompt_id)
        print(f"  [{step}] {prompt_id} ({input_type}) {validation_msg}")

        screen_lower = screen.lower()

        # Handle prompts until we reach menu_selection
        if "twgs_begin_adventure" in prompt_id:
            # Final prompt before entering game - just press Enter
            print(f"      → Begin adventure prompt, pressing Enter")
            await bot.session.send("\r")
            await asyncio.sleep(0.3)

        elif "twgs_ship_selection" in prompt_id:
            # Ship/sector selection during character creation - requires Enter
            print(f"      → Ship/sector selection prompt, choosing 1")
            await send_input(bot, "1", input_type)

        elif "twgs_gender" in prompt_id:
            # Gender prompt during character creation
            # Note: TWGS needs Enter even though it seems like single_key
            print(f"      → Gender prompt, sending M+Enter")
            await bot.session.send("M\r")
            await asyncio.sleep(0.3)

        elif "twgs_real_name" in prompt_id:
            # Real name prompt during character creation
            # Some stacks show: "Please enter your name (ENTER for none):"
            # This is NOT the login-name prompt; safest behavior is to accept blank.
            if "enter for none" in screen_lower:
                print("      → Real name prompt (ENTER for none), sending Enter")
                await bot.session.send("\r")
                await asyncio.sleep(0.3)
            else:
                print(f"      → Real name prompt, sending: {username}")
                await send_input(bot, username, input_type)

        elif "what_is_your_name" in prompt_id:
            # Some systems ask this prior to the normal login_name prompt.
            print(f"      → What is your name? entering: {username}")
            await send_input(bot, username, input_type, wait_after=0.5)
            sent_username = True

        elif "character_password" in prompt_id:
            # Character password for new character
            print(f"      → Character password prompt, sending password")
            await send_masked_password(bot, character_password)
            last_password_kind = "character"

        elif "create_character" in prompt_id:
            # Character creation confirmation - answer Y
            # Note: Even single_key prompts may need Enter on some systems
            print(f"      → Create character confirmation, answering Y")
            await bot.session.send("Y\r")
            await asyncio.sleep(0.5)

        elif "new_player_name" in prompt_id:
            # Creating a new character - send the desired character name
            print(f"      → New player name prompt, entering: {username}")
            await send_input(bot, username, input_type)
            sent_username = True

        elif "login_name" in prompt_id:
            # Send the desired username. Sending literal "new" here can accidentally log
            # in as user "new" (and then fail at Password? with invalid_password).
            #
            # If the system has a special "NEW" workflow, it should be triggered by
            # an explicit on-screen instruction, not by default heuristics.
            print(f"      → Sending username")
            await send_input(bot, username, input_type, wait_after=0.5)
            sent_username = True
            # Give server extra time to process login and prepare next prompt
            await asyncio.sleep(0.3)

        elif "menu_selection" in prompt_id:
            print(f"      ✓ Reached game selection menu!")
            break

        elif "sector_command" in prompt_id:
            # Already in game! Existing character logged in directly.
            print(f"      ✓ Already in game! (existing character)")
            # Skip to phase 3 end - parse state and return
            from bbsbot.games.tw2002.parsing import _parse_sector_from_screen, _parse_credits_from_screen
            bot.current_sector = _parse_sector_from_screen(bot, screen)
            bot.current_credits = _parse_credits_from_screen(bot, screen)
            print(
                f"\n✓ Login complete (existing character) - Sector {bot.current_sector}, "
                f"Credits: {bot.current_credits:,}"
            )
            return  # Early return - already logged in

        elif input_type == "any_key":
            print("      → Pressing space to continue")
            await send_input(bot, "", input_type)

        else:
            # Content-based fallback detection when prompt_id doesn't match
            handled = False

            if "what is your name" in screen_lower:
                print(f"      → [Content] Detected name prompt, entering: {username}")
                await bot.session.send(f"{username}\r")
                await asyncio.sleep(0.3)
                handled = True
            elif ("selection" in screen_lower and "for menu" in screen_lower):
                print(f"      ✓ [Content] Detected game selection menu!")
                break
            elif "command" in screen_lower and ("?" in screen_lower or "tl=" in screen_lower):
                print(f"      ✓ [Content] Detected game command prompt - already in game!")
                return

            if not handled:
                print(f"      ⚠️  Unexpected prompt (prompt_id={prompt_id}), pressing space")
                await bot.session.send(" ")
            await asyncio.sleep(0.2)

    # PHASE 2: Send game selection
    print("\nSending game selection...")
    # Use configured game_letter if available, otherwise auto-detect
    config_letter = getattr(bot.config.connection, 'game_letter', None) if hasattr(bot, 'config') else None
    game_letter = config_letter if config_letter else "B"  # Default to B if not configured
    original_threshold = bot.loop_detection.threshold  # Save before any modifications

    # Check screen content for game selection menu (more robust than prompt detection)
    screen_lower = screen.lower()
    if "selection" in screen_lower and ("for menu" in screen_lower or "<q>" in screen_lower):
        options = _extract_game_options(screen)
        print(f"  Available games: {options}")
        # Only auto-detect if no game_letter configured
        if not config_letter:
            game_letter = _select_trade_wars_game(screen)
        print(f"  → Sending {game_letter}" + (f" (configured)" if config_letter else " (auto-detected)"))
        await bot.session.send(game_letter)
        # Save game letter to bot for data directory scoping
        bot.last_game_letter = game_letter
    elif "menu_selection" in prompt_id:
        # Fallback to prompt detection if screen matching fails
        options = _extract_game_options(screen)
        print(f"  Available games: {options}")
        if not config_letter:
            game_letter = _select_trade_wars_game(screen)
        print(f"  → Sending {game_letter}" + (f" (configured)" if config_letter else " (auto-detected)"))
        await bot.session.send(game_letter)
        bot.last_game_letter = game_letter
        # Reset state before Phase 3 to prevent loop detection false triggers
        bot.loop_detection.reset()
        bot.last_prompt_id = None
        # Increase threshold for game loading phase (intro screens may repeat pause prompt)
        bot.loop_detection.threshold = 15  # Increased for complex flows
        print(f"  ✓ Reset loop detection state")

    # PHASE 3: Wait for game to load and reach command prompt
    # IMPORTANT: See games/tw2002/TWGS_LOGIN_FLOW.md for flow documentation
    print("\nWaiting for game to load...")
    description_mode_exits = 0  # Track how many times we exit description mode
    menu_reentries = 0  # Track re-entering game selection (indicates wrong password)
    capacity_retries = 0  # Track "Failed to start game session" (server capacity / node allocation)

    # Initialize kv_data for Phase 3 (may have been set to None in Phase 1 fallback)
    kv_data = {}

    # Increased loop limit to handle slow game loading (can take 10+ seconds after pressing T)
    reached_game = False
    for step_in_phase3 in range(200):
        step += 1
        try:
            # Game loading takes 11+ seconds, need longer timeout
            # Increased to 90s to handle slow server response when 90 bots logging in
            # With 12s spawn intervals, ~5-7 concurrent logins max, server still slow
            # During character creation, some prompts legitimately repeat.
            ignore_loop = {
                "prompt.ship_name",
                "prompt.planet_name",
                "prompt.menu_selection",
                "prompt.corporate_listings",
                # Password prompts can repeat (set + verify, or retries on invalid).
                "prompt.character_password",
                "prompt.game_password",
                "prompt.private_game_password",
            }
            input_type, prompt_id, screen, phase3_kv_data = await wait_and_respond(
                bot, timeout_ms=90000, ignore_loop_for=ignore_loop
            )
            # Always update kv_data from Phase 3 responses
            if phase3_kv_data:
                kv_data = phase3_kv_data
        except RuntimeError as e:
            print(f"✗ Game load error: {e}")
            raise
        except TimeoutError as e:
            # Print screen on timeout for debugging
            try:
                timeout_screen = bot.session.snapshot().get("screen", "")
                lines = [l.strip() for l in timeout_screen.split('\n') if l.strip()]
                print(f"      [TIMEOUT DEBUG] Screen ({len(lines)} lines), last 10:")
                for line in lines[-10:]:
                    print(f"        | {line[:75]}")
            except Exception:
                pass
            raise

        validation_msg = _check_kv_validation(kv_data, prompt_id)

        # CRITICAL: Use last-line analysis to determine ACTUAL prompt
        # The pattern matcher may match stale text (like old [Pause]) anywhere in buffer
        actual_prompt = _get_actual_prompt(screen)

        # If the prompt detector matched a very specific prompt, trust it over
        # last-line heuristics (the screen buffer frequently contains stale text).
        #
        # Exception: ship/planet naming screens have an immediate Y/N confirmation
        # ("X is what you want?") that must be answered before we re-send the name.
        if prompt_id == "prompt.ship_name":
            # The prompt detector can match stale "Use (N)ew Name or (B)BS Name" buffers.
            # Only force "ship_name_prompt" when the heuristic is clearly wrong.
            if actual_prompt in ("name_selection", "alias_prompt", "alias_input", ""):
                actual_prompt = "ship_name_prompt"
        elif prompt_id == "prompt.planet_name":
            if actual_prompt in ("name_selection", "alias_prompt", "alias_input", ""):
                actual_prompt = "planet_name_prompt"

        print(f"  [{step}] pattern:{prompt_id} actual:{actual_prompt} ({input_type}) {validation_msg}", flush=True)

        # Debug: Show screen content periodically (more frequently now)
        if step_in_phase3 % 5 == 0 or step_in_phase3 < 10 or step_in_phase3 >= 28:
            lines = [l.strip() for l in screen.split('\n') if l.strip()]
            print(f"      [DEBUG] Screen ({len(lines)} lines), last 8:")
            for line in lines[-8:]:
                print(f"        | {line[:75]}")

        # Handle prompts based on ACTUAL PROMPT (last-line analysis), not pattern ID
        # This prevents confusion from stale buffer content

        screen_lower = screen.lower()

        # Server capacity/backpressure case:
        # Some servers print "Failed to start game session [NNN]..." when no nodes are available.
        # This is not an auth error; hammering the menu just makes it worse. Back off and retry.
        if "failed to start game session" in screen_lower:
            capacity_retries += 1
            # Quick ramp to a stable retry cadence; keep it bounded.
            sleep_s = min(30.0, 1.5 + 2.5 * capacity_retries)
            logger.info(
                "Game session allocation failed (capacity). Backing off %.1fs (retry #%d)",
                sleep_s,
                capacity_retries,
            )
            await asyncio.sleep(sleep_s)
            try:
                # Re-try selecting the configured game letter.
                await bot.session.send(game_letter)
            except Exception:
                pass
            continue

        if actual_prompt == "command_prompt" or actual_prompt == "planet_prompt":
            # Reached game! (either sector command or planet command for new chars)
            print(f"      ✓ Reached game!", flush=True)
            reached_game = True
            break

        elif actual_prompt == "corporate_listings":
            # Corporate listings menu during login - exit with Q
            print(f"      → Corporate listings detected, sending Q to exit...")
            await bot.session.send("Q")
            await asyncio.sleep(0.5)

        elif actual_prompt == "description_mode" or _is_description_mode(screen):
            description_mode_exits += 1
            if description_mode_exits > 3:
                print(f"      ✗ Stuck in description mode after {description_mode_exits} attempts")
                raise RuntimeError("Stuck in game description mode - check game selection")
            print(f"      → Exiting description mode (attempt {description_mode_exits})")
            await bot.session.send("Q")
            await asyncio.sleep(0.3)

        elif actual_prompt == "tw_game_menu":
            # End-state behavior: always submit "T" with Enter.
            #
            # Some TWGS stacks won't echo the typed character reliably, and
            # waiting for the echo can lead to never actually entering the game.
            print("      → At game menu, sending T+Enter to start Trade Wars")
            await bot.session.send("T\r")
            # Let the server start loading; prompt waiter will handle the rest.
            await asyncio.sleep(0.5)

        elif actual_prompt == "name_selection":
            print("      → Name selection prompt, choosing (B)BS Name")
            await bot.session.send("B")
            await asyncio.sleep(0.3)

        elif actual_prompt == "alias_prompt":
            # Name was taken, need to provide a unique alias
            import uuid
            short_id = uuid.uuid4().hex[:6]
            alias = f"Cdx{short_id}"
            print(f"      → Alias prompt (name taken), entering: {alias}")
            await send_input(bot, alias, "multi_key")

        elif actual_prompt == "alias_input":
            # Some servers skip the explanatory alias prompt and go straight to input.
            import uuid
            short_id = uuid.uuid4().hex[:6]
            alias = f"Cdx{short_id}"
            print(f"      → Alias input prompt, entering: {alias}")
            await send_input(bot, alias, "multi_key")

        elif actual_prompt == "ship_name_prompt":
            # Use simple ship name without special characters
            ship_name = "Bot Ship"
            print(f"      → Ship naming prompt, entering: {ship_name}")
            await send_input(bot, ship_name, "multi_key")

        elif actual_prompt == "planet_name_prompt":
            planet_name = f"{username}'s World"
            print(f"      → Planet naming prompt, entering: {planet_name}")
            await send_input(bot, planet_name, "multi_key")

        elif actual_prompt == "name_confirm":
            print(f"      → Confirming name/alias: Y")
            await bot.session.send("Y")
            await asyncio.sleep(0.3)

        elif actual_prompt == "password_prompt":
            # Generic Password? prompt can mean either:
            # - game password (private game access) OR
            # - character password (new/existing character)
            #
            # Prefer explicit prompt_id classification when available.
            kind: str | None = None
            if prompt_id and ("game_password" in prompt_id or "private_game_password" in prompt_id):
                kind = "game"
            elif prompt_id and "character_password" in prompt_id:
                kind = "character"
            else:
                # Heuristics for ambiguous servers that only emit "Password?".
                # Prefer explicit on-screen banners.
                if "required to enter this game" in screen_lower or "private game" in screen_lower:
                    kind = "game"
                elif "repeat password to verify" in screen_lower or "please enter a password for this game account" in screen_lower:
                    kind = "character"
                elif not sent_username:
                    kind = "game"
                else:
                    kind = "character"

            # If this is a verify prompt, it's always the character/account password.
            if "repeat password to verify" in screen_lower:
                kind = "character"

            # If the screen says "invalid password" and the prompt is ambiguous,
            # flip once to the other password to avoid getting stuck due to misclassification.
            if "invalid password" in screen_lower:
                ambiguous_password_attempts += 1
                if ambiguous_password_attempts <= 2 and last_password_kind in ("game", "character"):
                    kind = "character" if last_password_kind == "game" else "game"

            if kind == "game":
                print("      → Password prompt, sending game password")
                await send_masked_password(bot, game_password)
                last_password_kind = "game"
            else:
                print("      → Password prompt, sending character password")
                # Some TWGS variants (or high-latency telnet bursts) can render both:
                # - "Please enter a password... Password?"
                # - "Repeat password to verify. Password?"
                # in one buffer. If we only submit once, TW treats the *repeat* as blank
                # (second Enter with no text) and we get "Passwords didn't match".
                if "repeat password to verify" in screen_lower:
                    await send_masked_password(bot, character_password)
                    await asyncio.sleep(0.2)
                    await send_masked_password(bot, character_password)
                else:
                    await send_masked_password(bot, character_password)
                last_password_kind = "character"
                # If the server explicitly complains, immediately retry with the double-submit.
                if "passwords didn't match" in screen_lower:
                    await send_masked_password(bot, character_password)
                    await asyncio.sleep(0.2)
                    await send_masked_password(bot, character_password)

        elif actual_prompt == "private_game_password":
            print(f"      → Private game password prompt, sending game password")
            await send_masked_password(bot, game_password)
            last_password_kind = "game"

        elif actual_prompt == "new_character_prompt":
            print("      → New character prompt, answering Y to create character")
            await bot.session.send("Y\r")
            await asyncio.sleep(2.0)  # Wait for server to process character creation

        elif actual_prompt == "show_log_prompt":
            print("      → Answering N to 'Show today's log?'")
            await bot.session.send("N")
            await asyncio.sleep(0.3)

        elif actual_prompt == "yes_no_prompt":
            print(f"      → Generic Y/N prompt, answering N")
            await bot.session.send("N")
            await asyncio.sleep(0.3)

        elif actual_prompt == "what_is_your_name":
            print(f"      → Entering character name: {username}")
            await send_input(bot, username, "multi_key")
            sent_username = True

        elif actual_prompt == "use_ansi":
            print("      → Selecting ANSI graphics: Y")
            await bot.session.send("Y")
            await asyncio.sleep(0.3)

        elif actual_prompt == "menu_selection":
            menu_reentries += 1
            if menu_reentries > 20:
                raise RuntimeError(
                    f"Returned to game menu {menu_reentries} times - "
                    f"likely wrong game password for game {game_letter}"
                )
            print(f"      → At menu, selecting game {game_letter} (re-entry #{menu_reentries})")
            await bot.session.send(game_letter)
            # Increase delay between retries to avoid overwhelming server
            await asyncio.sleep(0.5 if menu_reentries <= 3 else 1.0)

        elif actual_prompt in ("any_key", "pause"):
            print("      → Pressing space to continue")
            await bot.session.send(" ")
            await asyncio.sleep(0.3)

        # Fallback: if actual_prompt is empty, use pattern-based detection
        elif "twgs_begin_adventure" in prompt_id:
            # This prompt says "Press ENTER to begin" - needs Enter, not space
            print(f"      → Begin adventure prompt, pressing Enter")
            await bot.session.send("\r")
            await asyncio.sleep(0.3)

        elif "what_is_your_name" in prompt_id:
            print(f"      → Entering character name (pattern): {username}")
            await send_input(bot, username, "multi_key")
            sent_username = True

        elif "private_game_password" in prompt_id:
            print(f"      → Sending game password (pattern)")
            await send_masked_password(bot, game_password)
            last_password_kind = "game"

        elif "game_password" in prompt_id:
            # Some servers emit a plain `Password?` without the "private game" banner.
            # Treat this as a game password request, not a character password.
            print(f"      → Game password prompt (pattern), sending game password")
            await send_masked_password(bot, game_password)
            last_password_kind = "game"

        elif "corporate_listings" in prompt_id:
            # Corporate listings menu - send Q to quit
            print("      → Corporate Listings menu, sending Q to exit")
            await bot.session.send("Q")
            await asyncio.sleep(0.3)

        elif input_type == "any_key":
            print("      → Pressing space (any_key input_type)")
            await send_input(bot, "", input_type)

        else:
            print(f"      → Unknown state, pressing space")
            await bot.session.send(" ")
            await asyncio.sleep(0.2)

    if not reached_game:
        raise RuntimeError("Login did not reach game command prompt (stuck in pre-game menus)")

    # Restore threshold after game loading phase
    bot.loop_detection.threshold = original_threshold
    print(f"  [DEBUG] Threshold restored", flush=True)

    # Debug: Show what we have after exiting login loop
    print(f"  [DEBUG] After login loop - kv_data type: {type(kv_data)}, has credits: {'credits' in kv_data if kv_data else False}", flush=True)
    if kv_data and 'credits' in kv_data:
        print(f"  [DEBUG] kv_data HAS CREDITS: {kv_data.get('credits')}", flush=True)

    # Parse initial state
    print(f"  [DEBUG] Importing parsing...", flush=True)
    from bbsbot.games.tw2002.parsing import _parse_sector_from_screen, _parse_credits_from_screen
    print(f"  [DEBUG] Parsing sector...", flush=True)
    bot.current_sector = _parse_sector_from_screen(bot, screen)
    print(f"  [DEBUG] Parsing credits...", flush=True)
    bot.current_credits = _parse_credits_from_screen(bot, screen)

    # Note: Bots login on planet command prompts where credits aren't visible.
    # The orient() function (called on first trading turn) will establish accurate state
    # including credits by sending D command from a sector context. Accept credits=0 here.

    print(
        f"\n✓ Login complete - Sector {bot.current_sector}, "
        f"Credits: {bot.current_credits:,}",
        flush=True
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
        from bbsbot.games.tw2002.connection import connect
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
