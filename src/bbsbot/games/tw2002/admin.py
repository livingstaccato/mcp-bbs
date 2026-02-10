"""Unified admin interface for TW2002 - supports direct file access and remote terminal.

Two access methods:
- "direct": Uses twerk library for direct file access (local server, fastest, most precise)
- "remote": Uses MCP-BBS terminal automation (remote servers, legacy systems)
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, PrivateAttr

if TYPE_CHECKING:
    from twerk.parsers import PlayerRecord, PortRecord, SectorRecord


class TW2002Admin(BaseModel):
    """Unified admin interface - uses twerk (direct) or MCP-BBS (remote).

    Examples:
        # Direct file access (local server)
        admin = TW2002Admin(mode="direct", data_dir=Path("/path/to/tw2002/data"))
        config = await admin.get_config()
        players = await admin.list_players()

        # Remote terminal access
        admin = TW2002Admin(mode="remote")
        await admin.connect(host="localhost", port=2003, password="admin")
        config = await admin.get_config()
    """

    mode: str = "direct"  # "direct" (twerk) or "remote" (MCP-BBS terminal)
    data_dir: Path | None = None

    # Remote mode connection settings
    host: str = "localhost"
    port: int = 2003
    password: str = "admin"

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="ignore")

    _tedit_manager: Any = PrivateAttr(default=None)
    _connected: bool = PrivateAttr(default=False)

    def model_post_init(self, __context: Any) -> None:
        """Validate configuration."""
        if self.mode not in ("direct", "remote"):
            raise ValueError(f"mode must be 'direct' or 'remote', got '{self.mode}'")

        if self.mode == "direct" and self.data_dir is None:
            raise ValueError("data_dir is required for direct mode")

    # -------------------------------------------------------------------------
    # Connection management (remote mode only)
    # -------------------------------------------------------------------------

    async def connect(
        self,
        host: str | None = None,
        port: int | None = None,
        password: str | None = None,
        game_id: str = "A",
    ) -> bool:
        """Connect to TEDIT admin interface (remote mode only).

        Args:
            host: Override default host
            port: Override default port
            password: Override default password
            game_id: Game slot to manage (A or B)

        Returns:
            True if connection successful
        """
        if self.mode == "direct":
            # Direct mode doesn't need connection
            self._connected = True
            return True

        # Import TEDITManager for remote mode
        from games.tw2002.tedit_manager import TEDITManager

        if host:
            self.host = host
        if port:
            self.port = port
        if password:
            self.password = password

        self._tedit_manager = TEDITManager(
            host=self.host,
            port=self.port,
            password=self.password,
        )

        await self._tedit_manager.connect()
        await self._tedit_manager.enter_tedit(game_id)
        self._connected = True
        return True

    async def disconnect(self) -> None:
        """Disconnect from TEDIT (remote mode only)."""
        if self._tedit_manager:
            await self._tedit_manager.exit_tedit()
            await self._tedit_manager.disconnect()
            self._tedit_manager = None
        self._connected = False

    # -------------------------------------------------------------------------
    # Config operations
    # -------------------------------------------------------------------------

    async def get_config(self) -> dict[str, Any]:
        """Get game configuration.

        Returns:
            Dictionary of configuration values
        """
        if self.mode == "direct":
            return await self._get_config_direct()
        return await self._get_config_remote()

    async def _get_config_direct(self) -> dict[str, Any]:
        """Read config from twcfig.dat using twerk."""
        from twerk.parsers import parse_config

        config_path = self.data_dir / "twcfig.dat"  # type: ignore[operator]
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        config = parse_config(config_path)
        return {
            "game_title": config.game_title,
            "header_values": config.header_values,
            "turns_per_day": config.header_values[0] if len(config.header_values) > 0 else 0,
            "initial_fighters": config.header_values[1] if len(config.header_values) > 1 else 0,
            "initial_credits": config.header_values[2] if len(config.header_values) > 2 else 0,
            "initial_holds": config.header_values[3] if len(config.header_values) > 3 else 0,
            "_raw": config,
        }

    async def _get_config_remote(self) -> dict[str, Any]:
        """Read config via TEDIT terminal."""
        if not self._tedit_manager:
            raise RuntimeError("Not connected - call connect() first")

        # Aggregate settings from all general editors
        settings: dict[str, Any] = {}
        settings["general_one"] = await self._tedit_manager.get_general_settings_one()
        settings["general_two"] = await self._tedit_manager.get_general_settings_two()
        settings["general_three"] = await self._tedit_manager.get_general_settings_three()
        settings["game_timing"] = await self._tedit_manager.get_game_timing()
        return settings

    async def set_config(self, **settings: Any) -> None:
        """Update game configuration.

        Args:
            **settings: Configuration values to update
        """
        if self.mode == "direct":
            await self._set_config_direct(settings)
        else:
            await self._set_config_remote(settings)

    async def _set_config_direct(self, settings: dict[str, Any]) -> None:
        """Write config to twcfig.dat using twerk."""
        from twerk.parsers import parse_config, write_config

        config_path = self.data_dir / "twcfig.dat"  # type: ignore[operator]
        config = parse_config(config_path)

        # Apply settings to header values
        if "turns_per_day" in settings and len(config.header_values) > 0:
            config.header_values[0] = settings["turns_per_day"]
        if "initial_fighters" in settings and len(config.header_values) > 1:
            config.header_values[1] = settings["initial_fighters"]
        if "initial_credits" in settings and len(config.header_values) > 2:
            config.header_values[2] = settings["initial_credits"]
        if "initial_holds" in settings and len(config.header_values) > 3:
            config.header_values[3] = settings["initial_holds"]
        if "game_title" in settings:
            config.game_title = settings["game_title"]

        write_config(config, config_path)

    async def _set_config_remote(self, settings: dict[str, Any]) -> None:
        """Update config via TEDIT terminal."""
        if not self._tedit_manager:
            raise RuntimeError("Not connected - call connect() first")

        # Map common setting names to TEDIT editor/key pairs
        setting_map = {
            "turns_per_day": ("G", "A"),  # General Editor One, key A
            "initial_fighters": ("G", "B"),
            "initial_credits": ("G", "C"),
            "initial_holds": ("G", "D"),
        }

        for name, value in settings.items():
            if name in setting_map:
                editor, key = setting_map[name]
                await self._tedit_manager.set_setting(editor, key, str(value))

    # -------------------------------------------------------------------------
    # Player operations
    # -------------------------------------------------------------------------

    async def list_players(self) -> list[PlayerRecord]:
        """List all players.

        Returns:
            List of PlayerRecord objects (direct mode) or dicts (remote mode)
        """
        if self.mode == "direct":
            return await self._list_players_direct()
        return await self._list_players_remote()  # type: ignore[return-value]

    async def _list_players_direct(self) -> list[PlayerRecord]:
        """Read players from twuser.dat using twerk."""
        from twerk.parsers import parse_players

        players_path = self.data_dir / "twuser.dat"  # type: ignore[operator]
        if not players_path.exists():
            return []

        players, _header = parse_players(players_path)
        # Filter out deleted/empty player slots
        return [p for p in players if p.name and p.name.strip()]

    async def _list_players_remote(self) -> list[dict[str, Any]]:
        """List players via TEDIT terminal."""
        if not self._tedit_manager:
            raise RuntimeError("Not connected - call connect() first")

        return await self._tedit_manager.list_users()

    async def get_player(self, player_id: int) -> PlayerRecord | dict[str, Any]:
        """Get detailed player information.

        Args:
            player_id: Player ID number

        Returns:
            PlayerRecord (direct mode) or dict (remote mode)
        """
        if self.mode == "direct":
            return await self._get_player_direct(player_id)
        return await self._get_player_remote(player_id)

    async def _get_player_direct(self, player_id: int) -> PlayerRecord:
        """Read player from twuser.dat using twerk."""
        from twerk.parsers import parse_players

        players_path = self.data_dir / "twuser.dat"  # type: ignore[operator]
        players, _header = parse_players(players_path)

        for p in players:
            if p.player_id == player_id:
                return p

        raise ValueError(f"Player {player_id} not found")

    async def _get_player_remote(self, player_id: int) -> dict[str, Any]:
        """Get player via TEDIT terminal."""
        if not self._tedit_manager:
            raise RuntimeError("Not connected - call connect() first")

        return await self._tedit_manager.get_user(player_id)

    async def edit_player(self, player_id: int, **fields: Any) -> None:
        """Modify player fields.

        Args:
            player_id: Player ID to edit
            **fields: Fields to update (credits, turns, sector, etc.)
        """
        if self.mode == "direct":
            await self._edit_player_direct(player_id, fields)
        else:
            await self._edit_player_remote(player_id, fields)

    async def _edit_player_direct(self, player_id: int, fields: dict[str, Any]) -> None:
        """Edit player in twuser.dat using twerk."""
        from twerk.parsers import parse_players, write_players

        players_path = self.data_dir / "twuser.dat"  # type: ignore[operator]
        players, header = parse_players(players_path)

        for p in players:
            if p.player_id == player_id:
                # Apply field updates
                for key, value in fields.items():
                    if hasattr(p, key):
                        setattr(p, key, value)
                write_players((players, header), players_path)
                return

        raise ValueError(f"Player {player_id} not found")

    async def _edit_player_remote(self, player_id: int, fields: dict[str, Any]) -> None:
        """Edit player via TEDIT terminal.

        Note: Remote editing has limited field support.
        """
        if not self._tedit_manager:
            raise RuntimeError("Not connected - call connect() first")

        # Navigate to user editor
        await self._tedit_manager._send("U")
        await self._tedit_manager._send(str(player_id) + "\r")

        # Map field names to TEDIT keys (limited support)
        field_map = {
            "credits": "C",
            "turns": "T",
            "sector": "S",
        }

        for key, value in fields.items():
            if key in field_map:
                await self._tedit_manager._send(field_map[key])
                await self._tedit_manager._send(str(value) + "\r")

        await self._tedit_manager._send("Q")

    # -------------------------------------------------------------------------
    # Port operations
    # -------------------------------------------------------------------------

    async def list_ports(self) -> list[PortRecord]:
        """List all ports.

        Returns:
            List of PortRecord objects (direct mode) or dicts (remote mode)
        """
        if self.mode == "direct":
            return await self._list_ports_direct()
        # Remote mode doesn't support listing all ports efficiently
        raise NotImplementedError("Remote mode doesn't support listing all ports")

    async def _list_ports_direct(self) -> list[PortRecord]:
        """Read ports from twport.dat using twerk."""
        from twerk.parsers import parse_ports

        ports_path = self.data_dir / "twport.dat"  # type: ignore[operator]
        if not ports_path.exists():
            return []

        ports = parse_ports(ports_path)
        # Filter out empty port slots
        return [p for p in ports if p.sector_id > 0]

    async def get_port(self, sector: int) -> PortRecord | dict[str, Any]:
        """Get port information for a sector.

        Args:
            sector: Sector number containing the port

        Returns:
            PortRecord (direct mode) or dict (remote mode)
        """
        if self.mode == "direct":
            return await self._get_port_direct(sector)
        return await self._get_port_remote(sector)

    async def _get_port_direct(self, sector: int) -> PortRecord:
        """Read port from twport.dat using twerk."""
        from twerk.parsers import parse_ports

        ports_path = self.data_dir / "twport.dat"  # type: ignore[operator]
        ports = parse_ports(ports_path)

        for p in ports:
            if p.sector_id == sector:
                return p

        raise ValueError(f"No port found in sector {sector}")

    async def _get_port_remote(self, sector: int) -> dict[str, Any]:
        """Get port via TEDIT terminal."""
        if not self._tedit_manager:
            raise RuntimeError("Not connected - call connect() first")

        return await self._tedit_manager.get_port(sector)

    # -------------------------------------------------------------------------
    # Sector operations
    # -------------------------------------------------------------------------

    async def list_sectors(self) -> list[SectorRecord]:
        """List all sectors.

        Returns:
            List of SectorRecord objects (direct mode only)
        """
        if self.mode == "direct":
            return await self._list_sectors_direct()
        raise NotImplementedError("Remote mode doesn't support listing all sectors")

    async def _list_sectors_direct(self) -> list[SectorRecord]:
        """Read sectors from twsect.dat using twerk."""
        from twerk.parsers import parse_sectors

        sectors_path = self.data_dir / "twsect.dat"  # type: ignore[operator]
        if not sectors_path.exists():
            return []

        return parse_sectors(sectors_path)

    async def get_sector(self, sector_id: int) -> SectorRecord | dict[str, Any]:
        """Get sector information.

        Args:
            sector_id: Sector number

        Returns:
            SectorRecord (direct mode) or dict (remote mode)
        """
        if self.mode == "direct":
            return await self._get_sector_direct(sector_id)
        return await self._get_sector_remote(sector_id)

    async def _get_sector_direct(self, sector_id: int) -> SectorRecord:
        """Read sector from twsect.dat using twerk."""
        from twerk.parsers import parse_sectors

        sectors_path = self.data_dir / "twsect.dat"  # type: ignore[operator]
        sectors = parse_sectors(sectors_path)

        # Sectors are typically 1-indexed
        if 1 <= sector_id <= len(sectors):
            return sectors[sector_id - 1]

        raise ValueError(f"Sector {sector_id} not found")

    async def _get_sector_remote(self, sector_id: int) -> dict[str, Any]:
        """Get sector via TEDIT terminal."""
        if not self._tedit_manager:
            raise RuntimeError("Not connected - call connect() first")

        return await self._tedit_manager.get_sector(sector_id)

    async def get_warps(self, sector_id: int) -> list[int]:
        """Get warp connections from a sector.

        Args:
            sector_id: Sector number

        Returns:
            List of connected sector IDs
        """
        sector = await self.get_sector(sector_id)

        if self.mode == "direct":
            # Direct mode returns SectorRecord with warps list
            return [w for w in sector.warps if w > 0]  # type: ignore[union-attr]

        # Remote mode returns dict
        warps_raw = sector.get("warps", [])  # type: ignore[union-attr]
        if isinstance(warps_raw, dict):
            return [int(v.get("value", 0)) for v in warps_raw.values() if v.get("value")]
        return warps_raw

    # -------------------------------------------------------------------------
    # Status and utilities
    # -------------------------------------------------------------------------

    def get_status(self) -> dict[str, Any]:
        """Get current admin interface status.

        Returns:
            Status dictionary
        """
        status: dict[str, Any] = {
            "mode": self.mode,
            "connected": self._connected,
        }

        if self.mode == "direct":
            status["data_dir"] = str(self.data_dir)
        else:
            status["host"] = self.host
            status["port"] = self.port
            if self._tedit_manager:
                status["tedit_status"] = self._tedit_manager.get_status()

        return status

    async def __aenter__(self) -> TW2002Admin:
        """Async context manager entry."""
        if self.mode == "remote":
            await self.connect()
        else:
            self._connected = True
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.disconnect()
