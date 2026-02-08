"""Base class for game bots with framework concerns.

This module provides a base class that handles common bot infrastructure
like session management, error tracking, and connection lifecycle.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from bbsbot.core.error_detection import LoopDetector
from bbsbot.core.session_manager import SessionManager
from bbsbot.paths import default_knowledge_root


class BotBase:
    """Base class for game bots with framework concerns.

    Subclasses should:
    1. Call super().__init__() in their __init__
    2. Override run() to implement game-specific logic
    3. Use connect() to establish BBS connection
    4. Use disconnect() to clean up on exit

    The base class handles:
    - Session management (SessionManager, session lifecycle)
    - Knowledge root path management
    - Loop detection and error tracking
    - Step counting and timing
    - Prompt detection tracking
    """

    def __init__(self, character_name: str = "unknown"):
        """Initialize base bot.

        Args:
            character_name: Name of the character/player
        """
        # Framework state
        self.session_manager = SessionManager()
        self.knowledge_root = default_knowledge_root()
        self.session_id: str | None = None
        self.session: Any = None
        self.character_name = character_name

        # Generic tracking
        self.step_count = 0
        self.error_count = 0
        self.detected_prompts: list[dict] = []

        # Loop detection (legacy - new bots should use LoopDetector directly)
        self.loop_detection: dict[str, int] = {}
        self.last_prompt_id: str | None = None
        self.stuck_threshold = 10  # Increased from 3 to allow legitimate repeated prompts

        # Session tracking
        self.session_start_time = time.time()

    async def connect(
        self,
        host: str = "localhost",
        port: int = 2002,
        cols: int = 80,
        rows: int = 25,
        term: str = "ANSI",
        timeout: float = 10.0,
        namespace: str | None = None,
    ) -> None:
        """Generic connection setup.

        Args:
            host: BBS hostname
            port: BBS port
            cols: Terminal columns
            rows: Terminal rows
            term: Terminal type
            timeout: Connection timeout
            namespace: Learning namespace (e.g., "tw2002")
        """
        self.session_id = await self.session_manager.create_session(
            host=host, port=port, cols=cols, rows=rows, term=term, timeout=timeout
        )
        self.session = await self.session_manager.get_session(self.session_id)

        # Enable learning if namespace provided
        if namespace:
            await self.session_manager.enable_learning(
                self.session_id, self.knowledge_root, namespace=namespace
            )

    async def disconnect(self) -> None:
        """Generic disconnect cleanup."""
        if self.session_id:
            await self.session_manager.close_session(self.session_id)
            self.session_id = None
            self.session = None

    def is_looping(self, prompt_id: str) -> bool:
        """Check if stuck in loop (legacy interface).

        New bots should use LoopDetector directly for better control.

        Args:
            prompt_id: Current prompt ID

        Returns:
            True if stuck in loop
        """
        if not hasattr(self, "_loop_detector"):
            self._loop_detector = LoopDetector(threshold=self.stuck_threshold)

        return self._loop_detector.check(prompt_id)

    def get_elapsed_time(self) -> float:
        """Get elapsed session time in seconds.

        Returns:
            Seconds since session start
        """
        return time.time() - self.session_start_time

    async def run(self) -> None:
        """Game-specific run logic.

        Subclasses MUST override this method to implement their game logic.
        """
        raise NotImplementedError("Subclasses must implement run()")
