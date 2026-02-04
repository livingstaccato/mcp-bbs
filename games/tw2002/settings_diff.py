"""Settings diff tool for comparing TW2002 game configurations.

Compare settings between two game instances or between current and baseline.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .tedit_manager import TEDITManager


@dataclass
class SettingDiff:
    """Represents a difference in a single setting."""

    key: str
    label: str
    value_a: str | None
    value_b: str | None
    changed: bool

    @property
    def diff_type(self) -> str:
        """Return type of difference."""
        if self.value_a is None:
            return "added"
        elif self.value_b is None:
            return "removed"
        elif self.changed:
            return "modified"
        return "unchanged"


@dataclass
class DiffReport:
    """Complete diff report between two configurations."""

    source_a: str
    source_b: str
    general_one: list[SettingDiff]
    general_two: list[SettingDiff]
    general_three: list[SettingDiff]
    game_timing: list[SettingDiff]

    @property
    def total_changes(self) -> int:
        """Count total number of changed settings."""
        return sum(
            1
            for diff in (
                self.general_one + self.general_two + self.general_three + self.game_timing
            )
            if diff.changed
        )

    @property
    def has_changes(self) -> bool:
        """Return True if any settings differ."""
        return self.total_changes > 0


def diff_settings(
    settings_a: dict[str, Any],
    settings_b: dict[str, Any],
) -> list[SettingDiff]:
    """Compare two settings dictionaries.

    Args:
        settings_a: First settings dictionary
        settings_b: Second settings dictionary

    Returns:
        List of SettingDiff objects
    """
    diffs: list[SettingDiff] = []
    all_keys = set(settings_a.keys()) | set(settings_b.keys())

    for key in sorted(all_keys):
        a = settings_a.get(key, {})
        b = settings_b.get(key, {})

        value_a = a.get("value") if isinstance(a, dict) else None
        value_b = b.get("value") if isinstance(b, dict) else None
        label = a.get("label", "") if isinstance(a, dict) else (
            b.get("label", "") if isinstance(b, dict) else key
        )

        changed = value_a != value_b and not (value_a is None and value_b is None)

        diffs.append(SettingDiff(
            key=key,
            label=label,
            value_a=value_a,
            value_b=value_b,
            changed=changed,
        ))

    return diffs


async def diff_games(
    game_a: str,
    game_b: str,
    host: str = "localhost",
    port: int = 2003,
    password: str = "admin",
) -> DiffReport:
    """Compare settings between two games.

    Args:
        game_a: First game slot (e.g., "A")
        game_b: Second game slot (e.g., "B")
        host: TEDIT host
        port: TEDIT port
        password: Admin password

    Returns:
        DiffReport with all setting differences
    """
    manager = TEDITManager(host=host, port=port, password=password)

    try:
        await manager.connect()

        # Read settings from game A
        await manager.enter_tedit(game_a)
        settings_a = {
            "general_one": await manager.get_general_settings_one(),
            "general_two": await manager.get_general_settings_two(),
            "general_three": await manager.get_general_settings_three(),
            "game_timing": await manager.get_game_timing(),
        }
        await manager.exit_tedit()

        # Read settings from game B
        await manager.enter_tedit(game_b)
        settings_b = {
            "general_one": await manager.get_general_settings_one(),
            "general_two": await manager.get_general_settings_two(),
            "general_three": await manager.get_general_settings_three(),
            "game_timing": await manager.get_game_timing(),
        }
        await manager.exit_tedit()

        return DiffReport(
            source_a=f"Game {game_a}",
            source_b=f"Game {game_b}",
            general_one=diff_settings(
                settings_a["general_one"],
                settings_b["general_one"],
            ),
            general_two=diff_settings(
                settings_a["general_two"],
                settings_b["general_two"],
            ),
            general_three=diff_settings(
                settings_a["general_three"],
                settings_b["general_three"],
            ),
            game_timing=diff_settings(
                settings_a["game_timing"],
                settings_b["game_timing"],
            ),
        )

    finally:
        await manager.disconnect()


async def diff_from_baseline(
    game: str,
    baseline: dict[str, dict[str, Any]],
    host: str = "localhost",
    port: int = 2003,
    password: str = "admin",
) -> DiffReport:
    """Compare current settings against a known baseline.

    Args:
        game: Game slot to compare
        baseline: Baseline settings dictionary with keys:
            general_one, general_two, general_three, game_timing
        host: TEDIT host
        port: TEDIT port
        password: Admin password

    Returns:
        DiffReport comparing current to baseline
    """
    manager = TEDITManager(host=host, port=port, password=password)

    try:
        await manager.connect()
        await manager.enter_tedit(game)

        current = {
            "general_one": await manager.get_general_settings_one(),
            "general_two": await manager.get_general_settings_two(),
            "general_three": await manager.get_general_settings_three(),
            "game_timing": await manager.get_game_timing(),
        }

        await manager.exit_tedit()

        return DiffReport(
            source_a="Baseline",
            source_b=f"Game {game}",
            general_one=diff_settings(
                baseline.get("general_one", {}),
                current["general_one"],
            ),
            general_two=diff_settings(
                baseline.get("general_two", {}),
                current["general_two"],
            ),
            general_three=diff_settings(
                baseline.get("general_three", {}),
                current["general_three"],
            ),
            game_timing=diff_settings(
                baseline.get("game_timing", {}),
                current["game_timing"],
            ),
        )

    finally:
        await manager.disconnect()


def format_diff_report(report: DiffReport, show_unchanged: bool = False) -> str:
    """Format diff report as readable text.

    Args:
        report: DiffReport to format
        show_unchanged: Include unchanged settings in output

    Returns:
        Formatted report string
    """
    lines: list[str] = []
    lines.append("=" * 70)
    lines.append(f"Settings Comparison: {report.source_a} vs {report.source_b}")
    lines.append("=" * 70)
    lines.append("")

    if not report.has_changes:
        lines.append("No differences found - settings are identical.")
        return "\n".join(lines)

    lines.append(f"Total changes: {report.total_changes}")
    lines.append("")

    def format_section(name: str, diffs: list[SettingDiff]) -> None:
        changes = [d for d in diffs if d.changed]
        if not changes and not show_unchanged:
            return

        lines.append(f"## {name}")
        lines.append("-" * 50)

        for diff in diffs:
            if not diff.changed and not show_unchanged:
                continue

            marker = " " if not diff.changed else "*"
            if diff.diff_type == "added":
                lines.append(f"{marker} [{diff.key}] {diff.label}: (new) {diff.value_b}")
            elif diff.diff_type == "removed":
                lines.append(f"{marker} [{diff.key}] {diff.label}: {diff.value_a} (removed)")
            elif diff.changed:
                lines.append(
                    f"{marker} [{diff.key}] {diff.label}: {diff.value_a} -> {diff.value_b}"
                )
            else:
                lines.append(f"  [{diff.key}] {diff.label}: {diff.value_a}")

        lines.append("")

    format_section("General Editor One", report.general_one)
    format_section("General Editor Two", report.general_two)
    format_section("General Editor Three", report.general_three)
    format_section("Game Timing", report.game_timing)

    return "\n".join(lines)


# Default baseline for standard TW2002 settings
DEFAULT_BASELINE: dict[str, dict[str, Any]] = {
    "general_one": {
        "A": {"label": "Turns per day", "value": "250"},
        "B": {"label": "Initial fighters", "value": "30"},
        "C": {"label": "Initial credits", "value": "300"},
        "D": {"label": "Initial holds", "value": "20"},
        "E": {"label": "Days until inactive deleted", "value": "30"},
        "G": {"label": "Ferrengi regeneration %", "value": "20%"},
        "H": {"label": "Colonist reproduction rate", "value": "750/day"},
        "I": {"label": "Daily log limit", "value": "800"},
        "M": {"label": "Max planets per sector", "value": "5"},
        "N": {"label": "Max traders per corp", "value": "5"},
        "R": {"label": "Tournament mode", "value": "Off"},
    },
    "general_two": {
        "2": {"label": "Inactivity Timeout", "value": "300 sec"},
        "7": {"label": "Port Regeneration Rate", "value": "5%/day"},
        "8": {"label": "Max Regen Per Visit", "value": "100%"},
        "T": {"label": "Max Bank Credits", "value": "500,000"},
        "U": {"label": "Cloaking Fail Rate", "value": "3%"},
        "V": {"label": "NavHaz Dispersion", "value": "3%"},
    },
    "general_three": {},
    "game_timing": {},
}


async def quick_diff_from_defaults(
    game: str,
    host: str = "localhost",
    port: int = 2003,
    password: str = "admin",
) -> DiffReport:
    """Quickly compare a game against default TW2002 settings.

    Args:
        game: Game slot to compare
        host: TEDIT host
        port: TEDIT port
        password: Admin password

    Returns:
        DiffReport comparing game to defaults
    """
    return await diff_from_baseline(game, DEFAULT_BASELINE, host, port, password)
