#!/usr/bin/env python3
# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Generate comprehensive test matrix for bot configurations."""

from __future__ import annotations

import itertools
from pathlib import Path

import yaml

# Test dimensions
GAMES = ["A", "B", "C"]
STRATEGIES = ["opportunistic", "ai_strategy"]
TURN_LIMITS = [15, 30, 50]
EXPLORATION_LEVELS = [0.2, 0.5, 0.8]  # Low, medium, high
BANKING_OPTIONS = [True, False]
INTERVENTION_OPTIONS = [
    {"enabled": False},
    {"enabled": True, "auto_apply": False},
    {"enabled": True, "auto_apply": True},
]


def create_opportunistic_config(game: str, turns: int, explore: float, banking: bool) -> dict:
    """Create opportunistic strategy config."""
    return {
        "connection": {
            "host": "localhost",
            "port": 2002,
            "game_letter": game,
        },
        "trading": {
            "strategy": "opportunistic",
            "opportunistic": {
                "explore_chance": explore,
                "max_wander_without_trade": 5 if explore > 0.5 else 3,
            },
        },
        "session": {
            "max_turns_per_session": turns,
            "target_credits": 50000 if turns < 25 else 100000,
        },
        "banking": {
            "enabled": banking,
            **({"min_credits_to_bank": 25000} if banking else {}),
        },
        "upgrades": {
            "enabled": False,
        },
    }


def create_ai_config(game: str, turns: int, intervention: dict, banking: bool) -> dict:
    """Create AI strategy config."""
    config = {
        "connection": {
            "host": "localhost",
            "port": 2002,
            "game_letter": game,
        },
        "trading": {
            "strategy": "ai_strategy",
            "ai_strategy": {
                "enabled": True,
                "fallback_strategy": "opportunistic",
                "fallback_threshold": 3,
                "intervention": intervention,
            },
        },
        "llm": {
            "provider": "ollama",
            "ollama": {
                "base_url": "http://localhost:11434",
                "model": "gemma3",
                "timeout_seconds": 30.0,
            },
        },
        "session": {
            "max_turns_per_session": turns,
            "target_credits": 75000 if turns < 40 else 150000,
        },
        "banking": {
            "enabled": banking,
            **({"min_credits_to_bank": 50000} if banking else {}),
        },
        "upgrades": {
            "enabled": False,
        },
    }

    # Add intervention thresholds if enabled
    if intervention.get("enabled"):
        config["trading"]["ai_strategy"]["intervention"].update(
            {
                "min_priority": "low",
                "cooldown_turns": 3,
                "max_per_session": 20,
                "loop_action_threshold": 2,
                "loop_sector_threshold": 3,
                "stagnation_turns": 8,
                "profit_decline_ratio": 0.5,
                "turn_waste_threshold": 0.3,
                "analysis_temperature": 0.3,
                "analysis_max_tokens": 800,
            }
        )

    return config


def generate_all_configs():
    """Generate all test configuration files."""
    output_dir = Path("config/test_matrix")
    output_dir.mkdir(parents=True, exist_ok=True)

    test_num = 0

    # Generate opportunistic configs
    for game, turns, explore, banking in itertools.product(GAMES, TURN_LIMITS, EXPLORATION_LEVELS, BANKING_OPTIONS):
        test_num += 1
        config = create_opportunistic_config(game, turns, explore, banking)

        filename = f"{test_num:02d}_game{game}_opp_t{turns}_e{int(explore * 10)}_b{int(banking)}.yaml"
        filepath = output_dir / filename

        with open(filepath, "w") as f:
            f.write(
                f"# Test {test_num}: Game {game}, Opportunistic, {turns} turns, explore={explore}, banking={banking}\n"
            )
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)

        print(f"Created: {filename}")

    # Generate AI strategy configs
    for game, turns, intervention, banking in itertools.product(
        GAMES, TURN_LIMITS, INTERVENTION_OPTIONS, BANKING_OPTIONS
    ):
        test_num += 1
        config = create_ai_config(game, turns, intervention, banking)

        intervention_str = (
            "no_int" if not intervention["enabled"] else f"int_auto{int(intervention.get('auto_apply', False))}"
        )
        filename = f"{test_num:02d}_game{game}_ai_t{turns}_{intervention_str}_b{int(banking)}.yaml"
        filepath = output_dir / filename

        with open(filepath, "w") as f:
            f.write(
                f"# Test {test_num}: Game {game}, AI Strategy, "
                f"{turns} turns, intervention={intervention_str}, banking={banking}\n"
            )
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)

        print(f"Created: {filename}")

    print(f"\n✓ Generated {test_num} test configurations in {output_dir}")
    return test_num


if __name__ == "__main__":
    total = generate_all_configs()
    print(f"\nTotal configurations: {total}")
