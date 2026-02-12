# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Persistent per-bot identity and session lifecycle storage.

Stores bot credentials (for reuse across restarts) and session history
timestamps/metrics in JSON files under sessions/.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class BotSessionRecord(BaseModel):
    """Single bot runtime session record."""

    id: str
    started_at: float
    stopped_at: float | None = None
    stop_reason: str | None = None
    state: str | None = None
    exit_reason: str | None = None
    error_type: str | None = None
    error_message: str | None = None
    turns_executed: int = 0
    credits: int | None = None
    credits_delta: int | None = None
    trades_executed: int = 0
    sector: int | None = None

    model_config = ConfigDict(extra="ignore")


class BotIdentityRecord(BaseModel):
    """Durable identity + lifecycle metadata for one bot_id."""

    bot_id: str
    username: str | None = None
    character_password: str | None = None
    game_password: str | None = None
    host: str | None = None
    port: int | None = None
    game_letter: str | None = None
    identity_source: str = "unknown"  # config | persisted | pool | generated
    config_path: str | None = None
    first_seen_at: float = Field(default_factory=time.time)
    last_updated_at: float = Field(default_factory=time.time)
    last_started_at: float | None = None
    last_stopped_at: float | None = None
    run_count: int = 0
    active_session_id: str | None = None
    sessions: list[BotSessionRecord] = Field(default_factory=list)

    model_config = ConfigDict(extra="ignore")


class BotIdentityStore:
    """JSON-backed store for per-bot identity/session data."""

    def __init__(self, data_dir: str | Path = "sessions/bot_sessions", max_sessions: int = 500):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.max_sessions = max(10, int(max_sessions))

    def _path(self, bot_id: str) -> Path:
        safe = "".join(ch for ch in bot_id if ch.isalnum() or ch in ("_", "-")).strip()
        safe = safe or "bot"
        return self.data_dir / f"{safe}.json"

    def load(self, bot_id: str) -> BotIdentityRecord | None:
        path = self._path(bot_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return BotIdentityRecord.model_validate(data)
        except Exception:
            return None

    def save(self, record: BotIdentityRecord) -> None:
        record.last_updated_at = time.time()
        path = self._path(record.bot_id)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(record.model_dump(mode="json"), indent=2), encoding="utf-8")
        tmp.replace(path)

    def upsert_identity(
        self,
        *,
        bot_id: str,
        username: str,
        character_password: str,
        game_password: str | None,
        host: str | None,
        port: int | None,
        game_letter: str | None,
        config_path: str | None,
        identity_source: str | None = None,
    ) -> BotIdentityRecord:
        record = self.load(bot_id) or BotIdentityRecord(bot_id=bot_id)
        record.username = username
        record.character_password = character_password
        if game_password is not None:
            record.game_password = game_password
        record.host = host
        record.port = port
        record.game_letter = game_letter
        record.config_path = config_path
        if identity_source:
            record.identity_source = identity_source
        self.save(record)
        return record

    def start_session(
        self,
        *,
        bot_id: str,
        state: str | None = None,
    ) -> BotSessionRecord:
        record = self.load(bot_id) or BotIdentityRecord(bot_id=bot_id)
        session = BotSessionRecord(id=uuid4().hex, started_at=time.time(), state=state)
        record.run_count = int(record.run_count) + 1
        record.last_started_at = session.started_at
        record.active_session_id = session.id
        record.sessions.append(session)
        if len(record.sessions) > self.max_sessions:
            record.sessions = record.sessions[-self.max_sessions :]
        self.save(record)
        return session

    def end_session(
        self,
        *,
        bot_id: str,
        session_id: str,
        stop_reason: str,
        state: str | None = None,
        exit_reason: str | None = None,
        error_type: str | None = None,
        error_message: str | None = None,
        turns_executed: int | None = None,
        credits: int | None = None,
        credits_delta: int | None = None,
        trades_executed: int | None = None,
        sector: int | None = None,
    ) -> None:
        record = self.load(bot_id)
        if record is None:
            return
        now = time.time()
        for idx in range(len(record.sessions) - 1, -1, -1):
            session = record.sessions[idx]
            if session.id != session_id:
                continue
            session.stopped_at = now
            session.stop_reason = stop_reason
            session.state = state or session.state
            session.exit_reason = exit_reason
            session.error_type = error_type
            session.error_message = error_message
            if turns_executed is not None:
                session.turns_executed = int(turns_executed)
            if credits is not None:
                session.credits = int(credits)
            if credits_delta is not None:
                session.credits_delta = int(credits_delta)
            if trades_executed is not None:
                session.trades_executed = int(trades_executed)
            if sector is not None:
                session.sector = int(sector)
            break
        record.last_stopped_at = now
        if record.active_session_id == session_id:
            record.active_session_id = None
        self.save(record)

    def list_records(self) -> list[BotIdentityRecord]:
        records: list[BotIdentityRecord] = []
        for path in sorted(self.data_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                rec = BotIdentityRecord.model_validate(data)
                records.append(rec)
            except Exception:
                continue
        return records
