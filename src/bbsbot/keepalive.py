from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


class KeepaliveStatus(BaseModel):
    interval_s: float | None
    keys: str
    running: bool


class KeepaliveController:
    def __init__(
        self,
        send_cb: Callable[[str], Awaitable[str]],
        is_connected: Callable[[], bool],
    ) -> None:
        self._send_cb = send_cb
        self._is_connected = is_connected
        self._interval_s: float | None = 30.0
        self._keys = "\r"
        self._task: asyncio.Task[None] | None = None

    async def configure(self, interval_s: float | None, keys: str = "\r") -> str:
        if interval_s is not None and interval_s <= 0:
            self._interval_s = None
        else:
            self._interval_s = interval_s
        self._keys = keys
        if self._is_connected():
            if self._interval_s:
                self._start()
            else:
                await self._stop()
        return "ok"

    def on_connect(self) -> None:
        if self._interval_s:
            self._start()

    async def on_disconnect(self) -> None:
        await self._stop()

    def status(self) -> dict[str, Any]:
        running = self._task is not None and not self._task.done()
        return KeepaliveStatus(interval_s=self._interval_s, keys=self._keys, running=running).model_dump()

    def _start(self) -> None:
        # Note: _stop is now async, but we can't await in sync _start.
        # Instead, cancel synchronously and let caller handle cleanup if needed.
        if self._task and not self._task.done():
            self._task.cancel()
        if not self._interval_s:
            return
        self._task = asyncio.create_task(self._loop())

    async def _stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        self._task = None

    async def _loop(self) -> None:
        try:
            while self._is_connected() and self._interval_s:
                await asyncio.sleep(self._interval_s)
                if not self._is_connected():
                    break
                await self._send_cb(self._keys)
        except asyncio.CancelledError:
            return
