"""TW2002 game utilities and TEDIT integration.

This package provides tools for interacting with Trade Wars 2002 via MCP-BBS,
including TEDIT (Sysop Editor) automation and game settings management.

Modules:
    tedit_manager: High-level session management for TEDIT
    settings_diff: Compare settings between games or baselines
    data_mapper: Map TEDIT settings to underlying data files
"""

from .tedit_manager import TEDITManager
from .settings_diff import (
    diff_games,
    diff_from_baseline,
    diff_settings,
    format_diff_report,
    DiffReport,
    SettingDiff,
    DEFAULT_BASELINE,
    quick_diff_from_defaults,
)
from .data_mapper import (
    DataFileType,
    FieldMapping,
    FIELD_MAPPINGS,
    get_mappings_by_editor,
    get_mappings_by_file,
    get_mapping,
    get_affected_files,
    format_data_file_summary,
    get_file_info,
)

__all__ = [
    # TEDIT Manager
    "TEDITManager",
    # Settings Diff
    "diff_games",
    "diff_from_baseline",
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
