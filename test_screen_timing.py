"""Test to understand screen buffer timing and get_screen() behavior."""

from __future__ import annotations

import asyncio
import pyte

class MockTransport:
    """Mock transport that simulates BBS menu display."""

    def __init__(self):
        self.send_count = 0
        self.menu_sent = False

    async def receive(self, max_bytes, timeout_ms):
        """Simulate receiving data from BBS."""

        # First read: show menu
        if not self.menu_sent:
            self.menu_sent = True
            menu = "<A> Attack this Port\r\n<T> Trade at this Port\r\n<Q> Quit, nevermind\r\n\r\nEnter your choice [T] :"
            return menu.encode('cp437')

        # Subsequent reads: nothing new
        await asyncio.sleep(timeout_ms / 1000)
        return b""

    def is_connected(self):
        return True

class MockEmulator:
    """Mock emulator that uses pyte."""

    def __init__(self):
        self._screen = pyte.Screen(80, 25)
        self._stream = pyte.Stream(self._screen)

    def process(self, data: bytes):
        text = data.decode('cp437', errors='replace')
        self._stream.feed(text)

    def get_snapshot(self):
        screen_text = "\n".join(self._screen.display)
        return {
            "screen": screen_text,
            "screen_hash": "test",
            "cursor": {"x": self._screen.cursor.x, "y": self._screen.cursor.y},
        }

    def get_screen(self):
        """Direct screen access - no I/O."""
        return "\n".join(self._screen.display)

async def test_timing_issue():
    """Test the timing issue between get_screen() and read()."""

    transport = MockTransport()
    emulator = MockEmulator()

    print("=== Scenario 1: Call get_screen() before read() ===")
    print("Initial screen buffer:")
    screen1 = emulator.get_screen()
    print(repr(screen1[:100]))
    print()

    print("Now calling read() to get menu data...")
    data = await transport.receive(max_bytes=1024, timeout_ms=100)
    emulator.process(data)
    snapshot = emulator.get_snapshot()
    print("Screen after read():")
    print(snapshot["screen"][:200])
    print()

    print("=== Scenario 2: Call get_screen() after read() ===")
    transport2 = MockTransport()
    emulator2 = MockEmulator()

    # Read first to populate buffer
    data = await transport2.receive(max_bytes=1024, timeout_ms=100)
    emulator2.process(data)

    # Now get_screen() should show the menu
    screen2 = emulator2.get_screen()
    print("Screen via get_screen():")
    print(screen2[:200])
    print()

    print("=== Scenario 3: Stale buffer problem ===")
    print("If bot previously saw 'Old Content' and now BBS sent menu:")
    transport3 = MockTransport()
    emulator3 = MockEmulator()

    # Simulate old content in buffer
    emulator3.process(b"Old content from previous action\r\n")
    print("Stale buffer content:")
    print(emulator3.get_screen()[:50])

    # Now menu is sent by BBS, but bot calls get_screen() BEFORE read()
    print("\nBot calls get_screen() before reading new data:")
    screen_stale = emulator3.get_screen()
    print(repr(screen_stale[:50]))

    # Menu is actually sent but not yet read
    print("\nNow read() is called and processes the menu:")
    data = await transport3.receive(max_bytes=1024, timeout_ms=100)
    emulator3.process(data)
    screen_fresh = emulator3.get_screen()
    print(screen_fresh[:200])

if __name__ == "__main__":
    asyncio.run(test_timing_issue())
