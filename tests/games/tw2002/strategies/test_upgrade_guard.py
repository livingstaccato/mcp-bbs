# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

from bbsbot.games.tw2002.config import BotConfig
from bbsbot.games.tw2002.orientation import GameState, SectorKnowledge
from bbsbot.games.tw2002.strategies.base import TradeAction, TradingStrategy


class _DummyStrategy(TradingStrategy):
    @property
    def name(self) -> str:
        return "dummy"

    def get_next_action(self, state: GameState) -> tuple[TradeAction, dict]:
        return TradeAction.WAIT, {}

    def find_opportunities(self, state: GameState) -> list:
        return []


def test_should_upgrade_disabled_when_execution_not_enabled() -> None:
    cfg = BotConfig()
    knowledge = SectorKnowledge(knowledge_dir=None, character_name="t")
    strat = _DummyStrategy(cfg, knowledge)
    state = GameState(context="sector_command", credits=2_500, holds_total=20, fighters=0, shields=0)

    should, kind = strat.should_upgrade(state)
    assert should is False
    assert kind is None


def test_should_upgrade_enabled_when_execution_flag_true() -> None:
    cfg = BotConfig()
    cfg.upgrades.execution_enabled = True
    knowledge = SectorKnowledge(knowledge_dir=None, character_name="t")
    strat = _DummyStrategy(cfg, knowledge)
    state = GameState(context="sector_command", credits=2_500, holds_total=20, fighters=0, shields=0)

    should, kind = strat.should_upgrade(state)
    assert should is True
    assert kind in {"holds", "fighters", "shields"}
