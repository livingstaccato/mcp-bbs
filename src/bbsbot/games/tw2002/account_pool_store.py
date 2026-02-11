"""Cross-process account pool with lease + cooldown semantics."""

from __future__ import annotations

import json
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AccountLeaseError(RuntimeError):
    """Raised when an account cannot be leased for a bot."""


class AccountLease(BaseModel):
    """Lease metadata for one account."""

    bot_id: str
    leased_at: float
    lease_expires_at: float

    model_config = ConfigDict(extra="ignore")


class AccountPoolRecord(BaseModel):
    """One account in the pool."""

    account_id: str
    username: str
    character_password: str
    game_password: str | None = None
    host: str | None = None
    port: int | None = None
    game_letter: str | None = None
    source: str = "unknown"  # config | persisted | pool | generated
    created_at: float = Field(default_factory=time.time)
    last_used_at: float | None = None
    last_released_at: float | None = None
    use_count: int = 0
    cooldown_until: float | None = None
    disabled: bool = False
    lease: AccountLease | None = None

    model_config = ConfigDict(extra="ignore")

    def is_available(self, now: float) -> bool:
        if self.disabled:
            return False
        if self.cooldown_until and self.cooldown_until > now:
            return False
        return not (self.lease and self.lease.lease_expires_at > now)


class AccountPoolState(BaseModel):
    """Pool state persisted to disk."""

    updated_at: float = Field(default_factory=time.time)
    accounts: dict[str, AccountPoolRecord] = Field(default_factory=dict)

    model_config = ConfigDict(extra="ignore")


