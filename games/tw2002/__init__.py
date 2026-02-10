"""TW2002 game utilities and TEDIT integration.

This package provides tools for interacting with Trade Wars 2002 via MCP-BBS,
including TEDIT (Sysop Editor) automation and game settings management.

Two access methods are supported:
- Direct file access via twerk library (for local servers)
- Terminal automation via MCP-BBS (for remote/legacy servers)

Modules:
    tedit_manager: High-level session management for TEDIT
    settings_diff: Compare settings between games or baselines
    data_mapper: Map TEDIT settings to underlying data files
"""

from .data_mapper import (
    FIELD_MAPPINGS,
    DataFileType,
    FieldMapping,
    format_data_file_summary,
    get_affected_files,
    get_file_info,
    get_mapping,
    get_mappings_by_editor,
    get_mappings_by_file,
)
from .settings_diff import (
    DEFAULT_BASELINE,
    DiffReport,
    SettingDiff,
    diff_from_baseline,
    diff_from_files,
    diff_games,
    diff_settings,
    format_diff_report,
    quick_diff_from_defaults,
)
from .tedit_manager import TEDITManager

# Import TW2002Admin from bbsbot.tw2002 for unified admin access
try:
    from bbsbot.tw2002.admin import TW2002Admin
except ImportError:
    # twbot may not be installed in all environments
    TW2002Admin = None  # type: ignore[misc, assignment]

__all__ = [
    # Unified Admin Interface
    "TW2002Admin",
    # TEDIT Manager
    "TEDITManager",
    # Settings Diff
    "diff_games",
    "diff_from_baseline",
    "diff_from_files",
    "diff_settings",
    "format_diff_report",
    "DiffReport",
    "SettingDiff",
    "DEFAULT_BASELINE",
    "quick_diff_from_defaults",
    # Data Mapper
    "DataFileType",
    "FieldMapping",
    "FIELD_MAPPINGS",
    "get_mappings_by_editor",
    "get_mappings_by_file",
    "get_mapping",
    "get_affected_files",
    "format_data_file_summary",
    "get_file_info",
]
