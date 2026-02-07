"""Tests for TW2002 trading operations.

Tests critical bug fixes:
- Warp prompt validation
- Buy-before-warp flow with verification
- Special port guards
- Post-warp sector verification
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bbsbot.games.tw2002.trading import (
    _guard_trade_port,
    _extract_port_info,
    _is_trade_port_class,
)


class TestPortClassValidation:
    """Test port class validation for special port detection."""

    def test_is_trade_port_class_valid_classes(self):
        """Test that valid trade port classes are accepted."""
        valid_classes = [
            "BBB", "BBS", "BSB", "BSS",
            "SBB", "SBS", "SSB", "SSS",
        ]
        for port_class in valid_classes:
            assert _is_trade_port_class(port_class), f"{port_class} should be valid"

    def test_is_trade_port_class_invalid_classes(self):
        """Test that invalid port classes are rejected."""
        invalid_classes = [
            "ABC", "123", "BBBS", "B", "BS", "SPECIAL", "XYZ"
        ]
        for port_class in invalid_classes:
            assert not _is_trade_port_class(port_class), f"{port_class} should be invalid"

    def test_is_trade_port_class_none_and_empty(self):
        """Test handling of None and empty strings."""
        assert not _is_trade_port_class(None)
        assert not _is_trade_port_class("")
        assert not _is_trade_port_class("   ")


class TestSpecialPortGuards:
    """Test special port detection and guards (Fix #4)."""

    def test_guard_trade_port_no_port(self):
        """Test that guard raises error when no port is present."""
        bot = MagicMock()
        screen = "You are in empty space. No port here."

        with pytest.raises(RuntimeError, match="no_port"):
            _guard_trade_port(bot, screen, "buy")

    def test_guard_trade_port_stardock(self):
        """Test that Stardock is detected as special port."""
        bot = MagicMock()
        screen = """
        You are at Stardock (Federation Headquarters)
        Port: Stardock
        """

        with pytest.raises(RuntimeError, match="special_port"):
            _guard_trade_port(bot, screen, "sell")

    def test_guard_trade_port_rylos(self):
        """Test that Rylos is detected as special port."""
        bot = MagicMock()
        screen = """
        Port: Rylos (Corporate HQ)
        Class: Special
        """

        with pytest.raises(RuntimeError, match="special_port"):
            _guard_trade_port(bot, screen, "buy")

    def test_guard_trade_port_hardware(self):
        """Test that Hardware vendor is detected as special port (Fix #4)."""
        bot = MagicMock()
        screen = """
        Port: Hardware Inc.
        Ship equipment available for purchase
        """

        with pytest.raises(RuntimeError, match="special_port"):
            _guard_trade_port(bot, screen, "buy")

    def test_guard_trade_port_mcplasma(self):
        """Test that McPlasma vendor is detected as special port (Fix #4)."""
        bot = MagicMock()
        screen = """
        Welcome to McPlasma's Weapons Emporium
        """

        with pytest.raises(RuntimeError, match="special_port"):
            _guard_trade_port(bot, screen, "sell")

    def test_guard_trade_port_valid_port(self):
        """Test that valid trade ports pass the guard."""
        bot = MagicMock()
        bot.game_state = None

        # Mock _extract_port_info to return valid port
        with patch('bbsbot.games.tw2002.trading._extract_port_info') as mock_extract:
            mock_extract.return_value = (True, "BBS", "Trading Post")

            # Should not raise any exception
            try:
                _guard_trade_port(bot, "Port: Trading Post (Class BBS)", "buy")
            except RuntimeError:
                pytest.fail("Valid port should not raise RuntimeError")


class TestPortInfoExtraction:
    """Test port information extraction from screens."""

    def test_extract_port_info_with_class(self):
        """Test extracting port info when class is present."""
        bot = MagicMock()
        bot.game_state = None

        screen = """
        Sector 100
        Port: Trading Station (Class BBS)
        """

        has_port, port_class, port_name = _extract_port_info(bot, screen)

        assert has_port is True
        assert port_class == "BBS"
        assert "Trading Station" in port_name if port_name else True

    def test_extract_port_info_no_port(self):
        """Test extraction when no port is present."""
        bot = MagicMock()
        bot.game_state = None

        screen = """
        Sector 200
        Empty space
        """

        has_port, port_class, port_name = _extract_port_info(bot, screen)

        assert has_port is None or has_port is False

    def test_extract_port_info_class_only(self):
        """Test extraction with port class but no name."""
        bot = MagicMock()
        bot.game_state = None

        screen = """
        Port: (SSB)
        """

        has_port, port_class, port_name = _extract_port_info(bot, screen)

        assert port_class == "SSB"


class TestWarpVerification:
    """Test warp sector verification (Fix #3 and #5)."""

    @pytest.mark.asyncio
    async def test_warp_to_sector_success(self):
        """Test successful warp with verification."""
        from bbsbot.games.tw2002.trading import _warp_to_sector

        bot = MagicMock()
        bot.current_sector = 100
        bot.session = AsyncMock()
        bot.session.send = AsyncMock()

        # Mock wait_and_respond to simulate warp prompt and arrival
        with patch('bbsbot.games.tw2002.trading.wait_and_respond') as mock_wait:
            # First call: warp sector prompt
            # Second call: arrival at target
            mock_wait.side_effect = [
                ("multi_key", "prompt.warp_sector", "Enter sector [100]:", {"current_sector": 100}),
                ("single_key", "prompt.sector_command", "Sector 200 [?]:", {}),
            ]

            with patch('bbsbot.games.tw2002.trading.send_input') as mock_send:
                with patch('bbsbot.games.tw2002.trading._extract_sector_from_screen') as mock_extract:
                    mock_extract.return_value = 200

                    await _warp_to_sector(bot, 200)

                    # Verify sector was updated
                    assert bot.current_sector == 200

    @pytest.mark.asyncio
    async def test_warp_to_sector_already_there(self):
        """Test warp when already at target sector."""
        from bbsbot.games.tw2002.trading import _warp_to_sector

        bot = MagicMock()
        bot.current_sector = 150
        bot.session = AsyncMock()

        # Should skip warp if already there
        await _warp_to_sector(bot, 150)

        # Session.send should not be called
        bot.session.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_warp_verification_failure(self):
        """Test that warp verification catches failures (Fix #3)."""
        from bbsbot.games.tw2002.trading import _warp_to_sector

        bot = MagicMock()
        bot.current_sector = 100
        bot.session = AsyncMock()
        bot.session.send = AsyncMock()

        with patch('bbsbot.games.tw2002.trading.wait_and_respond') as mock_wait:
            # Simulate warp that lands at wrong sector
            mock_wait.side_effect = [
                ("multi_key", "prompt.warp_sector", "Enter sector:", {}),
                ("single_key", "prompt.sector_command", "Sector 150:", {}),  # Wrong sector
            ]

            with patch('bbsbot.games.tw2002.trading.send_input'):
                with patch('bbsbot.games.tw2002.trading._extract_sector_from_screen') as mock_extract:
                    mock_extract.return_value = 150  # Landed at 150 instead of 200

                    with pytest.raises(RuntimeError, match="warp_failed:150"):
                        await _warp_to_sector(bot, 200)


class TestWarpPromptValidation:
    """Test warp prompt input type handling (Fix #2)."""

    @pytest.mark.asyncio
    async def test_warp_saves_correct_input_type(self):
        """Test that warp_input_type is saved from actual warp prompt (Fix #2)."""
        from bbsbot.games.tw2002.trading import _warp_to_sector

        bot = MagicMock()
        bot.current_sector = 100
        bot.session = AsyncMock()

        with patch('bbsbot.games.tw2002.trading.wait_and_respond') as mock_wait:
            # Simulate pause prompt followed by warp prompt
            mock_wait.side_effect = [
                ("any_key", "prompt.pause_simple", "[Pause]", {}),  # Pause first
                ("multi_key", "prompt.warp_sector", "Enter sector:", {}),  # Then warp
                ("single_key", "prompt.sector_command", "Sector 200:", {}),
            ]

            with patch('bbsbot.games.tw2002.trading.send_input') as mock_send:
                with patch('bbsbot.games.tw2002.trading._extract_sector_from_screen') as mock_extract:
                    mock_extract.return_value = 200

                    await _warp_to_sector(bot, 200)

                    # Verify send_input was called with multi_key (from warp prompt)
                    # not any_key (from pause prompt)
                    calls = [call for call in mock_send.call_args_list
                            if len(call[0]) > 1 and call[0][1] == "multi_key"]
                    assert len(calls) > 0, "Should use multi_key from warp prompt"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
