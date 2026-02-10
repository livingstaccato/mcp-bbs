from __future__ import annotations

import json
from dataclasses import dataclass
from time import time
from typing import TYPE_CHECKING, Any

from bbsbot.games.tw2002.character import CharacterState

if TYPE_CHECKING:
    from pathlib import Path


@dataclass
class ResumeCharacter:
    name: str
    credits: int | None
    sector: int | None
    last_active: float | None
    state_path: str


@dataclass
class ResumeEntry:
    game: str
    host: str
    port: int | None
    data_dir: str
    resumable: list[ResumeCharacter]
    dead: int
    total: int


def _iter_tw2002_dirs(knowledge_root: Path) -> list[Path]:
    dirs: list[Path] = []
    tw_dir = knowledge_root / "tw2002"
    if tw_dir.exists():
        dirs.extend([p for p in tw_dir.iterdir() if p.is_dir()])
    games_dir = knowledge_root / "games" / "tw2002"
    if games_dir.exists():
        dirs.extend([p for p in games_dir.iterdir() if p.is_dir()])
    return dirs


def _parse_host_port(dir_name: str) -> tuple[str, int | None]:
    if "_" not in dir_name:
        return dir_name, None
    host, port_str = dir_name.rsplit("_", 1)
    try:
        return host, int(port_str)
    except ValueError:
        return dir_name, None


def list_resumable_tw2002(
    knowledge_root: Path,
    *,
    active_within_hours: float | None = None,
    min_credits: int | None = None,
    require_sector: bool = False,
    name_prefix: str | None = None,
) -> list[ResumeEntry]:
    entries: list[ResumeEntry] = []
    now = time()

    for data_dir in _iter_tw2002_dirs(knowledge_root):
        records_path = data_dir / "character_records.json"
        if not records_path.exists():
            continue
        try:
            records = json.loads(records_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue

        host, port = _parse_host_port(data_dir.name)
        record_map = records.get("records", {})
        dead = 0
        resumable: list[ResumeCharacter] = []

        for name, record in record_map.items():
            died_at = record.get("died_at")
            if died_at:
                dead += 1
                continue
            state_path = data_dir / f"{name}_state.json"
            if not state_path.exists():
                continue
            try:
                state = CharacterState.from_dict(json.loads(state_path.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                state = None
            credits = state.credits if state else None
            sector = state.current_sector if state else None
            last_active = state.last_active if state else None

            if name_prefix and not name.startswith(name_prefix):
                continue
            if require_sector and sector is None:
                continue
            if min_credits is not None and (credits is None or credits < min_credits):
                continue
            if active_within_hours is not None:
                if last_active is None:
                    continue
                hours_since = (now - last_active) / 3600
                if hours_since > active_within_hours:
                    continue

            resumable.append(
                ResumeCharacter(
                    name=name,
                    credits=credits,
                    sector=sector,
                    last_active=last_active,
                    state_path=str(state_path),
                )
            )

        total = len(record_map)
        if resumable or total > 0:
            entries.append(
                ResumeEntry(
                    game="tw2002",
                    host=host,
                    port=port,
                    data_dir=str(data_dir),
                    resumable=resumable,
                    dead=dead,
                    total=total,
                )
            )

    return entries


def as_dict(entries: list[ResumeEntry]) -> list[dict[str, Any]]:
    return [
        {
            "game": entry.game,
            "host": entry.host,
            "port": entry.port,
            "data_dir": entry.data_dir,
            "dead": entry.dead,
            "total": entry.total,
            "resumable": [
                {
                    "name": char.name,
                    "credits": char.credits,
                    "sector": char.sector,
                    "last_active": char.last_active,
                    "state_path": char.state_path,
                }
                for char in entry.resumable
            ],
        }
        for entry in entries
    ]
