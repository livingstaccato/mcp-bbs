# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Transport layer for BBS connections."""

from __future__ import annotations

from bbsbot.transport.base import ConnectionTransport
from bbsbot.transport.telnet import TelnetTransport

__all__ = ["ConnectionTransport", "TelnetTransport"]
