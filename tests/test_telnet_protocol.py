"""Tests for telnet protocol handling."""

from __future__ import annotations

import pytest

from mcp_bbs.telnet.protocol import (
    DO,
    DONT,
    IAC,
    OPT_BINARY,
    OPT_NAWS,
    SB,
    SE,
    WILL,
    WONT,
    TelnetProtocol,
    parse_telnet_commands,
)


@pytest.mark.asyncio
async def test_send_will(mock_writer) -> None:
    """Test sending WILL command."""
    negotiated = {"do": set(), "dont": set(), "will": set(), "wont": set()}
    protocol = TelnetProtocol(mock_writer, negotiated)

    await protocol.send_will(OPT_BINARY)

    mock_writer.write.assert_called_once_with(bytes([IAC, WILL, OPT_BINARY]))
    mock_writer.drain.assert_called_once()
    assert OPT_BINARY in negotiated["will"]


@pytest.mark.asyncio
async def test_send_wont(mock_writer) -> None:
    """Test sending WONT command."""
    negotiated = {"do": set(), "dont": set(), "will": set(), "wont": set()}
    protocol = TelnetProtocol(mock_writer, negotiated)

    await protocol.send_wont(OPT_BINARY)

    mock_writer.write.assert_called_once_with(bytes([IAC, WONT, OPT_BINARY]))
    assert OPT_BINARY in negotiated["wont"]


@pytest.mark.asyncio
async def test_send_do(mock_writer) -> None:
    """Test sending DO command."""
    negotiated = {"do": set(), "dont": set(), "will": set(), "wont": set()}
    protocol = TelnetProtocol(mock_writer, negotiated)

    await protocol.send_do(OPT_BINARY)

    mock_writer.write.assert_called_once_with(bytes([IAC, DO, OPT_BINARY]))
    assert OPT_BINARY in negotiated["do"]


@pytest.mark.asyncio
async def test_send_dont(mock_writer) -> None:
    """Test sending DONT command."""
    negotiated = {"do": set(), "dont": set(), "will": set(), "wont": set()}
    protocol = TelnetProtocol(mock_writer, negotiated)

    await protocol.send_dont(OPT_BINARY)

    mock_writer.write.assert_called_once_with(bytes([IAC, DONT, OPT_BINARY]))
    assert OPT_BINARY in negotiated["dont"]


@pytest.mark.asyncio
async def test_send_naws(mock_writer) -> None:
    """Test sending NAWS (window size) subnegotiation."""
    negotiated = {"do": set(), "dont": set(), "will": set(), "wont": set()}
    protocol = TelnetProtocol(mock_writer, negotiated)

    await protocol.send_naws(80, 25)

    expected = bytes([IAC, SB, OPT_NAWS, 0, 80, 0, 25, IAC, SE])
    mock_writer.write.assert_called_once_with(expected)


def test_strip_telnet_commands(mock_writer) -> None:
    """Test stripping telnet commands from data."""
    negotiated = {"do": set(), "dont": set(), "will": set(), "wont": set()}
    protocol = TelnetProtocol(mock_writer, negotiated)

    # Test with DO command
    data = b"Hello" + bytes([IAC, DO, OPT_BINARY]) + b"World"
    result = protocol.strip_telnet_commands(data)
    assert result == b"HelloWorld"

    # Test with subnegotiation
    data = b"Test" + bytes([IAC, SB, OPT_NAWS, 0, 80, IAC, SE]) + b"Data"
    result = protocol.strip_telnet_commands(data)
    assert result == b"TestData"

    # Test with escaped IAC
    data = bytes([IAC, IAC])
    result = protocol.strip_telnet_commands(data)
    assert result == bytes([IAC])


def test_parse_telnet_commands() -> None:
    """Test parsing telnet commands."""
    data = bytes([IAC, WILL, OPT_BINARY, IAC, DO, OPT_BINARY])
    commands = parse_telnet_commands(data)

    assert len(commands) == 2
    assert commands[0] == ("WILL", OPT_BINARY)
    assert commands[1] == ("DO", OPT_BINARY)
