# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

from bbsbot.games.tw2002.login import _get_actual_prompt, _normalize_phase3_prompt


def test_private_password_detected_when_banner_is_immediate() -> None:
    screen = "\n".join(
        [
            "A password is required to enter this game.",
            "Password?",
        ]
    )
    assert _get_actual_prompt(screen) == "private_game_password"


def test_password_prompt_not_misclassified_from_stale_private_banner() -> None:
    screen = "\n".join(
        [
            "A password is required to enter this game.",
            "Password? ****",
            "Invalid password.",
            "Password?",
        ]
    )
    assert _get_actual_prompt(screen) == "password_prompt"


def test_phase3_password_prompts_use_generic_disambiguation_branch() -> None:
    assert _normalize_phase3_prompt("prompt.character_password", "private_game_password") == "password_prompt"
    assert _normalize_phase3_prompt("prompt.game_password", "") == "password_prompt"
    assert _normalize_phase3_prompt("prompt.private_game_password", "password_prompt") == "password_prompt"
    assert _normalize_phase3_prompt("prompt.sector_command", "command_prompt") == "command_prompt"
