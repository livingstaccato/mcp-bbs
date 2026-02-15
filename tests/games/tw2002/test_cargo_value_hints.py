# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

from bbsbot.games.tw2002.cli_impl import _record_cargo_value_hint
from bbsbot.games.tw2002.config import BotConfig
from bbsbot.games.tw2002.orientation.knowledge import SectorKnowledge
from bbsbot.games.tw2002.worker import WorkerBot


def test_record_cargo_value_hint_conservative_for_port_sell_quotes() -> None:
    bot = WorkerBot(bot_id="bot_hint", config=BotConfig(), manager_url="http://localhost:9999")

    _record_cargo_value_hint(bot, "equipment", 400, side="sell")
    hints = getattr(bot, "_cargo_value_hints", {})
    assert int(hints.get("equipment", 0)) == 300

    # Smoothing should move gradually rather than jumping to extremes.
    _record_cargo_value_hint(bot, "equipment", 200, side="sell")
    hints = getattr(bot, "_cargo_value_hints", {})
    assert int(hints.get("equipment", 0)) == 262


def test_estimate_cargo_market_value_uses_value_hints_without_market_data() -> None:
    bot = WorkerBot(bot_id="bot_value", config=BotConfig(), manager_url="http://localhost:9999")
    bot._cargo_value_hints = {"equipment": 115}

    value = bot._estimate_cargo_market_value({"equipment": 3, "fuel_ore": 0, "organics": 0})
    assert value == 345


def test_estimate_cargo_market_value_prefers_observed_buy_quotes_over_hints() -> None:
    bot = WorkerBot(bot_id="bot_prices", config=BotConfig(), manager_url="http://localhost:9999")
    bot._cargo_value_hints = {"equipment": 80}
    bot.sector_knowledge = SectorKnowledge()
    bot.sector_knowledge.update_sector(
        7,
        {
            "port_prices": {
                "equipment": {"buy": 140, "sell": 120},
            },
        },
    )

    value = bot._estimate_cargo_market_value({"equipment": 2})
    assert value == 280


def test_estimate_cargo_market_value_uses_conservative_floor_when_unknown() -> None:
    bot = WorkerBot(bot_id="bot_floor", config=BotConfig(), manager_url="http://localhost:9999")

    value = bot._estimate_cargo_market_value({"fuel_ore": 2, "organics": 1, "equipment": 0})
    assert value == 45


def test_estimate_cargo_market_value_records_source_mix_and_confidence() -> None:
    bot = WorkerBot(bot_id="bot_mix", config=BotConfig(), manager_url="http://localhost:9999")
    bot._cargo_value_hints = {"organics": 50}
    bot.sector_knowledge = SectorKnowledge()
    bot.sector_knowledge.update_sector(
        7,
        {
            "port_prices": {
                "fuel_ore": {"buy": 30},
            },
        },
    )

    value = bot._estimate_cargo_market_value({"fuel_ore": 2, "organics": 1, "equipment": 3})
    assert value == 155
    assert bot.valuation_source_units_last["quote"] == 2
    assert bot.valuation_source_units_last["hint"] == 1
    assert bot.valuation_source_units_last["floor"] == 3
    assert bot.valuation_source_value_last["quote"] == 60
    assert bot.valuation_source_value_last["hint"] == 50
    assert bot.valuation_source_value_last["floor"] == 45
    assert bot.valuation_confidence_last > 0.0

    totals_before = dict(bot.valuation_source_units_total)
    _ = bot._estimate_cargo_market_value({"fuel_ore": 2, "organics": 1, "equipment": 3})
    assert bot.valuation_source_units_total == totals_before
