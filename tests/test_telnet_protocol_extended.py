"""Extended tests for telnet protocol edge cases."""

from __future__ import annotations

import pytest

from mcp_bbs.telnet.protocol import (
    DO,
    DONT,
    IAC,
    OPT_BINARY,
    SB,
    SE,
    WILL,
    TelnetProtocol,
)


@pytest.mark.asyncio
async def test_protocol_duplicate_negotiation(mock_writer) -> None:
    """Test that duplicate negotiations are not sent."""
    negotiated = {"do": set(), "dont": set(), "will": set(), "wont": set()}
    protocol = TelnetProtocol(mock_writer, negotiated)

    # Send WILL twice
    await protocol.send_will(OPT_BINARY)
    await protocol.send_will(OPT_BINARY)

    # Should only be called once
    assert mock_writer.write.call_count == 1


@pytest.mark.asyncio
async def test_protocol_writer_closing(mock_writer) -> None:
    """Test protocol behavior when writer is closing."""
    negotiated = {"do": set(), "dont": set(), "will": set(), "wont": set()}
    protocol = TelnetProtocol(mock_writer, negotiated)

    # Mock writer as closing
    mock_writer.is_closing.return_value = True

    # Should not write
    await protocol.send_will(OPT_BINARY)
    mock_writer.write.assert_not_called()


@pytest.mark.asyncio
async def test_protocol_connection_error(mock_writer) -> None:
    """Test protocol handling of connection errors."""
    negotiated = {"do": set(), "dont": set(), "will": set(), "wont": set()}
    protocol = TelnetProtocol(mock_writer, negotiated)

    # Mock drain to raise error
    mock_writer.drain.side_effect = ConnectionResetError()

    # Should not raise - error is caught
    await protocol.send_will(OPT_BINARY)


def test_strip_incomplete_command(mock_writer) -> None:
    """Test stripping incomplete telnet commands."""
    negotiated = {"do": set(), "dont": set(), "will": set(), "wont": set()}
    protocol = TelnetProtocol(mock_writer, negotiated)

    # Incomplete DO command at end
    data = b"Hello" + bytes([IAC, DO])
    result = protocol.strip_telnet_commands(data)
    assert result == b"Hello"


def test_strip_incomplete_subnegotiation(mock_writer) -> None:
    """Test stripping incomplete subnegotiation."""
    negotiated = {"do": set(), "dont": set(), "will": set(), "wont": set()}
    protocol = TelnetProtocol(mock_writer, negotiated)

    # Incomplete subnegotiation (no SE)
    data = b"Test" + bytes([IAC, SB, OPT_BINARY, 1, 2, 3])
    result = protocol.strip_telnet_commands(data)
    assert result == b"Test"


def test_strip_multiple_commands(mock_writer) -> None:
    """Test stripping multiple telnet commands."""
    negotiated = {"do": set(), "dont": set(), "will": set(), "wont": set()}
    protocol = TelnetProtocol(mock_writer, negotiated)

    # Multiple commands
    data = (
        b"Start"
        + bytes([IAC, WILL, OPT_BINARY])
        + b"Middle"
        + bytes([IAC, DO, OPT_BINARY])
        + b"End"
    )
    result = protocol.strip_telnet_commands(data)
    assert result == b"StartMiddleEnd"


def test_parse_mixed_commands() -> None:
    """Test parsing mixed telnet commands."""
    from mcp_bbs.telnet.protocol import parse_telnet_commands

    data = bytes([IAC, SB, OPT_BINARY, IAC, SE, IAC, WILL, OPT_BINARY])
    commands = parse_telnet_commands(data)

    assert len(commands) == 3
    assert commands[0] == ("SB", None)
    assert commands[1] == ("SE", None)
    assert commands[2] == ("WILL", OPT_BINARY)


@pytest.mark.asyncio
async def test_send_ttype(mock_writer) -> None:
    """Test sending terminal type."""
    negotiated = {"do": set(), "dont": set(), "will": set(), "wont": set()}
    protocol = TelnetProtocol(mock_writer, negotiated)

    await protocol.send_ttype("ANSI")

    # Should send SB with terminal type
    mock_writer.write.assert_called_once()
    call_args = mock_writer.write.call_args[0][0]
    assert IAC in call_args
    assert SB in call_args
    assert b"ANSI" in call_args
