# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Terminal spy/hijack routes for the Swarm Dashboard and MCP takeover.

This hub bridges:
1) Worker -> Manager: live terminal stream + snapshot requests
2) Browser -> Manager: watch live stream and websocket hijack
3) MCP/HTTP -> Manager: lease-based hijack sessions with guarded input
"""

from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from collections import deque
from typing import Any

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from bbsbot.logging import get_logger

logger = get_logger(__name__)


class _HijackSession(BaseModel):
    hijack_id: str
    owner: str
    acquired_at: float
    lease_expires_at: float
    last_heartbeat: float


class _BotTermState(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    worker_ws: WebSocket | None = None
    browsers: set[WebSocket] = Field(default_factory=set)
    hijack_owner: WebSocket | None = None
    hijack_owner_expires_at: float | None = None
    hijack_session: _HijackSession | None = None
    last_snapshot: dict[str, Any] | None = None
    events: deque[dict[str, Any]] = Field(default_factory=lambda: deque(maxlen=2000))
    event_seq: int = 0


class HijackAcquireRequest(BaseModel):
    owner: str = "mcp"
    lease_s: int = 90


class HijackHeartbeatRequest(BaseModel):
    lease_s: int = 90


class HijackSendRequest(BaseModel):
    keys: str
    expect_prompt_id: str | None = None
    expect_regex: str | None = None
    timeout_ms: int = 2000
    poll_interval_ms: int = 120


def _extract_prompt_id(snapshot: dict[str, Any] | None) -> str | None:
    if not snapshot:
        return None
    prompt = snapshot.get("prompt_detected")
    if isinstance(prompt, dict):
        value = prompt.get("prompt_id")
        if isinstance(value, str) and value:
            return value
    return None


class TermHub:
    """In-memory registry for terminal websocket connections."""

    def __init__(self, manager: Any | None = None, dashboard_hijack_lease_s: int = 45) -> None:
        self._lock = asyncio.Lock()
        self._bots: dict[str, _BotTermState] = {}
        self._manager = manager
        self._dashboard_hijack_lease_s = max(1, min(int(dashboard_hijack_lease_s), 600))

    @staticmethod
    def _clamp_lease(lease_s: int) -> int:
        return max(1, min(int(lease_s), 3600))

    @staticmethod
    def _is_rest_session_active(st: _BotTermState) -> bool:
        hs = st.hijack_session
        return hs is not None and hs.lease_expires_at > time.time()

    @staticmethod
    def _is_dashboard_hijack_active(st: _BotTermState) -> bool:
        if st.hijack_owner is None:
            return False
        if st.hijack_owner_expires_at is None:
            return True
        return st.hijack_owner_expires_at > time.time()

    def _is_hijacked(self, st: _BotTermState) -> bool:
        return self._is_dashboard_hijack_active(st) or self._is_rest_session_active(st)

    async def _get(self, bot_id: str) -> _BotTermState:
        async with self._lock:
            st = self._bots.get(bot_id)
            if st is None:
                st = _BotTermState()
                self._bots[bot_id] = st
            return st

    def _set_manager_hijack(self, bot_id: str, *, enabled: bool, owner: str | None = None) -> None:
        manager = self._manager
        if manager is None:
            return
        bot = manager.bots.get(bot_id)
        if bot is None:
            return
        bot.is_hijacked = enabled
        if enabled:
            bot.hijacked_at = time.time()
            bot.hijacked_by = owner
            bot.status_detail = "PAUSED"
        else:
            bot.hijacked_at = None
            bot.hijacked_by = None
            if bot.status_detail == "PAUSED":
                bot.status_detail = None

    async def _append_event(self, bot_id: str, event_type: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = data or {}
        async with self._lock:
            st = self._bots.get(bot_id)
            if st is None:
                st = _BotTermState()
                self._bots[bot_id] = st
            st.event_seq += 1
            evt = {"seq": st.event_seq, "ts": time.time(), "type": event_type, "data": payload}
            st.events.append(evt)
            return evt

    async def _cleanup_expired_hijack(self, bot_id: str) -> bool:
        now = time.time()
        rest_expired = False
        dashboard_expired = False
        should_resume = False

        async with self._lock:
            st = self._bots.get(bot_id)
            if st is None:
                return False

            if st.hijack_session is not None and st.hijack_session.lease_expires_at <= now:
                st.hijack_session = None
                rest_expired = True

            if (
                st.hijack_owner is not None
                and st.hijack_owner_expires_at is not None
                and st.hijack_owner_expires_at <= now
            ):
                st.hijack_owner = None
                st.hijack_owner_expires_at = None
                dashboard_expired = True

            should_resume = (rest_expired or dashboard_expired) and st.hijack_owner is None and st.hijack_session is None

        if not rest_expired and not dashboard_expired:
            return False

        if should_resume:
            await self._send_worker(
                bot_id,
                {"type": "control", "action": "resume", "owner": "lease-expired", "lease_s": 0, "ts": now},
            )
            self._set_manager_hijack(bot_id, enabled=False, owner=None)

        if rest_expired:
            await self._append_event(bot_id, "hijack_lease_expired")
        if dashboard_expired:
            await self._append_event(bot_id, "hijack_owner_expired")
        await self._broadcast_hijack_state(bot_id)
        return True

    async def _get_rest_session(self, bot_id: str, hijack_id: str) -> _HijackSession | None:
        await self._cleanup_expired_hijack(bot_id)
        st = await self._get(bot_id)
        hs = st.hijack_session
        if hs is None:
            return None
        if hs.lease_expires_at <= time.time():
            return None
        if hs.hijack_id != hijack_id:
            return None
        return hs

    @staticmethod
    def _snapshot_matches(
        snapshot: dict[str, Any] | None,
        *,
        expect_prompt_id: str | None,
        expect_regex: re.Pattern[str] | None,
    ) -> bool:
        if snapshot is None:
            return False
        if expect_prompt_id:
            prompt_id = _extract_prompt_id(snapshot)
            if prompt_id != expect_prompt_id:
                return False
        if expect_regex is not None:
            screen = str(snapshot.get("screen", ""))
            if not expect_regex.search(screen):
                return False
        return True

    async def _wait_for_snapshot(self, bot_id: str, timeout_ms: int = 1500) -> dict[str, Any] | None:
        end = time.time() + max(50, timeout_ms) / 1000.0
        while time.time() < end:
            st = await self._get(bot_id)
            if st.last_snapshot is not None:
                return st.last_snapshot
            await self._request_snapshot(bot_id)
            await asyncio.sleep(0.08)
        st = await self._get(bot_id)
        return st.last_snapshot

    async def _wait_for_guard(
        self,
        bot_id: str,
        *,
        expect_prompt_id: str | None,
        expect_regex: str | None,
        timeout_ms: int,
        poll_interval_ms: int,
    ) -> tuple[bool, dict[str, Any] | None, str | None]:
        regex_obj: re.Pattern[str] | None = None
        if expect_regex:
            try:
                regex_obj = re.compile(expect_regex, re.IGNORECASE | re.MULTILINE)
            except re.error as exc:
                return False, None, f"invalid expect_regex: {exc}"

        if not expect_prompt_id and regex_obj is None:
            st = await self._get(bot_id)
            return True, st.last_snapshot, None

        end = time.time() + max(50, timeout_ms) / 1000.0
        interval = max(20, poll_interval_ms) / 1000.0
        last_snapshot: dict[str, Any] | None = None
        while time.time() < end:
            st = await self._get(bot_id)
            last_snapshot = st.last_snapshot
            if self._snapshot_matches(
                last_snapshot,
                expect_prompt_id=expect_prompt_id,
                expect_regex=regex_obj,
            ):
                return True, last_snapshot, None
            await self._request_snapshot(bot_id)
            await asyncio.sleep(interval)

        return False, last_snapshot, "prompt_guard_not_satisfied"

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
        lease_expires_at = (
            st.hijack_session.lease_expires_at
            if self._is_rest_session_active(st) and st.hijack_session is not None
            else st.hijack_owner_expires_at
        )
        for ws in list(st.browsers):
            try:
                if self._is_dashboard_hijack_active(st) and st.hijack_owner is ws:
                    owner = "me"
                elif self._is_dashboard_hijack_active(st) or self._is_rest_session_active(st):
                    owner = "other"
                else:
                    owner = None
                await ws.send_text(
                    json.dumps(
                        {
                            "type": "hijack_state",
                            "hijacked": self._is_hijacked(st),
                            "owner": owner,
                            "lease_expires_at": lease_expires_at,
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

    async def _set_hijack_owner(self, bot_id: str, owner: WebSocket | None, lease_s: int | None = None) -> None:
        async with self._lock:
            st = self._bots.get(bot_id)
            if st is None:
                st = _BotTermState()
                self._bots[bot_id] = st
            st.hijack_owner = owner
            if owner is None:
                st.hijack_owner_expires_at = None
            else:
                ttl = self._dashboard_hijack_lease_s if lease_s is None else max(1, min(int(lease_s), 600))
                st.hijack_owner_expires_at = time.time() + ttl

    async def _touch_hijack_owner(self, bot_id: str, lease_s: int | None = None) -> float | None:
        async with self._lock:
            st = self._bots.get(bot_id)
            if st is None or st.hijack_owner is None:
                return None
            ttl = self._dashboard_hijack_lease_s if lease_s is None else max(1, min(int(lease_s), 600))
            st.hijack_owner_expires_at = time.time() + ttl
            return st.hijack_owner_expires_at

    async def _is_owner(self, bot_id: str, ws: WebSocket) -> bool:
        st = await self._get(bot_id)
        return self._is_dashboard_hijack_active(st) and st.hijack_owner is ws

    async def _owner_label_for(self, bot_id: str, ws: WebSocket) -> str | None:
        st = await self._get(bot_id)
        if self._is_dashboard_hijack_active(st) and st.hijack_owner is ws:
            return "me"
        if not self._is_dashboard_hijack_active(st) and not self._is_rest_session_active(st):
            return None
        return "other"

    async def _hijack_state_msg_for(self, bot_id: str, ws: WebSocket) -> dict[str, Any]:
        st = await self._get(bot_id)
        lease_expires_at = (
            st.hijack_session.lease_expires_at
            if self._is_rest_session_active(st) and st.hijack_session is not None
            else st.hijack_owner_expires_at
        )
        return {
            "type": "hijack_state",
            "hijacked": self._is_hijacked(st),
            "owner": await self._owner_label_for(bot_id, ws),
            "lease_expires_at": lease_expires_at,
        }

    async def _request_snapshot(self, bot_id: str) -> None:
        await self._send_worker(
            bot_id,
            {"type": "snapshot_req", "req_id": str(uuid.uuid4()), "ts": time.time()},
        )

    async def _request_analysis(self, bot_id: str) -> None:
        await self._send_worker(
            bot_id,
            {"type": "analyze_req", "req_id": str(uuid.uuid4()), "ts": time.time()},
        )

    def create_router(self) -> APIRouter:
        router = APIRouter()

        @router.post("/bot/{bot_id}/hijack/acquire")
        async def hijack_acquire(bot_id: str, request: HijackAcquireRequest | None = None) -> Any:
            if request is None:
                request = HijackAcquireRequest()
            await self._cleanup_expired_hijack(bot_id)
            st = await self._get(bot_id)
            if st.worker_ws is None:
                return JSONResponse({"error": "No worker connected for this bot."}, status_code=409)
            if st.hijack_owner is not None or self._is_rest_session_active(st):
                return JSONResponse({"error": "Bot is already hijacked."}, status_code=409)

            lease_s = self._clamp_lease(request.lease_s)
            hijack_id = str(uuid.uuid4())
            now = time.time()
            ok = await self._send_worker(
                bot_id,
                {
                    "type": "control",
                    "action": "pause",
                    "owner": request.owner,
                    "lease_s": lease_s,
                    "ts": now,
                },
            )
            if not ok:
                return JSONResponse({"error": "No worker connected for this bot."}, status_code=409)

            async with self._lock:
                st2 = self._bots.get(bot_id)
                if st2 is None:
                    st2 = _BotTermState()
                    self._bots[bot_id] = st2
                st2.hijack_session = _HijackSession(
                    hijack_id=hijack_id,
                    owner=request.owner,
                    acquired_at=now,
                    lease_expires_at=now + lease_s,
                    last_heartbeat=now,
                )

            self._set_manager_hijack(bot_id, enabled=True, owner=request.owner)
            await self._append_event(
                bot_id,
                "hijack_acquired",
                {"hijack_id": hijack_id, "owner": request.owner, "lease_s": lease_s},
            )
            await self._broadcast_hijack_state(bot_id)
            return {
                "ok": True,
                "bot_id": bot_id,
                "hijack_id": hijack_id,
                "lease_expires_at": now + lease_s,
                "owner": request.owner,
            }

        @router.post("/bot/{bot_id}/hijack/{hijack_id}/heartbeat")
        async def hijack_heartbeat(
            bot_id: str,
            hijack_id: str,
            request: HijackHeartbeatRequest | None = None,
        ) -> Any:
            if request is None:
                request = HijackHeartbeatRequest()
            hs = await self._get_rest_session(bot_id, hijack_id)
            if hs is None:
                return JSONResponse({"error": "Invalid or expired hijack session."}, status_code=404)

            lease_s = self._clamp_lease(request.lease_s)
            now = time.time()
            async with self._lock:
                st = self._bots.get(bot_id)
                if st is None or st.hijack_session is None or st.hijack_session.hijack_id != hijack_id:
                    return JSONResponse({"error": "Invalid or expired hijack session."}, status_code=404)
                st.hijack_session.last_heartbeat = now
                st.hijack_session.lease_expires_at = now + lease_s

            await self._append_event(bot_id, "hijack_heartbeat", {"hijack_id": hijack_id, "lease_s": lease_s})
            await self._broadcast_hijack_state(bot_id)
            return {"ok": True, "hijack_id": hijack_id, "lease_expires_at": now + lease_s}

        @router.get("/bot/{bot_id}/hijack/{hijack_id}/snapshot")
        async def hijack_snapshot(
            bot_id: str, hijack_id: str, wait_ms: int = Query(default=1500, ge=0, le=10000)
        ) -> Any:
            hs = await self._get_rest_session(bot_id, hijack_id)
            if hs is None:
                return JSONResponse({"error": "Invalid or expired hijack session."}, status_code=404)
            snapshot = await self._wait_for_snapshot(bot_id, timeout_ms=wait_ms)
            return {
                "ok": True,
                "bot_id": bot_id,
                "hijack_id": hijack_id,
                "snapshot": snapshot,
                "prompt_id": _extract_prompt_id(snapshot),
                "lease_expires_at": hs.lease_expires_at,
            }

        @router.get("/bot/{bot_id}/hijack/{hijack_id}/events")
        async def hijack_events(
            bot_id: str,
            hijack_id: str,
            after_seq: int = Query(default=0, ge=0),
            limit: int = Query(default=200, ge=1, le=2000),
        ) -> Any:
            hs = await self._get_rest_session(bot_id, hijack_id)
            if hs is None:
                return JSONResponse({"error": "Invalid or expired hijack session."}, status_code=404)
            async with self._lock:
                st = self._bots.get(bot_id)
                if st is None:
                    rows: list[dict[str, Any]] = []
                    latest_seq = 0
                else:
                    rows = [evt for evt in list(st.events) if int(evt.get("seq", 0)) > after_seq][:limit]
                    latest_seq = st.event_seq
            return {
                "ok": True,
                "bot_id": bot_id,
                "hijack_id": hijack_id,
                "after_seq": after_seq,
                "latest_seq": latest_seq,
                "events": rows,
                "lease_expires_at": hs.lease_expires_at,
            }

        @router.post("/bot/{bot_id}/hijack/{hijack_id}/send")
        async def hijack_send(bot_id: str, hijack_id: str, request: HijackSendRequest) -> Any:
            hs = await self._get_rest_session(bot_id, hijack_id)
            if hs is None:
                return JSONResponse({"error": "Invalid or expired hijack session."}, status_code=404)
            if not request.keys:
                return JSONResponse({"error": "keys must not be empty."}, status_code=400)

            matched, snapshot, reason = await self._wait_for_guard(
                bot_id,
                expect_prompt_id=request.expect_prompt_id,
                expect_regex=request.expect_regex,
                timeout_ms=request.timeout_ms,
                poll_interval_ms=request.poll_interval_ms,
            )
            if not matched:
                return JSONResponse(
                    {
                        "error": reason or "prompt_guard_not_satisfied",
                        "current_prompt_id": _extract_prompt_id(snapshot),
                    },
                    status_code=409,
                )

            ok = await self._send_worker(bot_id, {"type": "input", "data": request.keys, "ts": time.time()})
            if not ok:
                return JSONResponse({"error": "No worker connected for this bot."}, status_code=409)

            await self._append_event(
                bot_id,
                "hijack_send",
                {
                    "hijack_id": hijack_id,
                    "keys": request.keys[:120],
                    "expect_prompt_id": request.expect_prompt_id,
                    "expect_regex": request.expect_regex,
                },
            )
            return {
                "ok": True,
                "bot_id": bot_id,
                "hijack_id": hijack_id,
                "sent": request.keys,
                "matched_prompt_id": _extract_prompt_id(snapshot),
                "lease_expires_at": hs.lease_expires_at,
            }

        @router.post("/bot/{bot_id}/hijack/{hijack_id}/step")
        async def hijack_step(bot_id: str, hijack_id: str) -> Any:
            hs = await self._get_rest_session(bot_id, hijack_id)
            if hs is None:
                return JSONResponse({"error": "Invalid or expired hijack session."}, status_code=404)
            ok = await self._send_worker(
                bot_id,
                {"type": "control", "action": "step", "owner": hs.owner, "lease_s": 0, "ts": time.time()},
            )
            if not ok:
                return JSONResponse({"error": "No worker connected for this bot."}, status_code=409)
            await self._append_event(bot_id, "hijack_step", {"hijack_id": hijack_id})
            return {"ok": True, "bot_id": bot_id, "hijack_id": hijack_id, "lease_expires_at": hs.lease_expires_at}

        @router.post("/bot/{bot_id}/hijack/{hijack_id}/release")
        async def hijack_release(bot_id: str, hijack_id: str) -> Any:
            hs = await self._get_rest_session(bot_id, hijack_id)
            if hs is None:
                return JSONResponse({"error": "Invalid or expired hijack session."}, status_code=404)
            should_resume = False
            async with self._lock:
                st = self._bots.get(bot_id)
                if st is None or st.hijack_session is None or st.hijack_session.hijack_id != hijack_id:
                    return JSONResponse({"error": "Invalid or expired hijack session."}, status_code=404)
                st.hijack_session = None
                should_resume = st.hijack_owner is None
            if should_resume:
                await self._send_worker(
                    bot_id,
                    {"type": "control", "action": "resume", "owner": hs.owner, "lease_s": 0, "ts": time.time()},
                )
                self._set_manager_hijack(bot_id, enabled=False, owner=None)
            await self._append_event(bot_id, "hijack_released", {"hijack_id": hijack_id, "owner": hs.owner})
            await self._broadcast_hijack_state(bot_id)
            return {"ok": True, "bot_id": bot_id, "hijack_id": hijack_id}

        @router.websocket("/ws/worker/{bot_id}/term")
        async def ws_worker_term(websocket: WebSocket, bot_id: str) -> None:
            await websocket.accept()
            await self._get(bot_id)
            async with self._lock:
                st2 = self._bots.get(bot_id)
                if st2 is None:
                    st2 = _BotTermState()
                    self._bots[bot_id] = st2
                st2.worker_ws = websocket
            logger.info("term_worker_connected", bot_id=bot_id)

            await self._request_snapshot(bot_id)

            try:
                while True:
                    await self._cleanup_expired_hijack(bot_id)
                    raw = await websocket.receive_text()
                    try:
                        msg = json.loads(raw)
                    except Exception:
                        continue
                    mtype = msg.get("type")
                    if mtype == "term":
                        data = msg.get("data", "")
                        if data:
                            await self._broadcast(
                                bot_id, {"type": "term", "data": data, "ts": msg.get("ts", time.time())}
                            )
                    elif mtype == "snapshot":
                        snapshot = {
                            "type": "snapshot",
                            "screen": msg.get("screen", ""),
                            "cursor": msg.get("cursor", {"x": 0, "y": 0}),
                            "cols": int(msg.get("cols", 80) or 80),
                            "rows": int(msg.get("rows", 25) or 25),
                            "screen_hash": msg.get("screen_hash", ""),
                            "cursor_at_end": bool(msg.get("cursor_at_end", True)),
                            "has_trailing_space": bool(msg.get("has_trailing_space", False)),
                            "prompt_detected": msg.get("prompt_detected"),
                            "ts": msg.get("ts", time.time()),
                        }
                        async with self._lock:
                            st3 = self._bots.get(bot_id)
                            if st3 is not None:
                                st3.last_snapshot = snapshot
                        await self._broadcast(bot_id, snapshot)
                        await self._append_event(
                            bot_id,
                            "snapshot",
                            {"prompt_id": _extract_prompt_id(snapshot), "screen_hash": snapshot.get("screen_hash")},
                        )
                    elif mtype == "analysis":
                        await self._broadcast(
                            bot_id,
                            {
                                "type": "analysis",
                                "formatted": msg.get("formatted", ""),
                                "raw": msg.get("raw"),
                                "ts": msg.get("ts", time.time()),
                            },
                        )
                    elif mtype == "status":
                        await self._broadcast(bot_id, msg)
                        await self._append_event(bot_id, "worker_status", {"status": msg})
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

            await websocket.send_text(
                json.dumps(
                    {
                        "type": "hello",
                        "bot_id": bot_id,
                        "can_hijack": True,
                        "hijacked": self._is_hijacked(st),
                        "hijacked_by_me": self._is_dashboard_hijack_active(st) and st.hijack_owner is websocket,
                    },
                    ensure_ascii=True,
                )
            )
            await websocket.send_text(json.dumps(await self._hijack_state_msg_for(bot_id, websocket), ensure_ascii=True))

            if st.last_snapshot is not None:
                await websocket.send_text(json.dumps(st.last_snapshot, ensure_ascii=True))
            else:
                await self._request_snapshot(bot_id)

            try:
                while True:
                    await self._cleanup_expired_hijack(bot_id)
                    raw = await websocket.receive_text()
                    try:
                        msg = json.loads(raw)
                    except Exception:
                        continue
                    mtype = msg.get("type")
                    if mtype == "snapshot_req":
                        if await self._is_owner(bot_id, websocket):
                            await self._touch_hijack_owner(bot_id)
                        await self._request_snapshot(bot_id)
                    elif mtype == "analyze_req":
                        if await self._is_owner(bot_id, websocket):
                            await self._touch_hijack_owner(bot_id)
                        await self._request_analysis(bot_id)
                    elif mtype == "heartbeat":
                        if await self._is_owner(bot_id, websocket):
                            lease_expires_at = await self._touch_hijack_owner(bot_id)
                            await websocket.send_text(
                                json.dumps(
                                    {
                                        "type": "heartbeat_ack",
                                        "lease_expires_at": lease_expires_at,
                                        "ts": time.time(),
                                    },
                                    ensure_ascii=True,
                                )
                            )
                            await self._broadcast_hijack_state(bot_id)
                    elif mtype == "hijack_request":
                        st_now = await self._get(bot_id)
                        if st_now.hijack_owner is None and not self._is_rest_session_active(st_now):
                            await self._set_hijack_owner(bot_id, websocket, lease_s=self._dashboard_hijack_lease_s)
                            ok = await self._send_worker(
                                bot_id,
                                {"type": "control", "action": "pause", "owner": "dashboard", "lease_s": 0, "ts": time.time()},
                            )
                            if not ok:
                                await self._set_hijack_owner(bot_id, None)
                                await websocket.send_text(
                                    json.dumps(
                                        {"type": "error", "message": "No worker connected for this bot."},
                                        ensure_ascii=True,
                                    )
                                )
                            await self._broadcast_hijack_state(bot_id)
                            self._set_manager_hijack(bot_id, enabled=True, owner="dashboard")
                            await self._append_event(bot_id, "hijack_acquired", {"owner": "dashboard_ws"})
                        else:
                            await websocket.send_text(
                                json.dumps(
                                    {"type": "error", "message": "Already hijacked by another client."},
                                    ensure_ascii=True,
                                )
                            )
                            await websocket.send_text(
                                json.dumps(await self._hijack_state_msg_for(bot_id, websocket), ensure_ascii=True)
                            )
                    elif mtype == "hijack_step":
                        if await self._is_owner(bot_id, websocket):
                            await self._touch_hijack_owner(bot_id)
                            ok = await self._send_worker(
                                bot_id,
                                {"type": "control", "action": "step", "owner": "dashboard", "lease_s": 0, "ts": time.time()},
                            )
                            if not ok:
                                await websocket.send_text(
                                    json.dumps(
                                        {"type": "error", "message": "No worker connected for this bot."},
                                        ensure_ascii=True,
                                    )
                                )
                            else:
                                await self._append_event(bot_id, "hijack_step", {"owner": "dashboard_ws"})
                    elif mtype == "hijack_release":
                        if await self._is_owner(bot_id, websocket):
                            await self._set_hijack_owner(bot_id, None)
                            await self._send_worker(
                                bot_id,
                                {
                                    "type": "control",
                                    "action": "resume",
                                    "owner": "dashboard",
                                    "lease_s": 0,
                                    "ts": time.time(),
                                },
                            )
                            await self._broadcast_hijack_state(bot_id)
                            st_after = await self._get(bot_id)
                            if not self._is_rest_session_active(st_after):
                                self._set_manager_hijack(bot_id, enabled=False, owner=None)
                            await self._append_event(bot_id, "hijack_released", {"owner": "dashboard_ws"})
                    elif mtype == "input":
                        if await self._is_owner(bot_id, websocket):
                            await self._touch_hijack_owner(bot_id)
                            data = msg.get("data", "")
                            if data:
                                ok = await self._send_worker(bot_id, {"type": "input", "data": data, "ts": time.time()})
                                if not ok:
                                    await websocket.send_text(
                                        json.dumps(
                                            {"type": "error", "message": "Worker connection lost."}, ensure_ascii=True
                                        )
                                    )
                                else:
                                    await self._append_event(
                                        bot_id,
                                        "hijack_send",
                                        {"owner": "dashboard_ws", "keys": data[:120]},
                                    )
                        else:
                            continue
            except WebSocketDisconnect:
                pass
            except Exception as e:
                logger.warning("term_browser_ws_error", bot_id=bot_id, error=str(e))
            finally:
                was_owner = await self._is_owner(bot_id, websocket)
                async with self._lock:
                    st3 = self._bots.get(bot_id)
                    if st3 is not None:
                        st3.browsers.discard(websocket)
                        if was_owner and st3.hijack_owner is websocket:
                            st3.hijack_owner = None
                if was_owner:
                    await self._send_worker(
                        bot_id,
                        {"type": "control", "action": "resume", "owner": "dashboard", "lease_s": 0, "ts": time.time()},
                    )
                    await self._broadcast_hijack_state(bot_id)
                    st_after = await self._get(bot_id)
                    if not self._is_rest_session_active(st_after):
                        self._set_manager_hijack(bot_id, enabled=False, owner=None)
                    await self._append_event(bot_id, "hijack_released", {"owner": "dashboard_ws_disconnect"})

        return router


def setup(manager: Any) -> APIRouter:
    """Create (or reuse) a TermHub attached to the manager instance."""
    hub = getattr(manager, "term_hub", None)
    if hub is None:
        hub = TermHub(manager=manager)
        manager.term_hub = hub
    else:
        hub._manager = manager
    return hub.create_router()
