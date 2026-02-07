from __future__ import annotations

import asyncio
import base64
from typing import Any

from bbsbot.core.session import Session
from bbsbot.watch.broker import WatchBroker
from bbsbot.watch.registry import watch_settings


class WatchManager:
    """Lifecycle + wiring for watch broker and per-session hooks."""

    def __init__(self, broker: WatchBroker | None = None) -> None:
        self._broker = broker or WatchBroker()

    def emit_event(self, event: str, payload: dict[str, Any]) -> None:
        """Emit a structured watch event (JSON protocol only).

        This is intended for out-of-band events that are not part of the raw BBS
        byte stream (e.g. goal visualization lines).
        """
        if not watch_settings.enabled:
            return
        if watch_settings.protocol != "json":
            return
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return
        asyncio.create_task(self._broker.broadcast_event(event, payload))

    async def start(self) -> None:
        if not watch_settings.enabled:
            return
        await self._broker.start(watch_settings.host, watch_settings.port)

    async def stop(self) -> None:
        await self._broker.stop()

    def attach_session(self, session: Session) -> None:
        if not watch_settings.enabled:
            return

        async def _broadcast(snapshot: dict[str, Any], raw: bytes) -> None:
            if watch_settings.protocol == "json":
                payload: dict[str, Any] = {
                    "session_id": session.session_id,
                    "screen_hash": snapshot.get("screen_hash", ""),
                    "cursor": snapshot.get("cursor", {}),
                    "captured_at": snapshot.get("captured_at"),
                    "cols": snapshot.get("cols", 0),
                    "rows": snapshot.get("rows", 0),
                }
                if "prompt_detected" in snapshot:
                    payload["prompt_detected"] = snapshot.get("prompt_detected")
                if watch_settings.include_snapshot_text:
                    payload["screen"] = snapshot.get("screen", "")
                payload["raw_bytes_b64"] = base64.b64encode(raw).decode("ascii") if raw else ""
                await self._broker.broadcast_event("snapshot", payload)
                return

            if not raw and not watch_settings.metadata:
                return
            if raw:
                if watch_settings.send_clear:
                    await self._broker.broadcast_raw(b"\x1b[2J\x1b[H")
                await self._broker.broadcast_raw(raw)
            if watch_settings.metadata:
                payload: dict[str, Any] = {
                    "session_id": session.session_id,
                    "screen_hash": snapshot.get("screen_hash", ""),
                    "cursor": snapshot.get("cursor", {}),
                    "captured_at": snapshot.get("captured_at"),
                }
                if watch_settings.include_snapshot_text:
                    payload["screen"] = snapshot.get("screen", "")
                    payload["raw_bytes_b64"] = base64.b64encode(raw).decode("ascii")
                await self._broker.broadcast_event("snapshot", payload)

        def _callback(snapshot: dict[str, Any], raw: bytes) -> None:
            asyncio.create_task(_broadcast(snapshot, raw))

        session.add_watch(_callback, interval_s=0.0)