class AccountPoolStore:
    """File-backed account pool with process-safe leasing."""

    def __init__(
        self,
        *,
        pool_file: str | Path = "sessions/account_pool.json",
        lock_file: str | Path = "sessions/account_pool.lock",
    ) -> None:
        self.pool_file = Path(pool_file)
        self.lock_file = Path(lock_file)
        self.pool_file.parent.mkdir(parents=True, exist_ok=True)
        self.lock_file.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def account_id_for(*, username: str, host: str | None, port: int | None, game_letter: str | None) -> str:
        h = (host or "").strip().lower() or "localhost"
        p = int(port or 0)
        g = (game_letter or "-").strip().upper()
        u = (username or "").strip().lower()
        return f"{h}:{p}:{g}:{u}"

    def _load_state(self) -> AccountPoolState:
        if not self.pool_file.exists():
            return AccountPoolState()
        try:
            data = json.loads(self.pool_file.read_text(encoding="utf-8"))
            return AccountPoolState.model_validate(data)
        except Exception:
            return AccountPoolState()

    def _save_state(self, state: AccountPoolState) -> None:
        state.updated_at = time.time()
        tmp = self.pool_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(state.model_dump(mode="json"), indent=2), encoding="utf-8")
        tmp.replace(self.pool_file)

    @contextmanager
    def _locked_state(self):
        import fcntl

        with self.lock_file.open("a+", encoding="utf-8") as lock_handle:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
            state = self._load_state()
            try:
                yield state
            finally:
                self._save_state(state)
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)

    def upsert_account(
        self,
        *,
        username: str,
        character_password: str,
        game_password: str | None,
        host: str | None,
        port: int | None,
        game_letter: str | None,
        source: str,
    ) -> AccountPoolRecord:
        aid = self.account_id_for(username=username, host=host, port=port, game_letter=game_letter)
        now = time.time()
        with self._locked_state() as state:
            record = state.accounts.get(aid)
            if record is None:
                record = AccountPoolRecord(
                    account_id=aid,
                    username=username,
                    character_password=character_password,
                    game_password=game_password,
                    host=host,
                    port=port,
                    game_letter=game_letter,
                    source=source or "unknown",
                    created_at=now,
                )
            else:
                record.username = username
                record.character_password = character_password
                if game_password is not None:
                    record.game_password = game_password
                record.host = host
                record.port = int(port) if port is not None else None
                record.game_letter = game_letter
                if source:
                    record.source = source
            state.accounts[aid] = record
            return record

    def reserve_account(
        self,
        *,
        bot_id: str,
        username: str,
        character_password: str,
        game_password: str | None,
        host: str | None,
        port: int | None,
        game_letter: str | None,
        source: str,
        lease_ttl_s: int = 86_400,
    ) -> AccountPoolRecord:
        aid = self.account_id_for(username=username, host=host, port=port, game_letter=game_letter)
        now = time.time()
        with self._locked_state() as state:
            record = state.accounts.get(aid)
            if record is None:
                record = AccountPoolRecord(
                    account_id=aid,
                    username=username,
                    character_password=character_password,
                    game_password=game_password,
                    host=host,
                    port=port,
                    game_letter=game_letter,
                    source=source or "unknown",
                    created_at=now,
                )
            else:
                # Keep credentials fresh if caller provides them.
                record.username = username
                record.character_password = character_password
                if game_password is not None:
                    record.game_password = game_password
                record.host = host
                record.port = int(port) if port is not None else None
                record.game_letter = game_letter
                if source:
                    record.source = source

            if record.disabled:
                raise AccountLeaseError(f"account_disabled:{record.username}")
            if record.cooldown_until and record.cooldown_until > now:
                raise AccountLeaseError(f"account_cooldown:{record.username}")
            if record.lease and record.lease.bot_id != bot_id and record.lease.lease_expires_at > now:
                raise AccountLeaseError(f"account_leased:{record.username}:{record.lease.bot_id}")

            record.lease = AccountLease(
                bot_id=bot_id,
                leased_at=now,
                lease_expires_at=now + max(60, int(lease_ttl_s)),
            )
            record.last_used_at = now
            record.use_count = int(record.use_count) + 1
            state.accounts[aid] = record
            return record

    def acquire_account(
        self,
        *,
        bot_id: str,
        host: str | None,
        port: int | None,
        game_letter: str | None,
        lease_ttl_s: int = 86_400,
    ) -> AccountPoolRecord | None:
        now = time.time()
        with self._locked_state() as state:
            candidates: list[AccountPoolRecord] = []
            for record in state.accounts.values():
                if host and record.host and str(record.host).lower() != str(host).lower():
                    continue
                if port and record.port and int(record.port) != int(port):
                    continue
                if game_letter and record.game_letter and str(record.game_letter).upper() != str(game_letter).upper():
                    continue
                if record.is_available(now):
                    candidates.append(record)
            if not candidates:
                return None

            # Reuse the least-recently-used available account to spread usage.
            candidates.sort(key=lambda r: (r.last_used_at or 0.0, r.created_at))
            record = candidates[0]
            record.lease = AccountLease(
                bot_id=bot_id,
                leased_at=now,
                lease_expires_at=now + max(60, int(lease_ttl_s)),
            )
            record.last_used_at = now
            record.use_count = int(record.use_count) + 1
            state.accounts[record.account_id] = record
            return record

    def release_by_bot(self, *, bot_id: str, cooldown_s: int = 0) -> int:
        now = time.time()
        released = 0
        with self._locked_state() as state:
            for aid, record in state.accounts.items():
                lease = record.lease
                if lease is None or lease.bot_id != bot_id:
                    continue
                record.lease = None
                record.last_released_at = now
                if cooldown_s > 0:
                    record.cooldown_until = now + int(cooldown_s)
                state.accounts[aid] = record
                released += 1
        return released

    def list_accounts(self) -> list[AccountPoolRecord]:
        with self._locked_state() as state:
            return sorted(
                [AccountPoolRecord.model_validate(r.model_dump(mode="json")) for r in state.accounts.values()],
                key=lambda r: r.account_id,
            )

    def summary(self) -> dict[str, Any]:
        now = time.time()
        accounts = self.list_accounts()
        leased = [a for a in accounts if a.lease and a.lease.lease_expires_at > now]
        cooldown = [a for a in accounts if a.cooldown_until and a.cooldown_until > now]
        available = [a for a in accounts if a.is_available(now)]
        return {
            "accounts_total": len(accounts),
            "leased": len(leased),
            "cooldown": len(cooldown),
            "available": len(available),
            "accounts": [a.model_dump(mode="json") for a in accounts],
        }
