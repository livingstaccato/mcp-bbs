"""Data file mapper for TW2002.

Maps the relationship between TEDIT settings and underlying data files.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class DataFileType(Enum):
    """TW2002 data file types."""

    GAME = "game.dat"
    TEDIT = "tedit.dat"
    USER = "user.dat"
    PORT = "port.dat"
    SECTOR = "sector.dat"
    PLANET = "planet.dat"
    CORP = "corp.dat"
    SHIP = "ship.dat"
    ALIEN = "alien.dat"
    FERRENGI = "ferrengi.dat"


@dataclass
class FieldMapping:
    """Maps a TEDIT field to its data file location."""

    tedit_editor: str  # Editor key (G, H, I, etc.)
    tedit_key: str  # Field key within editor
    label: str  # Human-readable label
    data_file: DataFileType  # Primary data file
    offset: int | None = None  # Byte offset if known
    size: int | None = None  # Field size in bytes if known
    data_type: str = "string"  # int, string, bool, etc.
    notes: str = ""


# Known mappings between TEDIT fields and data files
FIELD_MAPPINGS: list[FieldMapping] = [
    # General Editor One (G) - Core Settings
    FieldMapping(
        tedit_editor="G",
        tedit_key="A",
        label="Turns per day",
        data_file=DataFileType.GAME,
        data_type="int",
        notes="Daily turn allocation per player",
    ),
    FieldMapping(
        tedit_editor="G",
        tedit_key="B",
        label="Initial fighters",
        data_file=DataFileType.GAME,
        data_type="int",
        notes="Starting fighters for new players",
    ),
    FieldMapping(
        tedit_editor="G",
        tedit_key="C",
        label="Initial credits",
        data_file=DataFileType.GAME,
        data_type="int",
        notes="Starting credits for new players",
    ),
    FieldMapping(
        tedit_editor="G",
        tedit_key="D",
        label="Initial holds",
        data_file=DataFileType.GAME,
        data_type="int",
        notes="Starting cargo holds for new players",
    ),
    FieldMapping(
        tedit_editor="G",
        tedit_key="E",
        label="Days until inactive deleted",
        data_file=DataFileType.GAME,
        data_type="int",
        notes="Cleanup inactive players after N days",
    ),
    FieldMapping(
        tedit_editor="G",
        tedit_key="G",
        label="Ferrengi regeneration %",
        data_file=DataFileType.FERRENGI,
        data_type="int",
        notes="Ferrengi respawn rate percentage",
    ),
    FieldMapping(
        tedit_editor="G",
        tedit_key="H",
        label="Colonist reproduction rate",
        data_file=DataFileType.PLANET,
        data_type="int",
        notes="Daily colonist growth rate",
    ),
    FieldMapping(
        tedit_editor="G",
        tedit_key="I",
        label="Daily log limit",
        data_file=DataFileType.GAME,
        data_type="int",
        notes="Maximum log entries per day",
    ),
    FieldMapping(
        tedit_editor="G",
        tedit_key="J",
        label="StarShip Intrepid location",
        data_file=DataFileType.SHIP,
        data_type="int",
        notes="Sector location of special ship",
    ),
    FieldMapping(
        tedit_editor="G",
        tedit_key="K",
        label="StarShip Valiant location",
        data_file=DataFileType.SHIP,
        data_type="int",
        notes="Sector location of special ship",
    ),
    FieldMapping(
        tedit_editor="G",
        tedit_key="L",
        label="StarShip Lexington location",
        data_file=DataFileType.SHIP,
        data_type="int",
        notes="Sector location of special ship",
    ),
    FieldMapping(
        tedit_editor="G",
        tedit_key="M",
        label="Max planets per sector",
        data_file=DataFileType.SECTOR,
        data_type="int",
        notes="Planet density limit per sector",
    ),
    FieldMapping(
        tedit_editor="G",
        tedit_key="N",
        label="Max traders per corp",
        data_file=DataFileType.CORP,
        data_type="int",
        notes="Maximum corporation size",
    ),
    FieldMapping(
        tedit_editor="G",
        tedit_key="O",
        label="Underground password",
        data_file=DataFileType.GAME,
        data_type="string",
        notes="Secret phrase for Underground access",
    ),
    FieldMapping(
        tedit_editor="G",
        tedit_key="P",
        label="Age of game (days)",
        data_file=DataFileType.GAME,
        data_type="int",
        notes="Game duration in days",
    ),
    FieldMapping(
        tedit_editor="G",
        tedit_key="R",
        label="Tournament mode",
        data_file=DataFileType.GAME,
        data_type="bool",
        notes="Tournament competition mode toggle",
    ),
    # General Editor Two (H) - Advanced Settings
    FieldMapping(
        tedit_editor="H",
        tedit_key="1",
        label="Allow MBBS MegaRob Bug",
        data_file=DataFileType.TEDIT,
        data_type="bool",
    ),
    FieldMapping(
        tedit_editor="H",
        tedit_key="2",
        label="Inactivity Timeout",
        data_file=DataFileType.GAME,
        data_type="int",
        notes="Seconds before auto-disconnect",
    ),
    FieldMapping(
        tedit_editor="H",
        tedit_key="3",
        label="Steal from Buy Port?",
        data_file=DataFileType.TEDIT,
        data_type="bool",
    ),
    FieldMapping(
        tedit_editor="H",
        tedit_key="7",
        label="Port Regeneration Rate",
        data_file=DataFileType.PORT,
        data_type="int",
        notes="Daily port stock regeneration percentage",
    ),
    FieldMapping(
        tedit_editor="H",
        tedit_key="8",
        label="Max Regen Per Visit",
        data_file=DataFileType.PORT,
        data_type="int",
        notes="Maximum regeneration per visit percentage",
    ),
    FieldMapping(
        tedit_editor="H",
        tedit_key="[",
        label="Closed Game",
        data_file=DataFileType.GAME,
        data_type="bool",
        notes="Prevent new player registration",
    ),
    FieldMapping(
        tedit_editor="H",
        tedit_key="]",
        label="Password Required",
        data_file=DataFileType.GAME,
        data_type="bool",
        notes="Require password for game entry",
    ),
    FieldMapping(
        tedit_editor="H",
        tedit_key="T",
        label="Max Bank Credits",
        data_file=DataFileType.GAME,
        data_type="int",
        notes="Maximum credits in bank",
    ),
    FieldMapping(
        tedit_editor="H",
        tedit_key="U",
        label="Cloaking Fail Rate",
        data_file=DataFileType.SHIP,
        data_type="int",
        notes="Percentage chance of cloak failure",
    ),
    FieldMapping(
        tedit_editor="H",
        tedit_key="V",
        label="NavHaz Dispersion",
        data_file=DataFileType.SECTOR,
        data_type="int",
        notes="Daily navigation hazard reduction",
    ),
    # User data mappings
    FieldMapping(
        tedit_editor="U",
        tedit_key="A",
        label="Player Name",
        data_file=DataFileType.USER,
        data_type="string",
    ),
    FieldMapping(
        tedit_editor="U",
        tedit_key="B",
        label="Password",
        data_file=DataFileType.USER,
        data_type="string",
    ),
    FieldMapping(
        tedit_editor="U",
        tedit_key="C",
        label="Sector Location",
        data_file=DataFileType.USER,
        data_type="int",
    ),
    FieldMapping(
        tedit_editor="U",
        tedit_key="D",
        label="Fighters",
        data_file=DataFileType.USER,
        data_type="int",
    ),
    FieldMapping(
        tedit_editor="U",
        tedit_key="E",
        label="Shields",
        data_file=DataFileType.USER,
        data_type="int",
    ),
    FieldMapping(
        tedit_editor="U",
        tedit_key="F",
        label="Holds",
        data_file=DataFileType.USER,
        data_type="int",
    ),
    FieldMapping(
        tedit_editor="U",
        tedit_key="G",
        label="Credits",
        data_file=DataFileType.USER,
        data_type="int",
    ),
    FieldMapping(
        tedit_editor="U",
        tedit_key="I",
        label="Turns",
        data_file=DataFileType.USER,
        data_type="int",
    ),
    FieldMapping(
        tedit_editor="U",
        tedit_key="J",
        label="Experience",
        data_file=DataFileType.USER,
        data_type="int",
    ),
    FieldMapping(
        tedit_editor="U",
        tedit_key="K",
        label="Alignment",
        data_file=DataFileType.USER,
        data_type="int",
    ),
    # Port data mappings
    FieldMapping(
        tedit_editor="P",
        tedit_key="A",
        label="Port Class",
        data_file=DataFileType.PORT,
        data_type="int",
        notes="Port trading class (1-8)",
    ),
    FieldMapping(
        tedit_editor="P",
        tedit_key="B",
        label="Fuel Ore Amount",
        data_file=DataFileType.PORT,
        data_type="int",
    ),
    FieldMapping(
        tedit_editor="P",
        tedit_key="C",
        label="Organics Amount",
        data_file=DataFileType.PORT,
        data_type="int",
    ),
    FieldMapping(
        tedit_editor="P",
        tedit_key="D",
        label="Equipment Amount",
        data_file=DataFileType.PORT,
        data_type="int",
    ),
    # Sector data mappings
    FieldMapping(
        tedit_editor="S",
        tedit_key="A",
        label="Warp 1",
        data_file=DataFileType.SECTOR,
        data_type="int",
        notes="First warp connection",
    ),
    FieldMapping(
        tedit_editor="S",
        tedit_key="B",
        label="Warp 2",
        data_file=DataFileType.SECTOR,
        data_type="int",
    ),
    FieldMapping(
        tedit_editor="S",
        tedit_key="C",
        label="Warp 3",
        data_file=DataFileType.SECTOR,
        data_type="int",
    ),
    FieldMapping(
        tedit_editor="S",
        tedit_key="D",
        label="Warp 4",
        data_file=DataFileType.SECTOR,
        data_type="int",
    ),
    FieldMapping(
        tedit_editor="S",
        tedit_key="E",
        label="Warp 5",
        data_file=DataFileType.SECTOR,
        data_type="int",
    ),
    FieldMapping(
        tedit_editor="S",
        tedit_key="F",
        label="Warp 6",
        data_file=DataFileType.SECTOR,
        data_type="int",
    ),
    FieldMapping(
        tedit_editor="S",
        tedit_key="N",
        label="NavHaz Level",
        data_file=DataFileType.SECTOR,
        data_type="int",
        notes="Navigation hazard percentage",
    ),
]


def get_mappings_by_editor(editor: str) -> list[FieldMapping]:
    """Get all field mappings for a specific editor.

    Args:
        editor: Editor key (G, H, I, U, P, S, etc.)

    Returns:
        List of FieldMapping objects for that editor
    """
    return [m for m in FIELD_MAPPINGS if m.tedit_editor == editor]


def get_mappings_by_file(data_file: DataFileType) -> list[FieldMapping]:
    """Get all field mappings that affect a specific data file.

    Args:
        data_file: DataFileType enum value

    Returns:
        List of FieldMapping objects that modify that file
    """
    return [m for m in FIELD_MAPPINGS if m.data_file == data_file]


def get_mapping(editor: str, key: str) -> FieldMapping | None:
    """Get specific field mapping.

    Args:
        editor: Editor key
        key: Field key within editor

    Returns:
        FieldMapping or None if not found
    """
    for mapping in FIELD_MAPPINGS:
        if mapping.tedit_editor == editor and mapping.tedit_key == key:
            return mapping
    return None


def get_affected_files(settings: dict[str, Any]) -> set[DataFileType]:
    """Determine which data files would be affected by a set of settings changes.

    Args:
        settings: Dictionary of editor -> {key -> value} changes

    Returns:
        Set of DataFileType values that would be modified
    """
    affected: set[DataFileType] = set()

    for editor, fields in settings.items():
        if isinstance(fields, dict):
            for key in fields.keys():
                mapping = get_mapping(editor, key)
                if mapping:
                    affected.add(mapping.data_file)

    return affected


def format_data_file_summary() -> str:
    """Generate a summary of all data file mappings.

    Returns:
        Formatted string describing data file relationships
    """
    lines: list[str] = []
    lines.append("TW2002 Data File Mappings")
    lines.append("=" * 50)
    lines.append("")

    for file_type in DataFileType:
        mappings = get_mappings_by_file(file_type)
        if mappings:
            lines.append(f"## {file_type.value}")
            lines.append("-" * 30)
            for m in mappings:
                notes = f" - {m.notes}" if m.notes else ""
                lines.append(f"  [{m.tedit_editor}:{m.tedit_key}] {m.label}{notes}")
            lines.append("")

    return "\n".join(lines)


# File structure documentation
DATA_FILE_STRUCTURE: dict[str, dict[str, Any]] = {
    "game.dat": {
        "description": "Core game configuration and limits",
        "contents": [
            "Turn allocation settings",
            "Initial player resources",
            "Game age and duration",
            "Password settings",
            "Bank limits",
            "Timeout values",
        ],
    },
    "tedit.dat": {
        "description": "TEDIT-specific configuration flags",
        "contents": [
            "Bug compatibility flags",
            "Advanced game options",
            "Expert mode settings",
        ],
    },
    "user.dat": {
        "description": "Player account data",
        "contents": [
            "Player names and passwords",
            "Ship location (sector)",
            "Resources (credits, fighters, shields)",
            "Cargo holds and contents",
            "Experience and alignment",
            "Corporation membership",
        ],
    },
    "port.dat": {
        "description": "Trading port data",
        "contents": [
            "Port class and type",
            "Commodity levels (Fuel, Organics, Equipment)",
            "Price multipliers",
            "Regeneration state",
        ],
    },
    "sector.dat": {
        "description": "Sector map and connections",
        "contents": [
            "Warp connections (up to 6 per sector)",
            "Navigation hazard levels",
            "FedSpace designation",
            "Beacon messages",
        ],
    },
    "planet.dat": {
        "description": "Planet ownership and resources",
        "contents": [
            "Planet names",
            "Owner (player/corp)",
            "Colonist population",
            "Resource production",
            "Defensive structures",
        ],
    },
    "corp.dat": {
        "description": "Corporation data",
        "contents": [
            "Corporation names",
            "Member lists",
            "Treasury",
            "Alliance status",
        ],
    },
    "ship.dat": {
        "description": "Ship type definitions",
        "contents": [
            "Ship names and stats",
            "Hold capacity",
            "Fighter/shield limits",
            "Special ability flags",
            "Special ship locations (Intrepid, Valiant, Lexington)",
        ],
    },
    "alien.dat": {
        "description": "Alien NPC data",
        "contents": [
            "Alien names and menace levels",
            "Ship types and equipment",
            "Patrol sectors",
            "Attack behavior",
        ],
    },
    "ferrengi.dat": {
        "description": "Ferrengi trader data",
        "contents": [
            "Ferrengi ship locations",
            "Regeneration state",
            "Movement patterns",
        ],
    },
}


def get_file_info(filename: str) -> dict[str, Any] | None:
    """Get documentation about a data file.

    Args:
        filename: Data file name (e.g., "user.dat")

    Returns:
        Dictionary with description and contents, or None
    """
    return DATA_FILE_STRUCTURE.get(filename)
