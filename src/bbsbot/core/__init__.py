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
