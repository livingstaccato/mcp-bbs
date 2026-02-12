# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for IAC byte escaping in telnet transport."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from bbsbot.transport.telnet import TelnetTransport


@pytest.mark.asyncio
async def test_iac_escaping_in_send() -> None:
    """Test that IAC bytes (0xFF) are properly escaped when sending."""
    transport = TelnetTransport()

    # Mock writer
    mock_writer = AsyncMock()
    mock_writer.write = Mock()
    mock_writer.drain = AsyncMock()
    mock_writer.is_closing = Mock(return_value=False)

    transport._writer = mock_writer

    # Send data with IAC byte (0xFF)
    test_data = b"Hello\xffWorld"
    await transport.send(test_data)

    # Verify IAC was escaped (0xFF -> 0xFF 0xFF)
    mock_writer.write.assert_called_once()
    written_data = mock_writer.write.call_args[0][0]
    assert written_data == b"Hello\xff\xffWorld"


@pytest.mark.asyncio
async def test_iac_escaping_multiple_bytes() -> None:
    """Test escaping multiple IAC bytes."""
    transport = TelnetTransport()

    mock_writer = AsyncMock()
    mock_writer.write = Mock()
    mock_writer.drain = AsyncMock()
    mock_writer.is_closing = Mock(return_value=False)

    transport._writer = mock_writer

    # Send data with multiple IAC bytes
    test_data = b"\xff\xff\xff"
    await transport.send(test_data)

    written_data = mock_writer.write.call_args[0][0]
    # Each 0xFF should become 0xFF 0xFF
    assert written_data == b"\xff\xff\xff\xff\xff\xff"


@pytest.mark.asyncio
async def test_iac_escaping_no_iac_bytes() -> None:
    """Test that data without IAC bytes passes through unchanged."""
    transport = TelnetTransport()

    mock_writer = AsyncMock()
    mock_writer.write = Mock()
    mock_writer.drain = AsyncMock()
    mock_writer.is_closing = Mock(return_value=False)

    transport._writer = mock_writer

    # Send normal data without IAC
    test_data = b"Normal text without IAC bytes"
    await transport.send(test_data)

    written_data = mock_writer.write.call_args[0][0]
    assert written_data == test_data


@pytest.mark.asyncio
async def test_iac_escaping_binary_data() -> None:
    """Test escaping IAC in binary data (e.g., file transfer)."""
    transport = TelnetTransport()

    mock_writer = AsyncMock()
    mock_writer.write = Mock()
    mock_writer.drain = AsyncMock()
    mock_writer.is_closing = Mock(return_value=False)

    transport._writer = mock_writer

    # Binary data with IAC byte in the middle
    test_data = b"\xfe\xff\x00"  # [0xFE, 0xFF, 0x00]
    await transport.send(test_data)

    written_data = mock_writer.write.call_args[0][0]
    # 0xFF should be escaped
    assert written_data == b"\xfe\xff\xff\x00"


@pytest.mark.asyncio
async def test_iac_unescaping_in_receive() -> None:
    """Test that doubled IAC bytes are unescaped when receiving."""
    transport = TelnetTransport()

    # Test data with escaped IAC (0xFF 0xFF -> 0xFF)
    raw_data = b"Hello\xff\xffWorld"

    # Process through strip_telnet_commands
    cleaned = transport._strip_telnet_commands(raw_data)

    # Should unescape to single 0xFF
    assert cleaned == b"Hello\xffWorld"


@pytest.mark.asyncio
async def test_iac_property_based() -> None:
    """Property-based test: send -> escape -> unescape should equal original."""
    transport = TelnetTransport()

    # Test various byte patterns
    test_patterns = [
        b"\xff",
        b"\xff\xff",
        b"text\xffmore",
        b"\xff" * 10,
        bytes(range(256)),  # All byte values
    ]

    for original in test_patterns:
        # Escape (as done in send)
        escaped = original.replace(b"\xff", b"\xff\xff")

        # Unescape (as done in strip_telnet_commands)
        unescaped = transport._strip_telnet_commands(escaped)

        # Should match original
        assert unescaped == original, f"Failed for pattern: {original!r}"


@pytest.mark.asyncio
async def test_iac_with_telnet_commands() -> None:
    """Test IAC escaping doesn't interfere with telnet command IAC bytes."""
    transport = TelnetTransport()

    # Data: "text" + IAC DO ECHO (telnet command) + data IAC byte + "more"
    # Telnet command IAC should NOT be doubled
    # Data IAC should be doubled in send, single in receive
    raw_data = b"text\xff\xfd\x01\xff\xffmore"

    # Strip telnet commands - should remove IAC DO ECHO, unescape data IAC
    cleaned = transport._strip_telnet_commands(raw_data)

    # Should have: "text" + single IAC byte + "more"
    assert cleaned == b"text\xffmore"
