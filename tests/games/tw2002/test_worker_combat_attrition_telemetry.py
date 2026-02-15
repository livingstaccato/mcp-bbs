# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

from bbsbot.games.tw2002.config import BotConfig
from bbsbot.games.tw2002.worker import WorkerBot


class _ScreenStub:
    def __init__(self, text: str):
        self._text = text

    def get_screen(self) -> str:
        return self._text


def test_note_action_completion_attribution_precedence_and_attrition() -> None:
    bot = WorkerBot(bot_id="bot_telemetry", config=BotConfig(), manager_url="http://localhost:9999")
    bot.session = _ScreenStub("Combat! escape pod ... ferrengi ... your ship was destroyed")

    # trade precedence
    bot.note_action_completion(
        action="TRADE",
        credits_before=1000,
        credits_after=1100,
        bank_before=0,
        bank_after=0,
        cargo_before={"fuel_ore": 1, "organics": 0, "equipment": 0},
        cargo_after={"fuel_ore": 0, "organics": 0, "equipment": 0},
        trade_attempted=True,
        trade_success=True,
        combat_evidence=True,
    )
    assert bot.delta_attribution_telemetry["delta_trade"] == 1

    # bank precedence
    bot.note_action_completion(
        action="BANK",
        credits_before=1100,
        credits_after=900,
        bank_before=0,
        bank_after=200,
        cargo_before={"fuel_ore": 0, "organics": 0, "equipment": 0},
        cargo_after={"fuel_ore": 0, "organics": 0, "equipment": 0},
        trade_attempted=False,
        trade_success=False,
        combat_evidence=False,
    )
    assert bot.delta_attribution_telemetry["delta_bank"] == 1

    # combat precedence over unknown
    bot.note_action_completion(
        action="MOVE",
        credits_before=900,
        credits_after=850,
        bank_before=200,
        bank_after=200,
        cargo_before={"fuel_ore": 10, "organics": 4, "equipment": 3},
        cargo_after={"fuel_ore": 7, "organics": 3, "equipment": 1},
        trade_attempted=False,
        trade_success=False,
        combat_evidence=True,
    )
    assert bot.delta_attribution_telemetry["delta_combat"] == 1
    assert bot.attrition_telemetry["fuel_ore_loss_nontrade"] == 3
    assert bot.attrition_telemetry["organics_loss_nontrade"] == 1
    assert bot.attrition_telemetry["equipment_loss_nontrade"] == 2
    assert bot.attrition_telemetry["credits_loss_nontrade"] >= 50
    assert bot.combat_telemetry["combat_context_seen"] >= 1
    assert bot.combat_telemetry["under_attack_reports"] >= 1
    assert bot.combat_telemetry["combat_prompt_escape_pod"] >= 1
    assert bot.combat_telemetry["combat_prompt_ferrengi"] >= 1
    assert bot.combat_telemetry["death_prompt_detected"] >= 1
    assert bot.combat_telemetry["combat_destroyed"] >= 1

    # unknown when no stronger evidence
    bot.session = _ScreenStub("")
    bot.note_action_completion(
        action="MOVE",
        credits_before=850,
        credits_after=840,
        bank_before=200,
        bank_after=200,
        cargo_before={"fuel_ore": 7, "organics": 3, "equipment": 1},
        cargo_after={"fuel_ore": 7, "organics": 3, "equipment": 1},
        trade_attempted=False,
        trade_success=False,
        combat_evidence=False,
    )
    assert bot.delta_attribution_telemetry["delta_unknown"] == 1
