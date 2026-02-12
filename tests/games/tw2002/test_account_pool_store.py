# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

from bbsbot.games.tw2002.account_pool_store import AccountLeaseError, AccountPoolStore


def _pool(tmp_path):
    return AccountPoolStore(
        pool_file=tmp_path / "sessions" / "account_pool.json",
        lock_file=tmp_path / "sessions" / "account_pool.lock",
    )


def test_reserve_enforces_single_active_lease(tmp_path):
    pool = _pool(tmp_path)
    pool.reserve_account(
        bot_id="bot_1",
        username="pilot_a",
        character_password="pw_a",
        game_password="game",
        host="localhost",
        port=2002,
        game_letter="T",
        source="generated",
    )

    try:
        pool.reserve_account(
            bot_id="bot_2",
            username="pilot_a",
            character_password="pw_a",
            game_password="game",
            host="localhost",
            port=2002,
            game_letter="T",
            source="generated",
        )
        raise AssertionError("expected AccountLeaseError for active lease")
    except AccountLeaseError:
        pass

    released = pool.release_by_bot(bot_id="bot_1")
    assert released == 1

    pool.reserve_account(
        bot_id="bot_2",
        username="pilot_a",
        character_password="pw_a",
        game_password="game",
        host="localhost",
        port=2002,
        game_letter="T",
        source="generated",
    )


def test_release_sets_cooldown_and_blocks_until_expiry(tmp_path):
    pool = _pool(tmp_path)
    pool.reserve_account(
        bot_id="bot_1",
        username="pilot_b",
        character_password="pw_b",
        game_password="game",
        host="localhost",
        port=2002,
        game_letter="T",
        source="generated",
    )
    pool.release_by_bot(bot_id="bot_1", cooldown_s=3600)

    try:
        pool.reserve_account(
            bot_id="bot_2",
            username="pilot_b",
            character_password="pw_b",
            game_password="game",
            host="localhost",
            port=2002,
            game_letter="T",
            source="generated",
        )
        raise AssertionError("expected AccountLeaseError for cooldown")
    except AccountLeaseError as exc:
        assert "account_cooldown" in str(exc)


def test_acquire_uses_lru_available_account(tmp_path):
    pool = _pool(tmp_path)
    pool.reserve_account(
        bot_id="bot_old",
        username="pilot_old",
        character_password="pw_old",
        game_password="game",
        host="localhost",
        port=2002,
        game_letter="T",
        source="pool",
    )
    pool.release_by_bot(bot_id="bot_old")

    pool.reserve_account(
        bot_id="bot_new",
        username="pilot_new",
        character_password="pw_new",
        game_password="game",
        host="localhost",
        port=2002,
        game_letter="T",
        source="pool",
    )
    pool.release_by_bot(bot_id="bot_new")

    record = pool.acquire_account(bot_id="bot_3", host="localhost", port=2002, game_letter="T")
    assert record is not None
    assert record.username == "pilot_old"
