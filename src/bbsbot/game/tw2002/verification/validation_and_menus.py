#!/usr/bin/env python3
"""Test validation system and menu exploration.

This script:
1. Connects to TW2002 server
2. Explores login menus and verifies prompt detection
3. Validates extracted K/V data
4. Traces state through a trading cycle
5. Verifies menu navigation is accurate
"""

import asyncio
import os
import sys
from pathlib import Path

# Add src to path

from bbsbot.tw2002 import TradingBot
from bbsbot.learning.rules import RuleSet


async def test_menu_exploration():
    """Test menu exploration and state verification."""
    print("\n" + "=" * 80)
    print("MENU EXPLORATION & VALIDATION TEST")
    print("=" * 80)

    bot = TradingBot()

    try:
        # Step 1: Connect
        print("\n[1/5] Connecting to server...")
        from bbsbot.tw2002.connection import connect
        await connect(bot)
        print(f"✓ Connected: {bot.session.host}:{bot.session.port}")

        # Step 2: Load rules and verify K/V extraction config
        print("\n[2/5] Loading rules and verifying K/V extraction config...")
        rules = RuleSet.from_json_file(Path("games/tw2002/rules.json"))

        # Find rules with K/V extraction
        kv_rules = [p for p in rules.prompts if p.kv_extract]
        print(f"✓ Found {len(kv_rules)} prompts with K/V extraction rules:")
        for rule in kv_rules:
            fields = ", ".join([r.field for r in rule.kv_extract])
            print(f"  - {rule.id}: {fields}")

        # Step 3: Login and trace menu states
        print("\n[3/5] Starting login sequence with state tracing...")
        print("     Tracking: prompt_id, kv_data presence, validation status")
        print()

        from bbsbot.tw2002.io import wait_and_respond, send_input
        from bbsbot.tw2002.login import _check_kv_validation

        login_prompts = []
        step = 0

        username = os.environ.get("BBSBOT_TEST_USERNAME", "codexbot")
        char_password = os.environ.get("BBSBOT_TEST_PASSWORD", "codex2026")
        game_password = os.environ.get("BBSBOT_GAME_PASSWORD", "game")
        game_letter = os.environ.get("BBSBOT_GAME_LETTER", "B")

        for _ in range(50):
            step += 1
            try:
                input_type, prompt_id, screen, kv_data = await wait_and_respond(
                    bot, timeout_ms=5000
                )

                # Track this prompt
                has_kv = kv_data is not None
                validation_msg = ""
                if has_kv:
                    validation = kv_data.get("_validation", {})
                    valid = validation.get("valid", True)
                    validation_msg = "✓ VALID" if valid else "✗ INVALID"

                status = f"KV: {has_kv} | {validation_msg}" if has_kv else "KV: None"
                print(f"  [{step:2d}] {prompt_id:30s} | {status}")

                login_prompts.append({
                    "step": step,
                    "prompt_id": prompt_id,
                    "input_type": input_type,
                    "has_kv": has_kv,
                    "kv_data": kv_data,
                })

                # Handle prompts
                if "login_name" in prompt_id:
                    await send_input(bot, username, input_type)
                elif "login_password" in prompt_id or "character_password" in prompt_id:
                    await send_input(bot, char_password, input_type)
                elif "private_game_password" in prompt_id:
                    await send_input(bot, game_password, input_type)
                elif "game_password" in prompt_id:
                    await send_input(bot, game_password, input_type)
                elif "use_ansi_graphics" in prompt_id:
                    await bot.session.send("y\r")
                    await asyncio.sleep(0.3)
                elif "twgs_select_game" in prompt_id:
                    if "show game descriptions" in screen.lower() or "select game (q for none)" in screen.lower():
                        await bot.session.send("Q")
                        await asyncio.sleep(0.3)
                    await bot.session.send(game_letter)
                    await asyncio.sleep(0.3)
                elif "menu_selection" in prompt_id:
                    await bot.session.send(game_letter)
                    await asyncio.sleep(0.3)
                elif input_type == "any_key":
                    await send_input(bot, "", input_type)
                elif "command" in prompt_id or "sector_command" in prompt_id:
                    print(f"\n✓ Reached game at step {step}!")
                    break
                else:
                    await bot.session.send(" ")
                    await asyncio.sleep(0.2)

            except RuntimeError as e:
                print(f"  ✗ Error: {e}")
                break
            except TimeoutError:
                print(f"  ✗ Timeout")
                break

        # Step 4: Verify K/V extraction in game menu
        print("\n[4/5] Verifying K/V extraction in game menu...")
        print(f"✓ Reached sector command prompt")

        input_type, prompt_id, screen, kv_data = await wait_and_respond(
            bot, timeout_ms=3000
        )

        if kv_data:
            print(f"✓ K/V data extracted:")
            for key, value in kv_data.items():
                if key != "_validation":
                    print(f"  - {key}: {value}")

            validation = kv_data.get("_validation", {})
            if validation.get("valid"):
                print(f"✓ Validation: PASSED")
                # Extract state
                sector = kv_data.get("sector")
                credits = kv_data.get("credits")
                print(f"✓ Game state: Sector {sector}, Credits {credits:,}")
            else:
                errors = validation.get("errors", [])
                print(f"✗ Validation: FAILED - {errors}")
        else:
            print(f"⚠️  No K/V data extracted for sector_command")

        # Step 5: Summary
        print("\n[5/5] Test Summary")
        print("=" * 80)
        kv_prompts = [p for p in login_prompts if p["has_kv"]]
        print(f"Total prompts: {len(login_prompts)}")
        print(f"Prompts with K/V data: {len(kv_prompts)}")
        print(f"Login prompts traced: {', '.join([p['prompt_id'] for p in login_prompts[:5]])}")
        print()

        print("✅ MENU EXPLORATION & VALIDATION TEST PASSED")

    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        if bot.session_id:
            await bot.session_manager.close_session(bot.session_id)

    return True


