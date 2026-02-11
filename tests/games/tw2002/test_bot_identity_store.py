from __future__ import annotations

import time

from bbsbot.games.tw2002.bot_identity_store import BotIdentityStore
from bbsbot.games.tw2002.config import BotConfig
from bbsbot.games.tw2002.worker import _resolve_worker_identity


def test_identity_store_persists_identity_and_session_lifecycle(tmp_path):
    store = BotIdentityStore(data_dir=tmp_path / "sessions")
    record = store.upsert_identity(
        bot_id="bot_001",
        username="pilot_001",
        character_password="char_pw_001",
        game_password="game_pw_001",
        host="localhost",
        port=2002,
        game_letter="T",
        config_path="config/swarm_demo/bot_001.yaml",
    )
    assert record.username == "pilot_001"
    assert record.character_password == "char_pw_001"

    session = store.start_session(bot_id="bot_001", state="running")
    assert session.started_at <= time.time()
    assert session.stopped_at is None

    store.end_session(
        bot_id="bot_001",
        session_id=session.id,
        stop_reason="shutdown",
        state="stopped",
        exit_reason="shutdown",
        turns_executed=42,
        credits=1337,
        credits_delta=120,
        trades_executed=6,
        sector=9,
    )

    loaded = store.load("bot_001")
    assert loaded is not None
    assert loaded.username == "pilot_001"
    assert loaded.character_password == "char_pw_001"
    assert loaded.game_password == "game_pw_001"
    assert loaded.last_started_at is not None
    assert loaded.last_stopped_at is not None
    assert loaded.run_count == 1
    assert loaded.active_session_id is None
    assert len(loaded.sessions) == 1
    assert loaded.sessions[0].stop_reason == "shutdown"
    assert loaded.sessions[0].turns_executed == 42
    assert loaded.sessions[0].credits == 1337
    assert loaded.sessions[0].trades_executed == 6


def test_resolve_worker_identity_reuses_persisted_values(tmp_path):
    store = BotIdentityStore(data_dir=tmp_path / "sessions")
    store.upsert_identity(
        bot_id="bot_123",
        username="persisted_name",
        character_password="persisted_char_pw",
        game_password="persisted_game_pw",
        host="localhost",
        port=2002,
        game_letter=None,
        config_path="old.yaml",
    )
    config_obj = BotConfig.model_validate({})
    username, char_pw, game_pw = _resolve_worker_identity(
        bot_id="bot_123",
        config_dict={},
        config_obj=config_obj,
        identity_store=store,
        config_path=tmp_path / "config.yaml",
    )
    assert username == "persisted_name"
    assert char_pw == "persisted_char_pw"
    assert game_pw == "persisted_game_pw"


def test_resolve_worker_identity_prefers_explicit_config(tmp_path):
    store = BotIdentityStore(data_dir=tmp_path / "sessions")
    store.upsert_identity(
        bot_id="bot_456",
        username="old_name",
        character_password="old_char_pw",
        game_password="old_game_pw",
        host="localhost",
        port=2002,
        game_letter=None,
        config_path="old.yaml",
    )
    config_dict = {
        "connection": {
            "username": "new_name",
            "character_password": "new_char_pw",
            "game_password": "new_game_pw",
        }
    }
    config_obj = BotConfig.model_validate(config_dict)
    username, char_pw, game_pw = _resolve_worker_identity(
        bot_id="bot_456",
        config_dict=config_dict,
        config_obj=config_obj,
        identity_store=store,
        config_path=tmp_path / "config.yaml",
    )
    assert username == "new_name"
    assert char_pw == "new_char_pw"
    assert game_pw == "new_game_pw"

    updated = store.load("bot_456")
    assert updated is not None
    assert updated.username == "new_name"
    assert updated.character_password == "new_char_pw"
    assert updated.game_password == "new_game_pw"
