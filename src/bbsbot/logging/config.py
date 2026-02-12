# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Centralized logging configuration for bbsbot.

This module provides structured logging using structlog, configured to:
- Write all logs to stderr (MCP uses stdout for JSON-RPC)
- Respect BBSBOT_LOG_LEVEL environment variable (default: WARNING)
- Use ISO timestamps and console rendering
"""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from bbsbot.settings import Settings

__all__ = ["get_logger", "configure_logging"]


def configure_logging(settings: Settings | None = None) -> None:
    """Configure structlog for bbsbot.

    This should be called once at application startup.
    Respects BBSBOT_LOG_LEVEL environment variable via Settings (default: WARNING).

    Args:
        settings: Settings instance (will be created if None)
    """
    if settings is None:
        from bbsbot.settings import Settings

        settings = Settings()

    log_level = getattr(logging, settings.log_level.upper(), logging.WARNING)

    # Configure structlog to write to stderr (MCP uses stdout for JSON-RPC)
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )


def get_logger(name: str | None = None) -> structlog.BoundLogger:
    """Get a structlog logger instance.

    Args:
        name: Logger name (typically __name__ of calling module)

    Returns:
        Configured structlog logger
    """
    return structlog.get_logger(name)