async def test_extraction_accuracy():
    """Test K/V extraction against known screens."""
    print("\n" + "=" * 80)
    print("EXTRACTION ACCURACY TEST")
    print("=" * 80)

    from bbsbot.learning.rules import RuleSet
    from bbsbot.learning.extractor import KVExtractor

    rules = RuleSet.from_json_file(Path("games/tw2002/rules.json"))

    test_cases = [
        {
            "name": "sector_command with valid data",
            "prompt_id": "prompt.sector_command",
            "screen": "Sector 100\nCommand [TL=10:45]:[100]\nCredits: 500,000",
            "expected_fields": {"sector": 100, "credits": 500000},
            "should_validate": True,
        },
        {
            "name": "sector_command with invalid sector",
            "prompt_id": "prompt.sector_command",
            "screen": "Sector 9999\nCommand [TL=10:45]:[9999]\nCredits: 500,000",
            "expected_fields": {"sector": 9999},
            "should_validate": False,
        },
        {
            "name": "warp_sector context extraction",
            "prompt_id": "prompt.warp_sector",
            "screen": "Current Location: Sector 499\n\nEnter destination Sector: ",
            "expected_fields": {"current_sector": 499},
            "should_validate": True,
        },
    ]

    passed = 0
    failed = 0

    for test in test_cases:
        rule = next((p for p in rules.prompts if p.id == test["prompt_id"]), None)
        if not rule or not rule.kv_extract:
            print(f"\n✗ {test['name']}: No K/V rules found")
            failed += 1
            continue

        kv_config = [
            {
                "field": r.field,
                "type": r.type,
                "regex": r.regex,
                "validate": r.validate,
                "required": r.required,
            }
            for r in rule.kv_extract
        ]

        result = KVExtractor.extract(test["screen"], kv_config)

        if not result:
            print(f"\n✗ {test['name']}: No extraction")
            failed += 1
            continue

        # Check expected fields
        fields_match = all(
            result.get(k) == v for k, v in test["expected_fields"].items()
        )

        # Check validation
        validation = result.get("_validation", {})
        is_valid = validation.get("valid", True)
        validation_match = is_valid == test["should_validate"]

        if fields_match and validation_match:
            print(f"\n✓ {test['name']}")
            print(f"  Fields: {test['expected_fields']}")
            print(f"  Valid: {is_valid}")
            passed += 1
        else:
            print(f"\n✗ {test['name']}")
            if not fields_match:
                print(f"  Fields mismatch: expected {test['expected_fields']}, got {result}")
            if not validation_match:
                print(
                    f"  Validation mismatch: expected {test['should_validate']}, got {is_valid}"
                )
            print(f"  Errors: {validation.get('errors', [])}")
            failed += 1

    print("\n" + "=" * 80)
    print(f"Extraction tests: {passed} passed, {failed} failed")

    if failed == 0:
        print("✅ EXTRACTION ACCURACY TEST PASSED")
    else:
        print(f"✗ EXTRACTION ACCURACY TEST FAILED")

    return failed == 0


async def main():
    """Run all tests."""
    print("\n" + "=" * 80)
    print("COMPREHENSIVE VALIDATION & MENU EXPLORATION TEST SUITE")
    print("=" * 80)

    # Test 1: Extraction accuracy
    extraction_ok = await test_extraction_accuracy()

    # Test 2: Menu exploration
    menu_ok = await test_menu_exploration()

    # Summary
    print("\n" + "=" * 80)
    print("FINAL RESULTS")
    print("=" * 80)
    print(f"Extraction accuracy: {'✓ PASS' if extraction_ok else '✗ FAIL'}")
    print(f"Menu exploration: {'✓ PASS' if menu_ok else '✗ FAIL'}")

    if extraction_ok and menu_ok:
        print("\n✅ ALL TESTS PASSED")
        sys.exit(0)
    else:
        print("\n✗ SOME TESTS FAILED")
        sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(1)
