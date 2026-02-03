"""Multi-session management with resource limits."""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

import structlog

from mcp_bbs.config import get_default_knowledge_root
from mcp_bbs.constants import (
    DEFAULT_COLS,
    DEFAULT_CONNECT_TIMEOUT_S,
    DEFAULT_MAX_SESSIONS,
    DEFAULT_ROWS,
    DEFAULT_TERM,
)
from mcp_bbs.core.session import Session
from mcp_bbs.learning.engine import LearningEngine
from mcp_bbs.logging.session_logger import SessionLogger
from mcp_bbs.terminal.emulator import TerminalEmulator
from mcp_bbs.transport.telnet import TelnetTransport

log = structlog.get_logger()


class SessionManager:
    """Manages multiple concurrent BBS sessions."""

    def __init__(self, max_sessions: int = DEFAULT_MAX_SESSIONS) -> None:
        """Initialize session manager.

        Args:
            max_sessions: Maximum number of concurrent sessions
        """
        self._sessions: dict[str, Session] = {}
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
        **options,
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
        async with self._lock:
            # Check for reusable session
            if reuse:
                for session_id, session in self._sessions.items():
                    if session.host == host and session.port == port and session.is_connected():
                        # Update size if different
                        if session.emulator.cols != cols or session.emulator.rows != rows:
                            await session.set_size(cols, rows)
                        # Send newline if requested
                        if send_newline:
                            await session.send("\r\n")
                        log.info("session_reused", session_id=session_id, host=host, port=port)
                        return session_id

            # Check session limit
            if len(self._sessions) >= self._max_sessions:
                raise RuntimeError(f"Max sessions ({self._max_sessions}) reached")

            # Create transport
            if transport_type == "telnet":
                transport = TelnetTransport()
            else:
                raise ValueError(f"Unknown transport: {transport_type}")

            # Connect with timeout
            try:
                await asyncio.wait_for(
                    transport.connect(host, port, cols=cols, rows=rows, term=term, **options),
                    timeout=timeout,
                )
            except asyncio.TimeoutError as e:
                raise ConnectionError(f"Connection timeout to {host}:{port}") from e

            # Create session components
            if not session_id:
                session_id = str(uuid.uuid4())

            self._session_counter += 1
            emulator = TerminalEmulator(cols, rows, term)
            session = Session(
                session_id=session_id,
                session_number=self._session_counter,
                transport=transport,
                emulator=emulator,
                host=host,
                port=port,
            )

            self._sessions[session_id] = session

            # Send newline if requested
            if send_newline:
                await session.send("\r\n")

            log.info(
                "session_created",
                session_id=session_id,
                session_number=self._session_counter,
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

        log.info("session_closed", session_id=session_id)

    async def close_all_sessions(self) -> None:
        """Close all sessions."""
        session_ids = list(self._sessions.keys())
        for session_id in session_ids:
            try:
                await self.close_session(session_id)
            except Exception as e:
                log.warning("session_close_failed", session_id=session_id, error=str(e))

    def list_sessions(self) -> list[dict]:
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
            knowledge_root = get_default_knowledge_root()

        session.learning = LearningEngine(knowledge_root, namespace)

        log.info(
            "learning_enabled",
            session_id=session_id,
            knowledge_root=str(knowledge_root),
            namespace=namespace,
        )

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
