"""Terminal spy/hijack WebSocket routes for the Swarm Dashboard.

This module provides a simple hub that bridges:
1) Worker -> Manager: live terminal stream + snapshot requests
2) Browser -> Manager: watch live stream and (optionally) hijack input
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, Field

from bbsbot.logging import get_logger

logger = get_logger(__name__)


class _BotTermState(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    worker_ws: WebSocket | None = None
    browsers: set[WebSocket] = Field(default_factory=set)
    hijack_owner: WebSocket | None = None
    last_snapshot: dict[str, Any] | None = None


class TermHub:
    """In-memory registry for terminal websocket connections."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._bots: dict[str, _BotTermState] = {}

    async def _get(self, bot_id: str) -> _BotTermState:
        async with self._lock:
            st = self._bots.get(bot_id)
            if st is None:
                st = _BotTermState()
                self._bots[bot_id] = st
            return st

    async def _broadcast(self, bot_id: str, msg: dict[str, Any]) -> None:
        st = await self._get(bot_id)
        dead: set[WebSocket] = set()
        payload = json.dumps(msg, ensure_ascii=True)
        for ws in list(st.browsers):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.add(ws)
        if dead:
            async with self._lock:
                st2 = self._bots.get(bot_id)
                if st2 is not None:
                    for ws in dead:
                        st2.browsers.discard(ws)

    async def _broadcast_hijack_state(self, bot_id: str) -> None:
        st = await self._get(bot_id)
        dead: set[WebSocket] = set()
        for ws in list(st.browsers):
            try:
                owner = "me" if st.hijack_owner is ws else ("other" if st.hijack_owner is not None else None)
                await ws.send_text(
                    json.dumps(
                        {
                            "type": "hijack_state",
                            "hijacked": st.hijack_owner is not None,
                            "owner": owner,
                        },
                        ensure_ascii=True,
                    )
                )
            except Exception:
                dead.add(ws)
        if dead:
            async with self._lock:
                st2 = self._bots.get(bot_id)
                if st2 is not None:
                    for ws in dead:
                        st2.browsers.discard(ws)

    async def _send_worker(self, bot_id: str, msg: dict[str, Any]) -> bool:
        st = await self._get(bot_id)
        if st.worker_ws is None:
            return False
        try:
            await st.worker_ws.send_text(json.dumps(msg, ensure_ascii=True))
            return True
        except Exception:
            async with self._lock:
                st2 = self._bots.get(bot_id)
                if st2 is not None and st2.worker_ws is st.worker_ws:
                    st2.worker_ws = None
            return False

    async def _set_hijack_owner(self, bot_id: str, owner: WebSocket | None) -> None:
        async with self._lock:
            st = self._bots.get(bot_id)
            if st is None:
                st = _BotTermState()
                self._bots[bot_id] = st
            st.hijack_owner = owner

    async def _is_owner(self, bot_id: str, ws: WebSocket) -> bool:
        st = await self._get(bot_id)
        return st.hijack_owner is ws

    async def _owner_label_for(self, bot_id: str, ws: WebSocket) -> str | None:
        st = await self._get(bot_id)
        if st.hijack_owner is None:
            return None
        return "me" if st.hijack_owner is ws else "other"

    async def _hijack_state_msg_for(self, bot_id: str, ws: WebSocket) -> dict[str, Any]:
        st = await self._get(bot_id)
        return {
            "type": "hijack_state",
            "hijacked": st.hijack_owner is not None,
            "owner": await self._owner_label_for(bot_id, ws),
        }

    async def _request_snapshot(self, bot_id: str) -> None:
        await self._send_worker(
            bot_id,
            {"type": "snapshot_req", "req_id": str(uuid.uuid4()), "ts": time.time()},
        )

    def create_router(self) -> APIRouter:
        router = APIRouter()

        @router.websocket("/ws/worker/{bot_id}/term")
        async def ws_worker_term(websocket: WebSocket, bot_id: str) -> None:
            await websocket.accept()
            st = await self._get(bot_id)
            async with self._lock:
                st2 = self._bots.get(bot_id)
                if st2 is None:
                    st2 = _BotTermState()
                    self._bots[bot_id] = st2
                st2.worker_ws = websocket
            logger.info("term_worker_connected", bot_id=bot_id)

            # If a browser is already connected, ask the worker for a fresh snapshot.
            await self._request_snapshot(bot_id)

            try:
                while True:
                    raw = await websocket.receive_text()
                    try:
                        msg = json.loads(raw)
                    except Exception:
                        continue
                    mtype = msg.get("type")
                    if mtype == "term":
                        data = msg.get("data", "")
                        if data:
                            await self._broadcast(bot_id, {"type": "term", "data": data, "ts": msg.get("ts", time.time())})
                    elif mtype == "snapshot":
                        # Store last snapshot for new browser clients and forward to all current watchers.
                        snapshot = {
                            "type": "snapshot",
                            "screen": msg.get("screen", ""),
                            "cursor": msg.get("cursor", {"x": 0, "y": 0}),
                            "cols": int(msg.get("cols", 80) or 80),
                            "rows": int(msg.get("rows", 25) or 25),
                            "ts": msg.get("ts", time.time()),
                        }
                        async with self._lock:
                            st3 = self._bots.get(bot_id)
                            if st3 is not None:
                                st3.last_snapshot = snapshot
                        await self._broadcast(bot_id, snapshot)
                    elif mtype == "status":
                        await self._broadcast(bot_id, msg)
            except WebSocketDisconnect:
                pass
            except Exception as e:
                logger.warning("term_worker_ws_error", bot_id=bot_id, error=str(e))
            finally:
                async with self._lock:
                    st4 = self._bots.get(bot_id)
                    if st4 is not None and st4.worker_ws is websocket:
                        st4.worker_ws = None
                logger.info("term_worker_disconnected", bot_id=bot_id)

        @router.websocket("/ws/bot/{bot_id}/term")
        async def ws_browser_term(websocket: WebSocket, bot_id: str) -> None:
            await websocket.accept()
            st = await self._get(bot_id)
            async with self._lock:
                st2 = self._bots.get(bot_id)
                if st2 is None:
                    st2 = _BotTermState()
                    self._bots[bot_id] = st2
                st2.browsers.add(websocket)

            # Hello + current hijack state
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "hello",
                        "bot_id": bot_id,
                        "can_hijack": True,
                        "hijacked": st.hijack_owner is not None,
                        "hijacked_by_me": st.hijack_owner is websocket,
                    },
                    ensure_ascii=True,
                )
            )
            await websocket.send_text(json.dumps(await self._hijack_state_msg_for(bot_id, websocket), ensure_ascii=True))

            # Best-effort snapshot: last known or request from worker.
            if st.last_snapshot is not None:
                await websocket.send_text(json.dumps(st.last_snapshot, ensure_ascii=True))
            else:
                await self._request_snapshot(bot_id)

            try:
                while True:
                    raw = await websocket.receive_text()
                    try:
                        msg = json.loads(raw)
                    except Exception:
                        continue
                    mtype = msg.get("type")
                    if mtype == "snapshot_req":
                        await self._request_snapshot(bot_id)
                    elif mtype == "hijack_request":
                        st_now = await self._get(bot_id)
                        if st_now.hijack_owner is None:
                            await self._set_hijack_owner(bot_id, websocket)
                            ok = await self._send_worker(bot_id, {"type": "control", "action": "pause", "owner": "dashboard", "lease_s": 0, "ts": time.time()})
                            if not ok:
                                await self._set_hijack_owner(bot_id, None)
                                await websocket.send_text(json.dumps({"type": "error", "message": "No worker connected for this bot."}, ensure_ascii=True))
                            await self._broadcast_hijack_state(bot_id)
                        else:
                            await websocket.send_text(json.dumps({"type": "error", "message": "Already hijacked by another client."}, ensure_ascii=True))
                            await websocket.send_text(json.dumps(await self._hijack_state_msg_for(bot_id, websocket), ensure_ascii=True))
                    elif mtype == "hijack_release":
                        if await self._is_owner(bot_id, websocket):
                            await self._set_hijack_owner(bot_id, None)
                            await self._send_worker(bot_id, {"type": "control", "action": "resume", "owner": "dashboard", "lease_s": 0, "ts": time.time()})
                            await self._broadcast_hijack_state(bot_id)
                    elif mtype == "input":
                        if await self._is_owner(bot_id, websocket):
                            data = msg.get("data", "")
                            if data:
                                ok = await self._send_worker(bot_id, {"type": "input", "data": data, "ts": time.time()})
                                if not ok:
                                    await websocket.send_text(json.dumps({"type": "error", "message": "Worker connection lost."}, ensure_ascii=True))
                        else:
                            # Ignore input from non-owner.
                            continue
            except WebSocketDisconnect:
                pass
            except Exception as e:
                logger.warning("term_browser_ws_error", bot_id=bot_id, error=str(e))
            finally:
                # Remove from watchers + release hijack if owner
                was_owner = await self._is_owner(bot_id, websocket)
                async with self._lock:
                    st3 = self._bots.get(bot_id)
                    if st3 is not None:
                        st3.browsers.discard(websocket)
                        if was_owner and st3.hijack_owner is websocket:
                            st3.hijack_owner = None
                if was_owner:
                    await self._send_worker(bot_id, {"type": "control", "action": "resume", "owner": "dashboard", "lease_s": 0, "ts": time.time()})
                    await self._broadcast_hijack_state(bot_id)

        return router


def setup(manager: Any) -> APIRouter:
    """Create (or reuse) a TermHub attached to the manager instance."""
    hub = getattr(manager, "term_hub", None)
    if hub is None:
        hub = TermHub()
        setattr(manager, "term_hub", hub)
    return hub.create_router()
