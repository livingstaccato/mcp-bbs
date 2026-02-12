# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Verification flows for TW2002."""

from bbsbot.games.tw2002.verification.game_entry import main as game_entry_main
from bbsbot.games.tw2002.verification.login import login as login_main
from bbsbot.games.tw2002.verification.new_character import test as new_character_main
from bbsbot.games.tw2002.verification.orientation_recovery import (
    main as orientation_recovery_main,
)
from bbsbot.games.tw2002.verification.trading_integration import (
    main as trading_integration_main,
)
from bbsbot.games.tw2002.verification.twgs_commands import main as twgs_commands_main
from bbsbot.games.tw2002.verification.validation_and_menus import (
    main as validation_and_menus_main,
)

__all__ = [
    "twgs_commands_main",
    "login_main",
    "game_entry_main",
    "new_character_main",
    "orientation_recovery_main",
    "trading_integration_main",
    "validation_and_menus_main",
]
