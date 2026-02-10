#!/usr/bin/env python3
"""Detailed state verification - track extraction and validation in real menus."""

import asyncio
import sys
from pathlib import Path

from bbsbot.games.tw2002 import TradingBot
from bbsbot.games.tw2002.io import wait_and_respond
from bbsbot.learning.extractor import KVExtractor
from bbsbot.learning.rules import RuleSet


async def test_sector_command_detection():
    """Test specifically for sector_command prompt and K/V extraction."""
    print("\n" + "=" * 80)
    print("SECTOR COMMAND DETECTION & K/V EXTRACTION TEST")
    print("=" * 80)

    bot = TradingBot()

    try:
        # Connect
        from bbsbot.games.tw2002.connection import connect

        await connect(bot)

        # Load rules
        rules = RuleSet.from_json_file(Path("games/tw2002/rules.json"))
        sector_rule = next(p for p in rules.prompts if p.id == "prompt.sector_command")

        print("\n✓ Sector command rule loaded:")
        print(f"  Prompt ID: {sector_rule.id}")
        print(f"  Pattern: {sector_rule.match.pattern}")
        print(f"  K/V rules: {len(sector_rule.kv_extract)}")
        for rule in sector_rule.kv_extract:
            print(f"    - {rule.field}: regex='{rule.regex}', validate={rule.validate}")

        # Fast login - use existing login function but trace deeply
        from bbsbot.games.tw2002.login import login_sequence

        # Run login with higher visibility
        print("\n" + "-" * 80)
        print("Starting login... waiting for sector_command prompt")
        print("-" * 80)

        await login_sequence(bot)

        # Now we should be in the game
        print("\n✓ Login complete, now in game")

        # Get the sector command prompt and examine it closely
        print("\nCapturing sector_command prompt state...")

        input_type, prompt_id, screen, kv_data = await wait_and_respond(
            bot, prompt_id_pattern="sector_command", timeout_ms=5000
        )

        print(f"\nPrompt detected: {prompt_id}")
        print(f"Input type: {input_type}")
        print("\nScreen content:")
        print("-" * 80)
        print(screen[:500])  # First 500 chars
        print("-" * 80)

        print(f"\nK/V Data present: {kv_data is not None}")
        if kv_data:
            print("K/V Data extracted:")
            for key, value in kv_data.items():
                if key == "_validation":
                    print(f"  {key}: {value}")
                else:
                    print(f"  {key}: {value}")

            # Analyze validation
            validation = kv_data.get("_validation", {})
            if validation.get("valid"):
                print("\n✓ VALIDATION PASSED")
                sector = kv_data.get("sector")
                credits = kv_data.get("credits")
                print(f"  Current state: Sector {sector}, Credits {credits:,}")
            else:
                print("\n✗ VALIDATION FAILED")
                for error in validation.get("errors", []):
                    print(f"  Error: {error}")
        else:
            print("\n⚠️  No K/V data - testing manual extraction...")

            # Try manual extraction to debug
            kv_config = [
                {
                    "field": r.field,
                    "type": r.type,
                    "regex": r.regex,
                    "validate": r.validate,
                    "required": r.required,
                }
                for r in sector_rule.kv_extract
            ]

            result = KVExtractor.extract(screen, kv_config)
            print(f"  Manual extraction result: {result}")

        print("\n✅ STATE VERIFICATION COMPLETE")

    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback

        traceback.print_exc()
        return False

    finally:
        if bot.session_id:
            await bot.session_manager.close_session(bot.session_id)

    return True


async def test_kv_flow_through_system():
    """Test that K/V data flows correctly through the entire system."""
    print("\n" + "=" * 80)
    print("K/V DATA FLOW TEST")
    print("=" * 80)

    print("\n1. Testing extraction in isolation...")
    from bbsbot.learning.extractor import KVExtractor

    config = {
        "field": "sector",
        "type": "int",
        "regex": r"Sector\s+(\d+)",
        "validate": {"min": 1, "max": 1000},
        "required": True,
    }

    screen = "Sector 499 in Outer Sector"
    result = KVExtractor.extract(screen, config)
    print(f"   Extraction: {result}")
    assert result and result["sector"] == 499, "Extraction failed"
    print("   ✓ PASS")

    print("\n2. Testing validation in isolation...")
    config_list = [
        {
            "field": "sector",
            "type": "int",
            "regex": r"Sector\s+(\d+)",
            "validate": {"min": 1, "max": 1000},
            "required": True,
        },
        {
            "field": "credits",
            "type": "int",
            "regex": r"Credits?:\s*([\d,]+)",
            "validate": {"min": 0},
            "required": True,
        },
    ]

    screen = "Sector 100\nCredits: 1,000,000"
    result = KVExtractor.extract(screen, config_list)
    print(f"   Extraction: sector={result['sector']}, credits={result['credits']}")
    assert result["_validation"]["valid"], "Validation should pass"
    print("   ✓ PASS")

    print("\n3. Testing invalid data detection...")
    screen = "Sector 9999\nCredits: 0"
    result = KVExtractor.extract(screen, config_list)
    print(f"   Validation status: {result['_validation']['valid']}")
    print(f"   Errors: {result['_validation']['errors']}")
    assert not result["_validation"]["valid"], "Should detect invalid sector"
    print("   ✓ PASS")

    print("\n✅ K/V DATA FLOW TEST COMPLETE")
    return True


async def main():
    """Run all state verification tests."""
    print("\n" + "=" * 80)
    print("STATE VERIFICATION & VALIDATION ACCURACY TESTS")
    print("=" * 80)

    # Test 1: K/V data flow
    flow_ok = await test_kv_flow_through_system()

    # Test 2: Sector command detection
    sector_ok = await test_sector_command_detection()

    # Summary
    print("\n" + "=" * 80)
    print("FINAL VERIFICATION RESULTS")
    print("=" * 80)
    print(f"K/V data flow: {'✓ PASS' if flow_ok else '✗ FAIL'}")
    print(f"Sector detection: {'✓ PASS' if sector_ok else '✗ FAIL'}")

    if flow_ok and sector_ok:
        print("\n✅ ALL VERIFICATION TESTS PASSED")
        return True
    else:
        print("\n⚠️  SOME TESTS FAILED - CHECK DETAILS ABOVE")
        return False


if __name__ == "__main__":
    try:
        result = asyncio.run(main())
        sys.exit(0 if result else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(1)
