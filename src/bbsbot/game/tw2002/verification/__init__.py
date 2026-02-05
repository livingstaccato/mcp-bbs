"""Verification flows for TW2002."""

from .twgs_commands import main as twgs_commands_main
from .login import login as login_main
from .game_entry import main as game_entry_main
from .new_character import test as new_character_main
from .orientation_recovery import main as orientation_recovery_main
from .trading_integration import main as trading_integration_main
from .validation_and_menus import main as validation_and_menus_main

__all__ = [
    "twgs_commands_main",
    "login_main",
    "game_entry_main",
    "new_character_main",
    "orientation_recovery_main",
    "trading_integration_main",
    "validation_and_menus_main",
]
