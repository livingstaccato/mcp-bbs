"""TEDIT Session Manager for TW2002 admin interface.

Provides high-level methods to interact with TEDIT (Sysop Editor) via MCP-BBS.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from bbsbot.core.session_manager import SessionManager
from bbsbot.paths import default_knowledge_root

# Regex patterns for parsing TEDIT screens
_FIELD_PATTERN = re.compile(r"<(?P<key>.?)>\s*(?P<label>[^:]+?)\s*:\s*(?P<value>.+)$")
_SIMPLE_KV_PATTERN = re.compile(r"^(?P<label>[A-Za-z0-9 /#'\-\[\]<>]+)\s*:\s*(?P<value>.+)$")
_USER_LINE_PATTERN = re.compile(
    r"^\s*(?P<id>\d+)\s+(?P<name>\S+)\s+(?P<sector>\d+)\s+(?P<fighters>\d+)\s+"
    r"(?P<shields>\d+)\s+(?P<ship>.+?)\s+(?P<turns>\d+)\s+(?P<corp>\d+)\s*$"
)
_EDITOR_HEADER_PATTERN = re.compile(r"Trade Wars 2002.*Editor", re.IGNORECASE)
_PROMPT_PATTERN = re.compile(r"\[.\]\s*[:\?]?\s*$")


class TEDITManager(BaseModel):
    """Manage TEDIT sessions via MCP-BBS."""

    host: str = "localhost"
    port: int = 2003  # Admin port
    password: str = "admin"

    session_manager: SessionManager = Field(default_factory=SessionManager)
    session_id: str | None = None
    session: Any = None
    knowledge_root: Any = Field(default_factory=default_knowledge_root)

    # State tracking
    current_game: str | None = None
    current_editor: str | None = None
    connected: bool = False

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="ignore")

    async def connect(
        self,
        host: str | None = None,
        port: int | None = None,
        password: str | None = None,
    ) -> bool:
        """Connect to TEDIT admin interface.

        Args:
            host: Override default host
            port: Override default port
            password: Override default password

        Returns:
            True if connection and authentication successful
        """
        if host:
            self.host = host
        if port:
            self.port = port
        if password:
            self.password = password

        self.session_id = await self.session_manager.create_session(
            host=self.host,
            port=self.port,
            cols=80,
            rows=25,
            term="ANSI",
            timeout=10.0,
        )
        self.session = await self.session_manager.get_session(self.session_id)

        # Enable learning with tedit namespace
        await self.session_manager.enable_learning(self.session_id, self.knowledge_root, namespace="tedit")

        # Wait for initial screen
        await asyncio.sleep(0.5)
        screen = await self._read_screen()

        # Handle password prompt
        if "password" in screen.lower():
            await self._send(self.password + "\r")
            await asyncio.sleep(0.3)
            screen = await self._read_screen()

        self.connected = True
        return True

    async def disconnect(self) -> None:
        """Disconnect from TEDIT."""
        if self.session_id:
            await self.session_manager.close_session(self.session_id)
            self.session_id = None
            self.session = None
            self.connected = False
            self.current_game = None
            self.current_editor = None

    async def enter_tedit(self, game_id: str = "A") -> bool:
        """Navigate to TEDIT and select a game.

        Args:
            game_id: Game slot to edit (A or B)

        Returns:
            True if successfully entered TEDIT for the game
        """
        # Press E to enter TEDIT from admin menu
        await self._send("E")
        await asyncio.sleep(0.5)
        screen = await self._read_screen()

        # Select game
        await self._send(game_id)
        await asyncio.sleep(0.5)
        screen = await self._read_screen()

        # Verify we're in TEDIT
        if _EDITOR_HEADER_PATTERN.search(screen):
            self.current_game = game_id
            return True

        return False

    async def exit_tedit(self) -> None:
        """Exit TEDIT back to admin menu."""
        await self._send("Q")
        await asyncio.sleep(0.3)
        self.current_game = None
        self.current_editor = None

    async def select_game(self, game_id: str) -> bool:
        """Select game slot (A or B).

        Args:
            game_id: Game slot identifier

        Returns:
            True if game selected successfully
        """
        if self.current_game:
            await self.exit_tedit()

        return await self.enter_tedit(game_id)

    async def get_general_settings_one(self) -> dict[str, Any]:
        """Read General Editor One settings.

        Returns:
            Dictionary of setting key -> {label, value}
        """
        return await self._read_editor_settings("G")

    async def get_general_settings_two(self) -> dict[str, Any]:
        """Read General Editor Two settings.

        Returns:
            Dictionary of setting key -> {label, value}
        """
        return await self._read_editor_settings("H")

    async def get_general_settings_three(self) -> dict[str, Any]:
        """Read General Editor Three settings.

        Returns:
            Dictionary of setting key -> {label, value}
        """
        return await self._read_editor_settings("I")

    async def get_game_timing(self) -> dict[str, Any]:
        """Read Game Timing Editor settings.

        Returns:
            Dictionary of timing settings
        """
        return await self._read_editor_settings("Z")

    async def _read_editor_settings(self, editor_key: str) -> dict[str, Any]:
        """Read settings from a specific editor.

        Args:
            editor_key: Single character editor key (G, H, I, Z, etc.)

        Returns:
            Dictionary of parsed settings
        """
        # Enter the editor
        await self._send(editor_key)
        await asyncio.sleep(0.5)
        screen = await self._read_screen()
        self.current_editor = editor_key

        # Parse settings from screen
        settings = self._parse_settings_screen(screen)

        # Exit back to main TEDIT menu
        await self._send("Q")
        await asyncio.sleep(0.3)
        self.current_editor = None

        return settings

    async def set_setting(
        self,
        editor: str,
        key: str,
        value: str,
    ) -> bool:
        """Modify a setting in specified editor.

        Args:
            editor: Editor key (G, H, I, Z, etc.)
            key: Setting key within the editor
            value: New value to set

        Returns:
            True if setting was changed successfully
        """
        # Enter the editor
        await self._send(editor)
        await asyncio.sleep(0.5)

        # Send the setting key
        await self._send(key)
        await asyncio.sleep(0.3)

        # Send the new value with Enter
        await self._send(value + "\r")
        await asyncio.sleep(0.3)

        # Read result
        screen = await self._read_screen()

        # Exit editor
        await self._send("Q")
        await asyncio.sleep(0.3)
        self.current_editor = None

        return True

    async def list_users(self) -> list[dict[str, Any]]:
        """List all active users.

        Returns:
            List of user dictionaries with id, name, sector, fighters, etc.
        """
        # Enter User List (L from main TEDIT menu)
        await self._send("L")
        await asyncio.sleep(0.5)

        users: list[dict[str, Any]] = []
        screen = await self._read_screen()

        # Parse user lines
        for line in screen.splitlines():
            if match := _USER_LINE_PATTERN.match(line):
                users.append(
                    {
                        "id": int(match["id"]),
                        "name": match["name"],
                        "sector": int(match["sector"]),
                        "fighters": int(match["fighters"]),
                        "shields": int(match["shields"]),
                        "ship": match["ship"].strip(),
                        "turns": int(match["turns"]),
                        "corp": int(match["corp"]),
                    }
                )

        # Handle pagination if needed
        while "[more]" in screen.lower() or "press any key" in screen.lower():
            await self._send(" ")
            await asyncio.sleep(0.3)
            screen = await self._read_screen()

            for line in screen.splitlines():
                if match := _USER_LINE_PATTERN.match(line):
                    users.append(
                        {
                            "id": int(match["id"]),
                            "name": match["name"],
                            "sector": int(match["sector"]),
                            "fighters": int(match["fighters"]),
                            "shields": int(match["shields"]),
                            "ship": match["ship"].strip(),
                            "turns": int(match["turns"]),
                            "corp": int(match["corp"]),
                        }
                    )

        # Exit user list
        await self._send("Q")
        await asyncio.sleep(0.3)

        return users

    async def get_user(self, user_id: int) -> dict[str, Any]:
        """Get detailed user information.

        Args:
            user_id: Player ID number

        Returns:
            Dictionary with user details
        """
        # Enter User Editor
        await self._send("U")
        await asyncio.sleep(0.3)

        # Enter user ID
        await self._send(str(user_id) + "\r")
        await asyncio.sleep(0.5)

        screen = await self._read_screen()
        user = self._parse_settings_screen(screen)
        user["id"] = user_id

        # Exit user editor
        await self._send("Q")
        await asyncio.sleep(0.3)

        return user

    async def get_port(self, port_id: int) -> dict[str, Any]:
        """Get port information.

        Args:
            port_id: Port ID/sector number

        Returns:
            Dictionary with port details
        """
        # Enter Port Editor
        await self._send("P")
        await asyncio.sleep(0.3)

        # Enter port ID
        await self._send(str(port_id) + "\r")
        await asyncio.sleep(0.5)

        screen = await self._read_screen()
        port = self._parse_settings_screen(screen)
        port["id"] = port_id

        # Exit port editor
        await self._send("Q")
        await asyncio.sleep(0.3)

        return port

    async def get_sector(self, sector_id: int) -> dict[str, Any]:
        """Get sector information.

        Args:
            sector_id: Sector number

        Returns:
            Dictionary with sector details
        """
        # Enter Sector Editor
        await self._send("S")
        await asyncio.sleep(0.3)

        # Enter sector ID
        await self._send(str(sector_id) + "\r")
        await asyncio.sleep(0.5)

        screen = await self._read_screen()
        sector = self._parse_settings_screen(screen)
        sector["id"] = sector_id

        # Exit sector editor
        await self._send("Q")
        await asyncio.sleep(0.3)

        return sector

    def _parse_settings_screen(self, screen: str) -> dict[str, Any]:
        """Parse a TEDIT settings screen into a dictionary.

        Args:
            screen: Raw screen text

        Returns:
            Dictionary of parsed settings
        """
        settings: dict[str, Any] = {}

        for line in screen.splitlines():
            line = line.rstrip()
            if not line.strip():
                continue

            # Try field pattern with key: <K> Label: Value
            if match := _FIELD_PATTERN.search(line):
                key = match["key"].strip()
                label = match["label"].strip()
                value = match["value"].strip()

                # Use key if present, otherwise use label
                dict_key = key if key else self._normalize_label(label)
                settings[dict_key] = {
                    "key": key,
                    "label": label,
                    "value": value,
                }
                continue

            # Try simple key-value pattern: Label: Value
            if match := _SIMPLE_KV_PATTERN.search(line):
                label = match["label"].strip()
                value = match["value"].strip()
                dict_key = self._normalize_label(label)
                settings[dict_key] = {
                    "label": label,
                    "value": value,
                }

        return settings

    def _normalize_label(self, label: str) -> str:
        """Normalize a label into a dictionary key.

        Args:
            label: Human-readable label

        Returns:
            Normalized key (lowercase, underscores)
        """
        # Remove special characters, convert spaces to underscores
        key = re.sub(r"[^a-zA-Z0-9\s]", "", label)
        key = key.lower().strip()
        key = re.sub(r"\s+", "_", key)
        return key

    async def _send(self, keys: str) -> None:
        """Send keystrokes to the session.

        Args:
            keys: Keys to send
        """
        if self.session:
            await self.session.send(keys)

    async def _read_screen(self, timeout_ms: int = 500, max_bytes: int = 8192) -> str:
        """Read current screen content.

        Args:
            timeout_ms: Read timeout in milliseconds
            max_bytes: Maximum bytes to read

        Returns:
            Screen text content
        """
        if self.session:
            snapshot = await self.session.read(timeout_ms=timeout_ms, max_bytes=max_bytes)
            return snapshot.get("screen", "")
        return ""

    async def wait_for_prompt(
        self,
        timeout_ms: int = 5000,
        interval_ms: int = 250,
    ) -> tuple[str, str]:
        """Wait for a prompt to appear.

        Args:
            timeout_ms: Maximum wait time
            interval_ms: Polling interval

        Returns:
            Tuple of (screen_text, detected_prompt_id or "")
        """
        elapsed = 0
        while elapsed < timeout_ms:
            snapshot = await self.session.read(timeout_ms=interval_ms, max_bytes=8192)
            screen = snapshot.get("screen", "")

            if "prompt_detected" in snapshot:
                detected = snapshot["prompt_detected"]
                prompt_id = detected.get("prompt_id", "")
                is_idle = detected.get("is_idle", False)
                if is_idle:
                    return (screen, prompt_id)

            elapsed += interval_ms

        return (screen, "")

    def get_status(self) -> dict[str, Any]:
        """Get current manager status.

        Returns:
            Status dictionary
        """
        return {
            "connected": self.connected,
            "host": self.host,
            "port": self.port,
            "current_game": self.current_game,
            "current_editor": self.current_editor,
            "session_id": self.session_id,
        }
