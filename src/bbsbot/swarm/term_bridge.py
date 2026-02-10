"""Worker-side terminal bridge to the Swarm Manager.

This connects a running bot worker process to the manager WebSocket endpoint:
  /ws/worker/{bot_id}/term

It forwards:
- live terminal output (cp437-decoded, including ANSI escapes) from Session watchers
- snapshot responses on demand
- hijack control and input commands from the dashboard
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from bbsbot.logging import get_logger

logger = get_logger(__name__)


def _to_ws_url(manager_url: str, path: str) -> str:
    base = manager_url.rstrip("/")
    if base.startswith("https://"):
        base = "wss://" + base[len("https://") :]
    elif base.startswith("http://"):
        base = "ws://" + base[len("http://") :]
    return base + path


class TermBridge:
    def __init__(self, bot: Any, bot_id: str, manager_url: str) -> None:
        self._bot = bot
        self._bot_id = bot_id
        self._manager_url = manager_url
        self._ws = None
        self._send_q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=2000)
        self._latest_snapshot: dict[str, Any] | None = None
        self._running = False
        self._task: asyncio.Task | None = None
        # Session is created later (after connect/login). Attach lazily and re-attach
        # if the worker reconnects with a new Session instance.
        self._attached_session: Any | None = None

    def attach_session(self) -> None:
        """Attach a Session watcher to forward live terminal output."""
        session = getattr(self._bot, "session", None)
        if session is None:
            return
        if self._attached_session is session:
            return
        self._attached_session = session

        def _watch(snapshot: dict[str, Any], raw: bytes) -> None:
            # Keep last snapshot for on-demand snapshot responses.
            self._latest_snapshot = snapshot
            if not raw:
                return
            try:
                text = raw.decode("cp437", errors="replace")
            except Exception:
                return
            if not text:
                return
            msg = {"type": "term", "data": text, "ts": time.time()}
            try:
                self._send_q.put_nowait(msg)
            except asyncio.QueueFull:
                # Drop on overload; terminal is best-effort.
                pass

        # Session calls watchers outside its lock; keep callback non-blocking.
        session.add_watch(_watch, interval_s=0.0)

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self) -> None:
        try:
            import websockets
        except Exception as e:  # pragma: no cover
            logger.warning("term_bridge_no_websockets", error=str(e))
            return

        url = _to_ws_url(self._manager_url, f"/ws/worker/{self._bot_id}/term")
        logger.info("term_bridge_connecting", bot_id=self._bot_id, url=url)

        try:
            async with websockets.connect(url, max_size=10 * 1024 * 1024) as ws:
                self._ws = ws
                send_task = asyncio.create_task(self._send_loop(ws))
                recv_task = asyncio.create_task(self._recv_loop(ws))
                done, pending = await asyncio.wait(
                    {send_task, recv_task},
                    return_when=asyncio.FIRST_EXCEPTION,
                )
                for t in pending:
                    t.cancel()
                for t in done:
                    exc = t.exception()
                    if exc:
                        raise exc
        except asyncio.CancelledError:
            return
        except Exception as e:
            logger.warning("term_bridge_disconnected", bot_id=self._bot_id, error=str(e))

    async def _send_loop(self, ws: Any) -> None:
        while self._running:
            msg = await self._send_q.get()
            await ws.send(json.dumps(msg, ensure_ascii=True))

    async def _recv_loop(self, ws: Any) -> None:
        while self._running:
            try:
                raw = await ws.recv()
            except Exception:
                # Normal shutdown/close should not bubble as an unhandled task exception.
                return
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            mtype = msg.get("type")
            if mtype == "snapshot_req":
                await self._send_snapshot(ws)
            elif mtype == "analyze_req":
                await self._send_analysis(ws)
            elif mtype == "control":
                action = msg.get("action")
                if action == "pause":
                    await self._set_hijacked(True)
                elif action == "resume":
                    await self._set_hijacked(False)
                elif action == "step":
                    await self._request_step()
            elif mtype == "input":
                data = msg.get("data", "")
                if data:
                    await self._send_keys(data)
            elif mtype == "resize":
                cols = int(msg.get("cols", 80) or 80)
                rows = int(msg.get("rows", 25) or 25)
                await self._set_size(cols, rows)

    async def _send_snapshot(self, ws: Any) -> None:
        session = getattr(self._bot, "session", None)
        if session is None:
            return
        # If we started the bridge before the bot connected, we won't have a watcher attached.
        # Attach here so the browser gets streaming output soon after the first snapshot request.
        try:
            self.attach_session()
        except Exception:
            pass
        try:
            snapshot = self._latest_snapshot or session.emulator.get_snapshot()
            msg = {
                "type": "snapshot",
                "screen": snapshot.get("screen", ""),
                "cursor": snapshot.get("cursor", {"x": 0, "y": 0}),
                "cols": int(snapshot.get("cols", 80) or 80),
                "rows": int(snapshot.get("rows", 25) or 25),
                "screen_hash": snapshot.get("screen_hash", ""),
                "cursor_at_end": bool(snapshot.get("cursor_at_end", True)),
                "has_trailing_space": bool(snapshot.get("has_trailing_space", False)),
                "prompt_detected": snapshot.get("prompt_detected"),
                "ts": time.time(),
            }
            await ws.send(json.dumps(msg, ensure_ascii=True))
        except Exception:
            return

    async def _send_analysis(self, ws: Any) -> None:
        # Best-effort: analysis is optional and should never crash the bridge.
        try:
            from bbsbot.games.tw2002.debug_screens import analyze_screen, format_screen_analysis
        except Exception:
            return

        try:
            analysis = await analyze_screen(self._bot)
            await ws.send(
                json.dumps(
                    {
                        "type": "analysis",
                        "formatted": format_screen_analysis(analysis),
                        "raw": analysis.model_dump(),
                        "ts": time.time(),
                    },
                    ensure_ascii=True,
                )
            )
        except Exception:
            return

    async def _send_keys(self, data: str) -> None:
        session = getattr(self._bot, "session", None)
        if session is None:
            return
        try:
            await session.send(data, mark_awaiting=False)
        except Exception:
            return

    async def _request_step(self) -> None:
        fn = getattr(self._bot, "request_step", None)
        if callable(fn):
            try:
                await fn()
            except Exception:
                return

    async def _set_size(self, cols: int, rows: int) -> None:
        session = getattr(self._bot, "session", None)
        if session is None:
            return
        try:
            await session.set_size(cols, rows)
        except Exception:
            return

    async def _set_hijacked(self, enabled: bool) -> None:
        fn = getattr(self._bot, "set_hijacked", None)
        if callable(fn):
            await fn(enabled)
            try:
                self._send_q.put_nowait({"type": "status", "hijacked": enabled, "ts": time.time()})
            except asyncio.QueueFull:
                pass
