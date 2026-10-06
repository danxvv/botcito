"""Check how voice-state events reach the player and how logging is set up."""

import asyncio
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

import main
from conftest import BOT_ID, FakeVoice


@pytest.fixture
def bot(manager, monkeypatch):
    """Route main.py's events to a manager whose player is connected to channel 10."""
    monkeypatch.setattr(main, "player_manager", manager)
    monkeypatch.setattr(main, "client", SimpleNamespace(user=SimpleNamespace(id=BOT_ID)))
    manager.check_listeners = Mock()
    manager.cleanup_external_disconnect = AsyncMock()
    manager.get_player(1).voice_client = FakeVoice(channel_id=10)
    return manager


def member(user_id, guild_id=1):
    return SimpleNamespace(id=user_id, guild=SimpleNamespace(id=guild_id))


def state(channel_id):
    return SimpleNamespace(channel=None if channel_id is None else SimpleNamespace(id=channel_id))


def test_a_person_joining_or_leaving_rechecks_the_channel(bot):
    asyncio.run(main.on_voice_state_update(member(7), state(10), state(None)))
    asyncio.run(main.on_voice_state_update(member(7), state(None), state(10)))
    asyncio.run(main.on_voice_state_update(member(7), state(10), state(20)))
    assert bot.check_listeners.call_count == 3
    bot.check_listeners.assert_called_with(1)
    bot.cleanup_external_disconnect.assert_not_awaited()


def test_the_bot_being_disconnected_ends_the_session(bot):
    asyncio.run(main.on_voice_state_update(member(BOT_ID), state(10), state(None)))
    bot.cleanup_external_disconnect.assert_awaited_once_with(1)
    bot.check_listeners.assert_not_called()


def test_the_bot_leaving_a_different_channel_is_ignored(bot):
    asyncio.run(main.on_voice_state_update(member(BOT_ID), state(30), state(None)))
    bot.cleanup_external_disconnect.assert_not_awaited()


def test_the_bot_being_moved_rechecks_who_is_with_it(bot):
    asyncio.run(main.on_voice_state_update(member(BOT_ID), state(10), state(20)))
    bot.check_listeners.assert_called_once_with(1)
    bot.cleanup_external_disconnect.assert_not_awaited()


def test_servers_without_a_session_are_ignored_and_not_given_one(bot):
    asyncio.run(main.on_voice_state_update(member(7, guild_id=555), state(None), state(10)))
    assert 555 not in bot.players
    bot.check_listeners.assert_not_called()


def test_a_session_without_a_voice_connection_is_ignored(bot):
    bot.get_player(1).voice_client = None
    asyncio.run(main.on_voice_state_update(member(7), state(10), state(None)))
    bot.check_listeners.assert_not_called()


@pytest.mark.parametrize(
    "value, expected",
    [(None, logging.INFO), ("debug", logging.DEBUG), ("WARNING", logging.WARNING), ("nonsense", logging.INFO), ("", logging.INFO)],
)
def test_log_level_comes_from_the_environment(value, expected, monkeypatch):
    configured = Mock()
    monkeypatch.setattr(main.logging, "basicConfig", configured)
    if value is None:
        monkeypatch.delenv("LOG_LEVEL", raising=False)
    else:
        monkeypatch.setenv("LOG_LEVEL", value)
    main.configure_logging()
    assert configured.call_args.kwargs["level"] == expected


def test_a_log_level_name_that_is_not_a_level_is_not_accepted(monkeypatch):
    configured = Mock()
    monkeypatch.setattr(main.logging, "basicConfig", configured)
    monkeypatch.setenv("LOG_LEVEL", "getLogger")  # A logging attribute, but not a level.
    main.configure_logging()
    assert configured.call_args.kwargs["level"] == logging.INFO


def test_discord_py_does_not_add_a_second_log_handler(monkeypatch):
    run = Mock()
    monkeypatch.setattr(main, "TOKEN", "token")
    monkeypatch.setattr(main.client, "run", run)
    monkeypatch.setattr(main, "configure_logging", Mock())
    main.main()
    run.assert_called_once_with("token", log_handler=None)


def test_a_missing_token_stops_before_connecting(monkeypatch, caplog):
    run = Mock()
    monkeypatch.setattr(main, "TOKEN", None)
    monkeypatch.setattr(main.client, "run", run)
    monkeypatch.setattr(main, "configure_logging", Mock())
    with caplog.at_level(logging.ERROR):
        main.main()
    run.assert_not_called()
    assert "DISCORD_TOKEN" in caplog.text


def test_an_old_ytdlp_gets_a_warning_and_a_current_one_does_not(monkeypatch, caplog):
    monkeypatch.setattr(main, "TOKEN", "token")
    monkeypatch.setattr(main.client, "run", Mock())
    monkeypatch.setattr(main, "configure_logging", Mock())
    monkeypatch.setattr(main, "check_dependencies", lambda: [])
    monkeypatch.setattr(main, "ytdlp_age_days", lambda version: main.YTDLP_MAX_AGE_DAYS + 1)
    with caplog.at_level(logging.WARNING):
        main.main()
    assert "days old" in caplog.text
    caplog.clear()
    monkeypatch.setattr(main, "ytdlp_age_days", lambda version: main.YTDLP_MAX_AGE_DAYS)
    with caplog.at_level(logging.WARNING):
        main.main()
    assert "days old" not in caplog.text


def test_startup_forgets_an_old_heartbeat_and_starts_a_new_one(monkeypatch):
    async def scenario():
        import audio_cache
        import commands

        monkeypatch.setattr(audio_cache.audio_cache, "clear_stale_files", Mock())
        monkeypatch.setattr(commands, "setup_commands", Mock())
        monkeypatch.setattr(main, "SYNC_COMMANDS", False)
        cleared = Mock()
        monkeypatch.setattr(main, "clear_heartbeat", cleared)
        bot = main.MusicBot()
        await bot.setup_hook()
        cleared.assert_called_once_with()
        assert bot.heartbeat.is_running()
        bot.heartbeat.cancel()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "ready, latency, writes",
    [(True, 0.05, 1), (False, 0.05, 0), (True, float("nan"), 0)],
)
def test_heartbeat_is_only_written_while_connected_to_discord(
    ready, latency, writes, monkeypatch
):
    async def scenario():
        write = Mock()
        monkeypatch.setattr(main, "write_heartbeat", write)
        monkeypatch.setattr(main.MusicBot, "is_ready", lambda self: ready)
        monkeypatch.setattr(main.MusicBot, "latency", property(lambda self: latency))
        await main.MusicBot.heartbeat.coro(main.MusicBot())
        assert write.call_count == writes

    asyncio.run(scenario())
