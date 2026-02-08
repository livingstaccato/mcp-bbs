"""Log reading and streaming service for bot workers.

Provides paginated log reading, tail-style access, and WebSocket
streaming for real-time log viewing in dashboards.
"""

from __future__ import annotations

import asyncio
import mmap
import os
from collections import deque
from pathlib import Path

from fastapi import WebSocket, WebSocketDisconnect

from bbsbot.logging import get_logger

logger = get_logger(__name__)

LOG_DIR = Path("logs/workers")
MAX_TAIL_LINES = 1000
MAX_CONCURRENT_STREAMS = 50
STREAM_POLL_INTERVAL = 0.3


class LogService:
    """Service for reading and streaming bot log files."""

    def __init__(self, log_dir: Path = LOG_DIR) -> None:
        self.log_dir = log_dir
        self._active_streams: set[str] = set()

    def log_path(self, bot_id: str) -> Path:
        """Get the log file path for a bot."""
        return self.log_dir / f"{bot_id}.log"

    def exists(self, bot_id: str) -> bool:
        """Check if a log file exists for the given bot."""
        return self.log_path(bot_id).is_file()

    def read_logs(
        self, bot_id: str, offset: int = 0, limit: int = 100
    ) -> dict:
        """Read paginated log lines from a bot's log file.

        Args:
            bot_id: Bot identifier
            offset: Line offset to start from
            limit: Maximum number of lines to return

        Returns:
            Dict with lines, offset, limit, total_lines, has_more
        """
        path = self.log_path(bot_id)
        if not path.is_file():
            return {
                "lines": [],
                "offset": offset,
                "limit": limit,
                "total_lines": 0,
                "has_more": False,
            }

        file_size = path.stat().st_size
        if file_size == 0:
            return {
                "lines": [],
                "offset": offset,
                "limit": limit,
                "total_lines": 0,
                "has_more": False,
            }

        # For large files use mmap, otherwise direct read
        if file_size > 10 * 1024 * 1024:  # >10MB
            return self._read_with_mmap(path, offset, limit)

        with open(path, errors="replace") as f:
            all_lines = f.readlines()

        total = len(all_lines)
        end = min(offset + limit, total)
        selected = all_lines[offset:end]

        return {
            "lines": [line.rstrip("\n") for line in selected],
            "offset": offset,
            "limit": limit,
            "total_lines": total,
            "has_more": end < total,
        }

    def _read_with_mmap(
        self, path: Path, offset: int, limit: int
    ) -> dict:
        """Read lines from large file using mmap."""
        with open(path, "rb") as f:
            with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                lines: list[str] = []
                line_num = 0
                pos = 0

                while pos < mm.size():
                    end = mm.find(b"\n", pos)
                    if end == -1:
                        end = mm.size()

                    if line_num >= offset:
                        raw = mm[pos:end]
                        lines.append(raw.decode("utf-8", errors="replace"))
                        if len(lines) >= limit:
                            line_num += 1
                            break

                    pos = end + 1
                    line_num += 1

                # Count remaining lines approximately
                remaining = mm[pos:].count(b"\n") if pos < mm.size() else 0

                return {
                    "lines": lines,
                    "offset": offset,
                    "limit": limit,
                    "total_lines": offset + len(lines) + remaining,
                    "has_more": remaining > 0,
                }

    def tail_logs(self, bot_id: str, lines: int = 50) -> dict:
        """Read the last N lines from a bot's log file.

        Args:
            bot_id: Bot identifier
            lines: Number of lines to return (max 1000)

        Returns:
            Dict with lines and total_lines
        """
        lines = min(lines, MAX_TAIL_LINES)
        path = self.log_path(bot_id)

        if not path.is_file():
            return {"lines": [], "total_lines": 0}

        file_size = path.stat().st_size
        if file_size == 0:
            return {"lines": [], "total_lines": 0}

        # Use deque for efficient last-N-lines
        result: deque[str] = deque(maxlen=lines)
        total = 0
        with open(path, errors="replace") as f:
            for line in f:
                result.append(line.rstrip("\n"))
                total += 1

        return {
            "lines": list(result),
            "total_lines": total,
        }

    async def stream_logs(self, bot_id: str, websocket: WebSocket) -> None:
        """Stream log updates via WebSocket (tail -f style).

        Args:
            bot_id: Bot identifier
            websocket: Connected WebSocket
        """
        if len(self._active_streams) >= MAX_CONCURRENT_STREAMS:
            await websocket.send_json(
                {"error": "Too many active log streams"}
            )
            return

        stream_key = f"{bot_id}:{id(websocket)}"
        self._active_streams.add(stream_key)

        try:
            path = self.log_path(bot_id)

            # Send initial tail
            if path.is_file():
                tail = self.tail_logs(bot_id, lines=50)
                await websocket.send_json({
                    "type": "initial",
                    "lines": tail["lines"],
                })
            else:
                await websocket.send_json({
                    "type": "initial",
                    "lines": ["[Waiting for log file...]"],
                })

            # Stream new lines
            last_size = path.stat().st_size if path.is_file() else 0

            while True:
                await asyncio.sleep(STREAM_POLL_INTERVAL)

                if not path.is_file():
                    continue

                current_size = path.stat().st_size
                if current_size <= last_size:
                    if current_size < last_size:
                        # File was truncated (bot restarted)
                        last_size = 0
                        await websocket.send_json({
                            "type": "truncated",
                            "lines": ["[Log file reset - bot restarted]"],
                        })
                    continue

                # Read new content
                new_lines: list[str] = []
                with open(path, errors="replace") as f:
                    f.seek(last_size)
                    for line in f:
                        new_lines.append(line.rstrip("\n"))

                last_size = current_size

                if new_lines:
                    await websocket.send_json({
                        "type": "append",
                        "lines": new_lines,
                    })

        except WebSocketDisconnect:
            logger.debug(f"Log stream disconnected for {bot_id}")
        except Exception as e:
            logger.error(f"Log stream error for {bot_id}: {e}")
        finally:
            self._active_streams.discard(stream_key)
