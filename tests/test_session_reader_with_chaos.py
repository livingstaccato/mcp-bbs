from __future__ import annotations

import pytest

from bbsbot.core.session_manager import SessionManager
from tests.mock_bbs_server import MockBBS


@pytest.mark.asyncio
async def test_session_reader_disconnect_injected_notifies_waiters() -> None:
    async with MockBBS(["\r\nWelcome\r\n"]) as server:
        manager = SessionManager(max_sessions=1)
        sid = await manager.create_session(
            host=server.host,
            port=server.port,
            timeout=2.0,
            chaos={"seed": 1, "disconnect_every_n_receives": 1, "label": "test"},
        )
        session = await manager.get_session(sid)

        ok = await session.wait_for_update(timeout_ms=2000)
        assert ok is False

        snap = session.snapshot()
        assert snap.get("disconnected") is True

        await manager.close_session(sid)

