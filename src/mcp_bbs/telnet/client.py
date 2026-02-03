from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pyte
import structlog

from mcp_bbs.config import get_default_knowledge_root
from mcp_bbs.keepalive import KeepaliveController
from mcp_bbs.learn import apply_auto_discover, apply_auto_learn
from mcp_bbs.telnet.protocol import (
    CP437,
    DO,
    DONT,
    OPT_BINARY,
    OPT_ECHO,
    OPT_NAWS,
    OPT_SGA,
    OPT_TTYPE,
    WILL,
    WONT,
    TelnetProtocol,
)

log = structlog.get_logger()


@dataclass
class Session:
    reader: Any
    writer: Any
    screen: pyte.Screen
    stream: pyte.Stream
    cols: int
    rows: int
    term: str
    host: str
    port: int
    session_id: int


class TelnetClient:
    def __init__(self) -> None:
        self._session: Session | None = None
        self._rx_buf = bytearray()
        self._log_path: Path | None = None
        self._log_fp: Any = None
        self._negotiated: dict[str, set[int]] = {
            "do": set(),
            "dont": set(),
            "will": set(),
            "wont": set(),
        }
        self._protocol: TelnetProtocol | None = None
        self._auto_learn_enabled = False
        self._auto_prompt_rules: list[dict[str, str]] = []
        self._auto_menu_rules: list[dict[str, str]] = []
        self._auto_learn_seen: set[tuple[str, str]] = set()
        self._learn_namespace: str | None = None
        self._knowledge_root = get_default_knowledge_root()
        self._shared_dir = self._knowledge_root / "shared" / "bbs"
        self._context: dict[str, str] = {}
        self._session_counter = 0
        self._last_rx_ts: float | None = None
        self._last_tx_ts: float | None = None
        self._keepalive = KeepaliveController(self.send, self._is_connected)
        self._auto_discover_menus = False

    async def connect(
        self,
        host: str,
        port: int,
        cols: int,
        rows: int,
        term: str,
        send_newline: bool,
        reuse: bool,
    ) -> str:
        if self._session:
            if reuse and self._session.host == host and self._session.port == port:
                if self._session.cols != cols or self._session.rows != rows:
                    await self.set_size(cols, rows)
                if send_newline:
                    await self.send("\r\n")
                self._log_event(
                    "connect_reuse",
                    {
                        "host": host,
                        "port": port,
                        "cols": cols,
                        "rows": rows,
                        "term": term,
                        "codepage": CP437,
                        "send_newline": send_newline,
                    },
                )
                return "ok"
            await self.disconnect()
        reader, writer = await asyncio.open_connection(host, port)
        screen = pyte.Screen(cols, rows)
        stream = pyte.Stream(screen)
        self._session_counter += 1
        self._session = Session(
            reader=reader,
            writer=writer,
            screen=screen,
            stream=stream,
            cols=cols,
            rows=rows,
            term=term,
            host=host,
            port=port,
            session_id=self._session_counter,
        )
        self._protocol = TelnetProtocol(writer, self._negotiated)
        # Send telnet commands immediately so BBS knows we're a telnet client
        # Standard telnet clients announce their capabilities on connect
        await self._protocol.send_do(OPT_SGA)
        await self._protocol.send_do(OPT_ECHO)
        self._log_event(
            "connect",
            {
                "host": host,
                "port": port,
                "cols": cols,
                "rows": rows,
                "term": term,
                "codepage": CP437,
                "send_newline": send_newline,
            },
        )
        if send_newline:
            await self.send("\r\n")
        self._keepalive.on_connect()
        return "ok"

    async def disconnect(self) -> str:
        if self._session:
            await self._handle_disconnect("client_disconnect")
        return "ok"

    async def send(self, keys: str) -> str:
        session = self._require_session()
        payload = keys.encode(CP437, errors="replace")
        log.debug(
            "telnet_send",
            keys=keys,
            keys_len=len(keys),
            payload_len=len(payload),
            payload_b64=base64.b64encode(payload).decode("ascii"),
        )
        try:
            session.writer.write(payload)
            await session.writer.drain()
        except (ConnectionResetError, BrokenPipeError):
            await self._handle_disconnect("send_failed")
            return "disconnected"
        self._last_tx_ts = time.time()
        self._log_event(
            "send",
            {
                "keys": keys,
                "bytes_b64": base64.b64encode(payload).decode("ascii"),
            },
        )
        return "ok"

    async def read(self, timeout_ms: int, max_bytes: int) -> dict[str, Any]:
        data = await self._read_raw(timeout_ms, max_bytes)
        if data is None:
            snapshot = self._snapshot_disconnected()
            self._log_event("read", snapshot)
            return snapshot
        if data:
            self._feed_terminal(data)
            self._last_rx_ts = time.time()
        full_snapshot, clean_snapshot = self._snapshot(data)
        self._log_event("read", full_snapshot)  # Log full data to JSONL
        return clean_snapshot  # Return clean data to MCP client

    async def read_until_nonblank(self, timeout_ms: int, interval_ms: int, max_bytes: int) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_ms / 1000
        last_snapshot: dict[str, Any] = {}
        while time.monotonic() < deadline:
            last_snapshot = await self.read(interval_ms, max_bytes)
            if last_snapshot.get("disconnected"):
                return last_snapshot
            screen = last_snapshot.get("screen", "")
            if screen and screen.strip():
                return last_snapshot
        return last_snapshot or await self.read(interval_ms, max_bytes)

    async def read_until_pattern(
        self,
        pattern: str,
        timeout_ms: int,
        interval_ms: int,
        max_bytes: int,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_ms / 1000
        regex = re.compile(pattern, re.MULTILINE)
        last_snapshot: dict[str, Any] = {}
        while time.monotonic() < deadline:
            last_snapshot = await self.read(interval_ms, max_bytes)
            if last_snapshot.get("disconnected"):
                last_snapshot["matched"] = False
                return last_snapshot
            screen = last_snapshot.get("screen", "")
            if screen and regex.search(screen):
                last_snapshot["matched"] = True
                return last_snapshot
        if last_snapshot:
            last_snapshot["matched"] = False
            return last_snapshot
        result = await self.read(interval_ms, max_bytes)
        result["matched"] = False
        return result

    async def expect(self, pattern: str, timeout_ms: int, interval_ms: int) -> dict[str, Any]:
        return await self.read_until_pattern(pattern, timeout_ms, interval_ms, 8192)

    async def wake(self, timeout_ms: int, interval_ms: int, max_bytes: int, keys_sequence: list[str]) -> dict[str, Any]:
        last_snapshot = await self.read(interval_ms, max_bytes)
        last_hash = last_snapshot.get("screen_hash", "")
        for keys in keys_sequence:
            await self.send(keys)
            snapshot = await self.read_until_nonblank(timeout_ms, interval_ms, max_bytes)
            screen_hash = snapshot.get("screen_hash", "")
            if screen_hash and screen_hash != last_hash:
                return snapshot
            last_snapshot = snapshot
            last_hash = screen_hash
        return last_snapshot

    async def set_size(self, cols: int, rows: int) -> str:
        session = self._require_session()
        if not self._protocol:
            raise RuntimeError("protocol not initialized")
        session.cols = cols
        session.rows = rows
        session.screen.resize(cols, rows)
        await self._protocol.send_naws(cols, rows)
        self._log_event("resize", {"cols": cols, "rows": rows})
        return "ok"

    def set_auto_learn(self, enabled: bool) -> str:
        self._auto_learn_enabled = enabled
        return "ok"

    def set_auto_prompt_rules(self, rules: list[dict[str, str]]) -> str:
        self._auto_prompt_rules = rules
        return "ok"

    def set_auto_menu_rules(self, rules: list[dict[str, str]]) -> str:
        self._auto_menu_rules = rules
        return "ok"

    def set_auto_discover_menus(self, enabled: bool) -> str:
        self._auto_discover_menus = enabled
        return "ok"

    def set_learn_namespace(self, namespace: str | None) -> str:
        self._learn_namespace = namespace
        return "ok"

    def set_knowledge_root(self, path: str) -> str:
        self._knowledge_root = Path(path)
        self._shared_dir = self._knowledge_root / "shared" / "bbs"
        return "ok"

    def get_knowledge_root(self) -> str:
        return str(self._knowledge_root)

    def set_context(self, context: dict[str, str]) -> str:
        self._context = {str(k): str(v) for k, v in context.items()}
        return "ok"

    def clear_context(self) -> str:
        self._context = {}
        return "ok"

    def status(self) -> dict[str, Any]:
        return {
            "connected": self._session is not None,
            "cols": self._session.cols if self._session else None,
            "rows": self._session.rows if self._session else None,
            "term": self._session.term if self._session else None,
            "host": self._session.host if self._session else None,
            "port": self._session.port if self._session else None,
            "session_id": self._session.session_id if self._session else None,
            "last_rx_ts": self._last_rx_ts,
            "last_tx_ts": self._last_tx_ts,
            "log_path": str(self._log_path) if self._log_path else None,
            "context": dict(self._context),
            "keepalive": self._keepalive.status(),
        }

    def log_start(self, path: str) -> str:
        self.log_stop()
        self._log_path = Path(path)
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log_fp = self._log_path.open("a", encoding="utf-8")
        header = {
            "path": str(self._log_path),
            "started_at": time.time(),
            "negotiated": {key: sorted(value) for key, value in self._negotiated.items()},
        }
        self._log_event("log_start", header)
        return "ok"

    def log_stop(self) -> str:
        if self._log_fp:
            self._log_event("log_stop", {})
            self._log_fp.close()
        self._log_fp = None
        self._log_path = None
        return "ok"

    def log_note(self, data: dict[str, Any]) -> str:
        self._log_event("note", data)
        return "ok"

    def learn_base_dir(self) -> Path:
        if not self._learn_namespace:
            return self._shared_dir
        return self._knowledge_root / "games" / self._learn_namespace / "docs"

    def auto_learn(self, snapshot: dict[str, Any]) -> None:
        screen = snapshot.get("screen", "")
        screen_hash = snapshot.get("screen_hash", "")
        apply_auto_learn(
            screen,
            screen_hash,
            self.learn_base_dir(),
            self._auto_prompt_rules,
            self._auto_menu_rules,
            self._auto_learn_seen,
        )
        if self._auto_discover_menus:
            apply_auto_discover(screen, screen_hash, self.learn_base_dir(), self._auto_learn_seen)

    def _require_session(self) -> Session:
        if not self._session:
            raise RuntimeError("not connected")
        return self._session

    async def _read_raw(self, timeout_ms: int, max_bytes: int) -> bytes | None:
        session = self._require_session()
        if not self._protocol:
            raise RuntimeError("protocol not initialized")
        try:
            chunk = await asyncio.wait_for(session.reader.read(max_bytes), timeout_ms / 1000)
        except TimeoutError:
            return b""
        except (ConnectionResetError, BrokenPipeError):
            await self._handle_disconnect("read_failed")
            return None
        if not chunk:
            await self._handle_disconnect("eof")
            return None
        self._rx_buf.extend(chunk)
        data = bytes(self._rx_buf)
        self._rx_buf.clear()
        return self._handle_telnet(data)

    def _handle_telnet(self, data: bytes) -> bytes:
        if not self._protocol:
            return data
        i = 0
        while i < len(data):
            if data[i] == 255 and i + 1 < len(data):
                cmd = data[i + 1]
                if cmd in (DO, DONT, WILL, WONT) and i + 2 < len(data):
                    asyncio.create_task(self._negotiate(cmd, data[i + 2]))
                    i += 3
                    continue
                elif cmd == 250 and (end := data.find(bytes([255, 240]), i + 2)) != -1:
                    asyncio.create_task(self._handle_subnegotiation(data[i + 2 : end]))
                    i = end + 2
                    continue
            i += 1
        return self._protocol.strip_telnet_commands(data)

    async def _negotiate(self, cmd: int, opt: int) -> None:
        if not self._protocol:
            return
        if not self._session:
            return
        if cmd == DO:
            self._negotiated["do"].add(opt)
        elif cmd == DONT:
            self._negotiated["dont"].add(opt)
        elif cmd == WILL:
            self._negotiated["will"].add(opt)
        elif cmd == WONT:
            self._negotiated["wont"].add(opt)
        self._log_event("negotiate", {"cmd": cmd, "opt": opt})
        try:
            if cmd == DO:
                if opt in (OPT_BINARY, OPT_SGA):
                    await self._protocol.send_will(opt)
                    return
                if opt == OPT_NAWS:
                    await self._protocol.send_will(opt)
                    await self._protocol.send_naws(self._session.cols, self._session.rows)
                    return
                if opt == OPT_TTYPE:
                    await self._protocol.send_will(opt)
                    await self._protocol.send_ttype(self._session.term)
                    return
                await self._protocol.send_wont(opt)
                return
            if cmd == DONT:
                await self._protocol.send_wont(opt)
                return
            if cmd == WILL:
                if opt in (OPT_ECHO, OPT_SGA, OPT_BINARY):
                    await self._protocol.send_do(opt)
                    return
                await self._protocol.send_dont(opt)
                return
            if cmd == WONT:
                await self._protocol.send_dont(opt)
        except (ConnectionResetError, BrokenPipeError):
            return

    async def _handle_subnegotiation(self, sub: bytes) -> None:
        if not sub or not self._protocol or not self._session:
            return
        if sub[0] == OPT_TTYPE and len(sub) > 1 and sub[1] == 1:
            await self._protocol.send_ttype(self._session.term)

    def _feed_terminal(self, data: bytes) -> None:
        session = self._require_session()
        text = data.decode(CP437, errors="replace")
        session.stream.feed(text)

    def _snapshot(self, data: bytes) -> tuple[dict[str, Any], dict[str, Any]]:
        session = self._require_session()
        screen_text = "\n".join(session.screen.display)
        screen_hash = hashlib.sha256(screen_text.encode("utf-8")).hexdigest()

        # Full snapshot for JSONL logging
        full_snapshot = {
            "raw": data.decode(CP437, errors="replace"),
            "raw_bytes_b64": base64.b64encode(data).decode("ascii"),
            "screen": screen_text,
            "screen_hash": screen_hash,
            "cursor": {"x": session.screen.cursor.x, "y": session.screen.cursor.y},
            "cols": session.cols,
            "rows": session.rows,
            "term": session.term,
        }

        if self._auto_learn_enabled:
            self.auto_learn(full_snapshot)

        # Clean snapshot for MCP tool response (without raw data)
        clean_snapshot = {
            "screen": screen_text,
            "screen_hash": screen_hash,
            "cursor": {"x": session.screen.cursor.x, "y": session.screen.cursor.y},
            "cols": session.cols,
            "rows": session.rows,
            "term": session.term,
        }

        return full_snapshot, clean_snapshot

    def _snapshot_disconnected(self) -> dict[str, Any]:
        return {
            "raw": "",
            "raw_bytes_b64": "",
            "screen": "",
            "screen_hash": "",
            "cursor": {"x": 0, "y": 0},
            "cols": None,
            "rows": None,
            "term": None,
            "disconnected": True,
        }

    def _log_event(self, event: str, data: dict[str, Any]) -> None:
        if not self._log_fp:
            return
        record = {"ts": time.time(), "event": event, "data": data}
        if self._session:
            record["session_id"] = self._session.session_id
        if self._context:
            ctx = dict(self._context)
            record["ctx"] = ctx
            if "menu" in ctx:
                record["menu"] = ctx["menu"]
            if "action" in ctx:
                record["action"] = ctx["action"]
        self._log_fp.write(json.dumps(record, ensure_ascii=True) + "\n")
        self._log_fp.flush()

    def set_keepalive(self, interval_s: float | None, keys: str = "\r") -> str:
        return self._keepalive.configure(interval_s, keys)

    def _is_connected(self) -> bool:
        return self._session is not None

    async def _handle_disconnect(self, reason: str) -> None:
        if not self._session:
            return
        self._keepalive.on_disconnect()
        try:
            self._session.writer.close()
            await self._session.writer.wait_closed()
        except (ConnectionResetError, BrokenPipeError, RuntimeError):
            pass
        self._session = None
        self._rx_buf.clear()
        self._log_event("disconnect", {"reason": reason})
