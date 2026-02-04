"""JSONL session logger."""

from __future__ import annotations

import asyncio
import base64
import json
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from io import TextIOWrapper


class SessionLogger:
    """JSONL session logger with thread-safe async writes."""

    def __init__(self, log_path: str | Path) -> None:
        """Initialize session logger.

        Args:
            log_path: Path to JSONL log file
        """
        self._log_path = Path(log_path)
        self._file: TextIOWrapper | None = None
        self._lock = asyncio.Lock()
        self._session_id: int | None = None
        self._context: dict[str, str] = {}

    async def start(self, session_id: int) -> None:
        """Open log file and write header.

        Args:
            session_id: Session identifier for log entries
        """
        async with self._lock:
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
            self._file = self._log_path.open("a", encoding="utf-8")
            self._session_id = session_id

            # Write header
            header = {
                "path": str(self._log_path),
                "started_at": time.time(),
            }
            await self._write_event("log_start", header)

    async def stop(self) -> None:
        """Close log file."""
        async with self._lock:
            if self._file:
                await self._write_event("log_stop", {})
                self._file.close()
                self._file = None

    async def log_send(self, keys: str) -> None:
        """Log sent keystrokes.

        Args:
            keys: Keystrokes sent to BBS
        """
        payload = keys.encode("cp437", errors="replace")
        data = {
            "keys": keys,
            "bytes_b64": base64.b64encode(payload).decode("ascii"),
        }
        await self._write_event("send", data)

    async def log_screen(self, snapshot: dict[str, Any], raw: bytes) -> None:
        """Log screen snapshot with raw bytes.

        Args:
            snapshot: Screen snapshot dictionary
            raw: Raw bytes received
        """
        data = {
            **snapshot,
            "raw": raw.decode("cp437", errors="replace"),
            "raw_bytes_b64": base64.b64encode(raw).decode("ascii"),
        }
        await self._write_event("read", data)

    async def log_event(self, event: str, data: dict[str, Any]) -> None:
        """Log custom event.

        Args:
            event: Event name
            data: Event data
        """
        await self._write_event(event, data)

    def set_context(self, context: dict[str, str]) -> None:
        """Set context metadata for log entries.

        Args:
            context: Context dictionary (e.g., menu, action)
        """
        self._context = {str(k): str(v) for k, v in context.items()}

    def clear_context(self) -> None:
        """Clear context metadata."""
        self._context = {}

    async def _write_event(self, event: str, data: dict[str, Any]) -> None:
        """Write event to log file (must hold lock).

        Args:
            event: Event name
            data: Event data
        """
        if not self._file:
            return

        record: dict[str, Any] = {"ts": time.time(), "event": event, "data": data}

        if self._session_id is not None:
            record["session_id"] = self._session_id

        if self._context:
            ctx = dict(self._context)
            record["ctx"] = ctx
            if "menu" in ctx:
                record["menu"] = ctx["menu"]
            if "action" in ctx:
                record["action"] = ctx["action"]

        self._file.write(json.dumps(record, ensure_ascii=True) + "\n")
        self._file.flush()
