# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Core session management."""

from __future__ import annotations

from bbsbot.core.bot_base import BotBase
from bbsbot.core.error_detection import BaseErrorDetector, ErrorDetector, LoopDetector
from bbsbot.core.generic_io import InputSender, PromptWaiter
from bbsbot.core.login_flow import LoginHandler, MultiStageLoginFlow
from bbsbot.core.session import Session
from bbsbot.core.session_manager import SessionManager

__all__ = [
    "BaseErrorDetector",
    "BotBase",
    "ErrorDetector",
    "InputSender",
    "LoginHandler",
    "LoopDetector",
    "MultiStageLoginFlow",
    "PromptWaiter",
    "Session",
    "SessionManager",
]
