"""Verify that player and queue controls act on the displayed song."""

import asyncio
import time
from unittest.mock import AsyncMock

import discord
from discord import app_commands

from commands import music, player_view, queue_view
from conftest import FakeVoice


def test_queue_edits_keep_identity_after_positions_change(manager, song_factory):
    async def scenario():
        first, selected, duplicate = [song_factory() for _ in range(3)]
        for song in (first, selected, duplicate):
            await manager.add_to_queue(1, song)
        await manager.remove_from_queue(1, 1)
        assert await manager.edit_queue_entry(1, selected.entry_id) is selected
        assert manager.get_queue(1) == [duplicate]
        assert await manager.edit_queue_entry(1, selected.entry_id) is None
        assert manager.get_queue(1) == [duplicate]

    asyncio.run(scenario())


def test_queue_pagination_requesters_and_selection(manager, monkeypatch, song_factory):
    async def scenario():
        monkeypatch.setattr(queue_view, "player_manager", manager)
        songs = [song_factory(title=f"Song {i}") for i in range(12)]
        for song in songs:
            await manager.add_to_queue(1, song, requester_name="Alice")
        view = queue_view.QueueView(1, 42)
        embed = view.render()
        assert len(view.select_song.options) == 10
        assert "Alice" in embed.description
        assert not view.next_page.disabled
        view.page = 1
        embed = view.render()
        assert len(view.select_song.options) == 2
        assert view.select_song.options[0].value == songs[10].entry_id
        assert "Page 2/2" in embed.footer.text
        view.stop()

    asyncio.run(scenario())


def test_wait_estimate_handles_paused_live_and_preparing(manager, song_factory):
    player = manager.get_player(1)
    player.voice_client = FakeVoice()
    player.current_song = song_factory(duration=180)
    player.song_start_time = time.time() - 60
    first, second = song_factory(duration=120), song_factory()
    player.queue.extend([first, second])
    assert manager.queue_wait(1, second.entry_id) == 240
    player.voice_client.paused = True
    assert manager.queue_wait(1, second.entry_id) is None
    player.voice_client.paused = False
    player.current_song.duration = 0
    assert manager.queue_wait(1, second.entry_id) is None
    player.current_song.duration = 180
    player.is_starting = True
    assert manager.queue_wait(1, second.entry_id) is None


def test_stale_player_cannot_rate_or_skip_new_song(
    manager, monkeypatch, song_factory, interaction
):
    async def scenario():
        monkeypatch.setattr(player_view, "player_manager", manager)
        rate = AsyncMock()
        monkeypatch.setattr(player_view, "rate_song", rate)
        player = manager.get_player(1)
        first, second = song_factory(title="Old"), song_factory(title="New")
        player.current_song = first
        view = player_view.PlayerView(1, first.entry_id)
        player.current_song = second
        await view.rate(interaction, 1)
        await view.skip_song.callback(interaction)
        rate.assert_not_called()
        assert player.current_song is second
        assert "song changed" in interaction.response.send_message.call_args.args[0]
        view.stop()

    asyncio.run(scenario())


def test_player_card_updates_song_and_never_times_out_during_session(
    manager, monkeypatch, song_factory
):
    async def scenario():
        monkeypatch.setattr(player_view, "player_manager", manager)
        monkeypatch.setattr(player_view, "get_rating_counts", lambda *args: (0, 0))
        player = manager.get_player(1)
        player.voice_client = FakeVoice()
        player.current_song = song_factory(title="First")
        player.phase = "playing"
        embed, view = await player_view.render_player(1)
        assert "First" in embed.description
        assert view.timeout is None
        assert view.pause_resume.label == "Pause"
        view.stop()
        player.current_song = song_factory(title="Second")
        player.phase = "paused"
        embed, view = await player_view.render_player(1)
        assert "Second" in embed.description
        assert view.entry_id == player.current_song.entry_id
        assert view.pause_resume.label == "Resume"
        view.stop()

    asyncio.run(scenario())


def test_player_requests_reuse_one_shared_card(manager, monkeypatch, interaction):
    async def scenario():
        monkeypatch.setattr(player_view, "player_manager", manager)
        manager.get_player(1).voice_client = FakeVoice()
        panels = player_view.PlayerPanels()
        first = await panels.ensure(interaction)
        second = await panels.ensure(interaction)
        assert first is second
        interaction.channel.send.assert_awaited_once()
        await panels.close()

    asyncio.run(scenario())


def test_music_commands_register_with_distinct_autocomplete_values(monkeypatch):
    async def scenario():
        client = discord.Client(intents=discord.Intents.none())
        client.tree = app_commands.CommandTree(client)
        music.setup(client)
        monkeypatch.setattr(
            music.ytmusic,
            "search_songs_async",
            AsyncMock(
                return_value=[
                    {"title": "Song", "artist": "Artist", "videoId": "abcdefghijk"}
                ]
            ),
        )
        play = client.tree.get_command("play")
        choices = await play._params["query"].autocomplete(None, "song")
        assert choices[0].value == "yt:abcdefghijk"
        assert all(command.guild_only for command in client.tree.get_commands())
        await client.close()

    asyncio.run(scenario())
