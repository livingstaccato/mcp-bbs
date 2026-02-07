#!/usr/bin/env python3
"""Test script for goals system.

Tests:
1. Goal configuration loads correctly
2. Goal selection logic works
3. Goals inject into prompts
4. MCP tools are registered
"""
import sys


def test_goals_config():
    """Test goals configuration loads."""
    print("\n[Test 1] Goals configuration...")
    try:
        from bbsbot.games.tw2002.config import BotConfig

        config = BotConfig()
        goals_config = config.trading.ai_strategy.goals

        # Check default goals exist
        goal_ids = [g.id for g in goals_config.available]
        expected = ["profit", "combat", "exploration", "banking"]

        if all(g in goal_ids for g in expected):
            print(f"  ✓ All default goals present: {goal_ids}")
            return True
        else:
            print(f"  ✗ Missing goals. Expected {expected}, got {goal_ids}")
            return False
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False


def test_goal_selection():
    """Test goal selection logic."""
    print("\n[Test 2] Goal selection logic...")
    try:
        from bbsbot.games.tw2002.config import BotConfig
        from bbsbot.games.tw2002.strategies.ai_strategy import AIStrategy
        from bbsbot.games.tw2002.orientation import SectorKnowledge, GameState
        from pathlib import Path

        config = BotConfig()
        knowledge = SectorKnowledge(
            knowledge_dir=Path("/tmp/test_knowledge"),
            character_name="test",
        )
        strategy = AIStrategy(config, knowledge)

        # Test with low credits (should select profit goal)
        state = GameState(
            context="sector_command",
            sector=1,
            credits=5000,  # Low credits
            turns_left=100,
        )

        import asyncio
        goal = asyncio.run(strategy._select_goal(state))

        if goal == "profit":
            print(f"  ✓ Low credits correctly selected 'profit' goal")
            return True
        else:
            print(f"  ✗ Expected 'profit', got '{goal}'")
            return False
    except Exception as e:
        print(f"  ✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_goal_in_prompts():
    """Test goals inject into prompts."""
    print("\n[Test 3] Goal injection into prompts...")
    try:
        from bbsbot.games.tw2002.strategies.ai.prompts import PromptBuilder
        from bbsbot.games.tw2002.orientation import GameState, SectorKnowledge
        from pathlib import Path

        builder = PromptBuilder()
        state = GameState(context="sector_command", sector=1)
        knowledge = SectorKnowledge(
            knowledge_dir=Path("/tmp/test_knowledge"),
            character_name="test",
        )
        stats = {}

        # Build with goal
        messages = builder.build(
            state,
            knowledge,
            stats,
            goal_description="Test goal",
            goal_instructions="Do test things",
        )

        # Check if goal appears in system prompt
        system_prompt = messages[0].content
        if "Test goal" in system_prompt and "Do test things" in system_prompt:
            print("  ✓ Goal correctly injected into system prompt")
            return True
        else:
            print("  ✗ Goal not found in prompt")
            print(f"  System prompt: {system_prompt[:200]}...")
            return False
    except Exception as e:
        print(f"  ✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_mcp_registry():
    """Test MCP registry system."""
    print("\n[Test 4] MCP registry system...")
    try:
        from bbsbot.mcp.registry import create_registry

        # Create test registry
        registry = create_registry("test")

        # Register a test tool
        @registry.tool()
        async def test_tool(arg: str) -> dict:
            """Test tool."""
            return {"result": arg}

        # Check it was registered
        tools = registry.get_tools()
        if "test_test_tool" in tools:
            print(f"  ✓ Registry created and tool registered: test_test_tool")
            return True
        else:
            print(f"  ✗ Tool not found in registry. Tools: {list(tools.keys())}")
            return False
    except Exception as e:
        print(f"  ✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_tw2002_tools():
    """Test TW2002 tools are registered."""
    print("\n[Test 5] TW2002 MCP tools...")
    try:
        # Import triggers registration
        from bbsbot.games.tw2002 import mcp_tools
        from bbsbot.mcp.registry import get_manager

        manager = get_manager()
        tools = manager.get_all_tools()

        expected_tools = [
            "tw2002_set_goal",
            "tw2002_get_goals",
            "tw2002_get_trade_opportunities",
            "tw2002_analyze_combat_readiness",
            "tw2002_get_bot_status",
        ]

        found = [t for t in expected_tools if t in tools]

        if len(found) == len(expected_tools):
            print(f"  ✓ All TW2002 tools registered: {found}")
            return True
        else:
            missing = set(expected_tools) - set(found)
            print(f"  ✗ Missing tools: {missing}")
            print(f"  Available: {list(tools.keys())}")
            return False
    except Exception as e:
        print(f"  ✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("="*60)
    print("GOALS SYSTEM & MCP TOOLS TESTS")
    print("="*60)

    tests = [
        test_goals_config,
        test_goal_selection,
        test_goal_in_prompts,
        test_mcp_registry,
        test_tw2002_tools,
    ]

    results = []
    for test in tests:
        try:
            results.append(test())
        except Exception as e:
            print(f"\n  ✗ Test crashed: {e}")
            results.append(False)

    print("\n" + "="*60)
    print(f"RESULTS: {sum(results)}/{len(results)} tests passed")
    print("="*60)

    if all(results):
        print("\n✓ All tests passed!")
        return 0
    else:
        print("\n✗ Some tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
