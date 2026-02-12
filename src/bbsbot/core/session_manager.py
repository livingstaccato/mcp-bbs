# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Multi-session management with resource limits."""

from __future__ import annotations

import asyncio
import uuid
from typing import TYPE_CHECKING, Any

import structlog

from bbsbot.addons.manager import AddonManager
from bbsbot.addons.tedit import TeditAddon
from bbsbot.addons.tw2002 import Tw2002Addon
from bbsbot.constants import (
    DEFAULT_COLS,
    DEFAULT_CONNECT_TIMEOUT_S,
    DEFAULT_MAX_SESSIONS,
    DEFAULT_ROWS,
    DEFAULT_TERM,
)
from bbsbot.core.session import Session
from bbsbot.learning.engine import LearningEngine
from bbsbot.logging.session_logger import SessionLogger
from bbsbot.paths import default_knowledge_root, find_repo_games_root
from bbsbot.terminal.emulator import TerminalEmulator
from bbsbot.transport.chaos import ChaosTransport
from bbsbot.transport.telnet import TelnetTransport

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

log = structlog.get_logger()


class SessionManager:
    """Manages multiple concurrent BBS sessions."""

    def __init__(self, max_sessions: int = DEFAULT_MAX_SESSIONS) -> None:
        """Initialize session manager.

        Args:
            max_sessions: Maximum number of concurrent sessions
        """
        self._sessions: dict[str, Session] = {}
        self._bots: dict[str, Any] = {}  # session_id -> bot instance
        self._max_sessions = max_sessions
        self._lock = asyncio.Lock()
        self._session_counter = 0

    async def create_session(
        self,
        host: str,
        port: int,
        transport_type: str = "telnet",
        cols: int = DEFAULT_COLS,
        rows: int = DEFAULT_ROWS,
        term: str = DEFAULT_TERM,
        timeout: float = DEFAULT_CONNECT_TIMEOUT_S,
        reuse: bool = False,
        send_newline: bool = False,
        session_id: str | None = None,
        **options: Any,
    ) -> str:
        """Create new session or reuse existing one.

        Args:
            host: Remote hostname or IP address
            port: Remote port number
            transport_type: Transport protocol ("telnet", "ssh")
            cols: Terminal columns
            rows: Terminal rows
            term: Terminal type
            timeout: Connection timeout in seconds
            reuse: Reuse existing session to same host:port if available
            send_newline: Send newline after connecting
            session_id: Optional specific session ID (defaults to UUID)
            **options: Additional transport-specific options

        Returns:
            Session ID

        Raises:
            RuntimeError: If max sessions reached
            ConnectionError: If connection fails
            ValueError: If unknown transport type
        """
        # Check for reusable session (lock only for brief read)
        async with self._lock:
            if reuse:
                for sid, session in self._sessions.items():
                    if session.host == host and session.port == port and session.is_connected():
                        # Update size if different
                        if session.emulator.cols != cols or session.emulator.rows != rows:
                            await session.set_size(cols, rows)
                        # Send newline if requested
                        if send_newline:
                            await session.send("\r\n")
                        log.info("session_reused", session_id=sid, host=host, port=port)
                        return sid

            # Check session limit
            if len(self._sessions) >= self._max_sessions:
                raise RuntimeError(f"Max sessions ({self._max_sessions}) reached")

            # Reserve a session ID WITHOUT holding the lock during connection
            if not session_id:
                session_id = str(uuid.uuid4())
            self._session_counter += 1
            session_number = self._session_counter

        # **CRITICAL FIX**: Move network connection OUTSIDE the lock
        # This allows multiple bots to connect in parallel instead of serially
        # Validate transport type first (quick check)
        if transport_type == "telnet":
            chaos = options.pop("chaos", None)
            transport = TelnetTransport()
            if chaos:
                # Deterministic fault injection for resilience testing.
                transport = ChaosTransport(transport, **dict(chaos))
        else:
            raise ValueError(f"Unknown transport: {transport_type}")

        # Connect with timeout - NO LOCK HELD
        try:
            await asyncio.wait_for(
                transport.connect(host, port, cols=cols, rows=rows, term=term, **options),
                timeout=timeout,
            )
        except TimeoutError as e:
            raise ConnectionError(f"Connection timeout to {host}:{port}") from e
        except Exception as e:
            raise ConnectionError(f"Failed to connect to {host}:{port}: {e}") from e

        # Create session components and register (reacquire lock for registration)
        emulator = TerminalEmulator(cols, rows, term)
        session = Session(
            session_id=session_id,
            session_number=session_number,
            transport=transport,
            emulator=emulator,
            host=host,
            port=port,
        )

        async with self._lock:
            # Double-check we haven't exceeded limits while we were connecting
            if len(self._sessions) >= self._max_sessions:
                await transport.disconnect()
                raise RuntimeError(f"Max sessions ({self._max_sessions}) reached")

            self._sessions[session_id] = session
            self._emit_session_created(session)

        # Start event-driven reader pump (end-state: no caller performs transport receives).
        session.start_reader()

        # Send newline if requested (after registration)
        if send_newline:
            await session.send("\r\n")

        log.info(
            "session_created",
            session_id=session_id,
            session_number=session_number,
            host=host,
            port=port,
            cols=cols,
            rows=rows,
            term=term,
        )

        return session_id

    async def get_session(self, session_id: str) -> Session:
        """Get session by ID.

        Args:
            session_id: Session identifier

        Returns:
            Session object

        Raises:
            ValueError: If session not found
        """
        if session_id not in self._sessions:
            raise ValueError(f"Session not found: {session_id}")
        return self._sessions[session_id]

    async def close_session(self, session_id: str) -> None:
        """Close and remove session.

        Args:
            session_id: Session identifier

        Raises:
            ValueError: If session not found
        """
        session = await self.get_session(session_id)
        await session.disconnect()

        async with self._lock:
            del self._sessions[session_id]
            # Auto-unregister bot if registered
            if session_id in self._bots:
                del self._bots[session_id]

        log.info("session_closed", session_id=session_id)

    async def close_all_sessions(self) -> None:
        """Close all sessions."""
        session_ids = list(self._sessions.keys())
        for session_id in session_ids:
            try:
                await self.close_session(session_id)
            except Exception as e:
                log.warning("session_close_failed", session_id=session_id, error=str(e))

    def list_sessions(self) -> list[dict[str, Any]]:
        """List all sessions.

        Returns:
            List of session status dictionaries
        """
        return [session.get_status() for session in self._sessions.values()]

    async def enable_logging(self, session_id: str, log_path: str | Path) -> None:
        """Enable JSONL logging for a session.

        Args:
            session_id: Session identifier
            log_path: Path to JSONL log file

        Raises:
            ValueError: If session not found
        """
        session = await self.get_session(session_id)

        if session.logger:
            await session.logger.stop()

        session.logger = SessionLogger(log_path)
        await session.logger.start(session.session_number)

        log.info("logging_enabled", session_id=session_id, log_path=str(log_path))

    def register_session_callback(self, callback: Callable[[Session], None]) -> None:
        """Register a callback invoked for every new session."""
        if not hasattr(self, "_session_callbacks"):
            self._session_callbacks: list[Callable[[Session], None]] = []
        self._session_callbacks.append(callback)

    def _emit_session_created(self, session: Session) -> None:
        callbacks: list[Callable[[Session], None]] = getattr(self, "_session_callbacks", [])
        for callback in callbacks:
            try:
                callback(session)
            except Exception as exc:
                log.warning("session_callback_failed", session_id=session.session_id, error=str(exc))

    async def disable_logging(self, session_id: str) -> None:
        """Disable logging for a session.

        Args:
            session_id: Session identifier

        Raises:
            ValueError: If session not found
        """
        session = await self.get_session(session_id)

        if session.logger:
            await session.logger.stop()
            session.logger = None

        log.info("logging_disabled", session_id=session_id)

    async def enable_learning(
        self,
        session_id: str,
        knowledge_root: Path | None = None,
        namespace: str | None = None,
    ) -> None:
        """Enable learning for a session.

        Args:
            session_id: Session identifier
            knowledge_root: Knowledge base root (defaults to config value)
            namespace: Optional namespace for game-specific knowledge

        Raises:
            ValueError: If session not found
        """
        session = await self.get_session(session_id)

        if not knowledge_root:
            knowledge_root = default_knowledge_root()

        if session.logger is None and namespace:
            repo_games_root = find_repo_games_root()
            if repo_games_root:
                log_path = repo_games_root / namespace / "session.jsonl"
            else:
                log_path = knowledge_root / "games" / namespace / "session.jsonl"
            session.logger = SessionLogger(log_path)
            await session.logger.start(session.session_number)

        session.learning = LearningEngine(knowledge_root, namespace)
        if namespace == "tw2002":
            session.addons = AddonManager(addons=[Tw2002Addon()])
        if namespace == "tedit":
            session.addons = AddonManager(addons=[TeditAddon()])

        log.info(
            "learning_enabled",
            session_id=session_id,
            knowledge_root=str(knowledge_root),
            namespace=namespace,
        )

    async def set_watch(
        self,
        session_id: str,
        callback: Callable[[dict[str, Any]], None] | None,
        interval_s: float = 0.0,
    ) -> None:
        session = await self.get_session(session_id)
        session.set_watch(callback, interval_s=interval_s)

    async def disable_learning(self, session_id: str) -> None:
        """Disable learning for a session.

        Args:
            session_id: Session identifier

        Raises:
            ValueError: If session not found
        """
        session = await self.get_session(session_id)
        session.learning = None

        log.info("learning_disabled", session_id=session_id)

    def register_bot(self, session_id: str, bot_instance: Any) -> None:
        """Register a bot instance for a session.

        Allows MCP tools to access running bot for debugging.

        Args:
            session_id: Session identifier
            bot_instance: Bot instance to register
        """
        self._bots[session_id] = bot_instance
        log.info("bot_registered", session_id=session_id, bot_type=type(bot_instance).__name__)

    def get_bot(self, session_id: str) -> Any | None:
        """Get registered bot for a session.

        Args:
            session_id: Session identifier

        Returns:
            Bot instance or None if not registered
        """
        return self._bots.get(session_id)

    def unregister_bot(self, session_id: str) -> None:
        """Unregister bot for a session.

        Args:
            session_id: Session identifier
        """
        if session_id in self._bots:
            del self._bots[session_id]
            log.info("bot_unregistered", session_id=session_id)
