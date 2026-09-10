"""Exercise playback races, recovery, and preparation without network access."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import music_player
from conftest import FakeSource, FakeVoice, settle


def test_skip_preparing_song_starts_next_without_waiting(manager, song_factory):
    async def scenario():
        voice = FakeVoice()
        player = manager.get_player(1)
        player.voice_client = voice
        first, second = song_factory(title="First"), song_factory(title="Second")
        waiting = asyncio.Event()

        async def source(song, player, **kwargs):
            if song is first:
                waiting.set()
                await asyncio.Event().wait()
            return FakeSource()

        manager._create_audio_source = source
        await manager.add_to_queue(1, first)
        await manager.add_to_queue(1, second)
        manager.start_playback(1)
        await waiting.wait()
        assert manager.skip(1)
        await asyncio.wait_for(voice.started.wait(), 1)
        assert player.current_song is second
        assert len(voice.sources) == 1
        assert not player.is_starting
        await manager.disconnect(1)

    asyncio.run(scenario())


def test_late_source_after_stop_cannot_restart_old_session(manager, song_factory):
    async def scenario():
        player = manager.get_player(1)
        voice = FakeVoice()
        player.voice_client = voice
        first = song_factory()
        waiting = asyncio.Event()
        old_source = FakeSource()

        async def source(*args, **kwargs):
            waiting.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                return old_source

        manager._create_audio_source = source
        await manager.add_to_queue(1, first)
        manager.start_playback(1)
        await waiting.wait()
        await manager.disconnect(1)
        await settle()
        assert not voice.sources
        assert old_source.cleaned
        assert player.current_song is None
        assert player.phase == "disconnected"

    asyncio.run(scenario())


def test_interrupt_retries_once_then_moves_on(manager, song_factory):
    async def scenario():
        player = manager.get_player(1)
        voice = FakeVoice()
        player.voice_client = voice
        first, second = song_factory(title="Broken"), song_factory(title="Next")
        await manager.add_to_queue(1, first)
        await manager.add_to_queue(1, second)
        manager.start_playback(1)
        await voice.started.wait()
        voice.finish()
        await settle()
        assert player.current_song is first
        assert len(voice.sources) == 2
        assert manager._create_audio_source.call_args.kwargs["retry"]
        voice.finish()
        await settle()
        assert player.current_song is second
        assert len(voice.sources) == 3
        assert "Skipped" in player.notice
        await manager.disconnect(1)

    asyncio.run(scenario())


def test_manual_skip_does_not_retry(manager, song_factory):
    async def scenario():
        player = manager.get_player(1)
        player.voice_client = FakeVoice()
        first, second = song_factory(), song_factory(title="Next")
        await manager.add_to_queue(1, first)
        await manager.add_to_queue(1, second)
        manager.start_playback(1)
        await player.voice_client.started.wait()
        assert manager.skip(1)
        await settle()
        assert player.current_song is second
        assert len(player.voice_client.sources) == 2
        await manager.disconnect(1)

    asyncio.run(scenario())


def test_connection_never_moves_another_listening_group(manager):
    async def scenario():
        player = manager.get_player(1)
        voice = FakeVoice(channel_id=10)
        player.voice_client = voice
        other = SimpleNamespace(id=20, connect=AsyncMock())
        with pytest.raises(ValueError, match="<#10>"):
            await manager.connect(1, other)
        other.connect.assert_not_called()
        assert player.voice_client.channel.id == 10

    asyncio.run(scenario())


def test_simultaneous_connects_share_one_connection(manager):
    async def scenario():
        channel = SimpleNamespace(
            id=10,
            guild=SimpleNamespace(name="Server"),
            connect=AsyncMock(return_value=FakeVoice()),
        )
        first, second = await asyncio.gather(
            manager.connect(1, channel), manager.connect(1, channel)
        )
        assert first is second
        channel.connect.assert_awaited_once()
        await manager.disconnect(1)

    asyncio.run(scenario())


def test_new_songs_and_reorders_prepare_upcoming_audio(manager, song_factory):
    async def scenario():
        songs = [song_factory(title=str(i)) for i in range(4)]
        for song in songs:
            await manager.add_to_queue(1, song)
        music_player.audio_cache.start_background_download.reset_mock()
        await manager.move_in_queue(1, 4, 1)
        calls = music_player.audio_cache.start_background_download.call_args_list
        assert [call.args[0] for call in calls] == [songs[3], songs[0]]

    asyncio.run(scenario())


def test_autoplay_arrivals_trigger_audio_downloads(manager, monkeypatch, song_factory):
    async def scenario():
        player = manager.get_player(1)
        player.voice_client = FakeVoice()
        player.recent_songs.append("seed")
        player.autoplay_enabled = True
        song = song_factory()
        manager._get_blended_recommendations = AsyncMock(
            return_value=[{"videoId": song.video_id}]
        )
        monkeypatch.setattr(
            music_player, "extract_song_info", AsyncMock(return_value=song)
        )
        await manager._prefetch_autoplay(1, player)
        assert list(player.autoplay_queue) == [song]
        music_player.audio_cache.start_background_download.assert_called_with(song)
        await manager.disconnect(1)

    asyncio.run(scenario())


def test_clear_queue_cancels_import_but_keeps_current_song(manager, song_factory):
    async def scenario():
        player = manager.get_player(1)
        current = song_factory()
        player.current_song = current
        player.voice_client = FakeVoice()
        player.voice_client.playing = True
        task = asyncio.create_task(asyncio.Event().wait())
        player._request_tasks.add(task)
        await manager.add_to_queue(1, song_factory(title="Queued"))
        assert await manager.clear_queue(1) == 1
        await settle()
        assert task.cancelled()
        assert player.current_song is current
        assert player.voice_client.is_playing()
        await manager.disconnect(1)

    asyncio.run(scenario())


def test_streaming_retry_refreshes_old_url(manager, monkeypatch, song_factory):
    async def scenario():
        song = song_factory()
        fresh = song_factory()
        fresh.url = "https://audio.example/fresh"
        monkeypatch.setattr(
            music_player, "extract_song_info", AsyncMock(return_value=fresh)
        )
        from unittest.mock import Mock

        ffmpeg = Mock(return_value=FakeSource())
        monkeypatch.setattr(music_player.discord, "FFmpegPCMAudio", ffmpeg)
        monkeypatch.setattr(
            music_player.discord, "PCMVolumeTransformer", lambda source, volume: source
        )
        source = await music_player.MusicPlayerManager._create_audio_source(
            manager, song, manager.get_player(1), retry=True
        )
        assert ffmpeg.call_args.args[0] == fresh.url
        source.cleanup()

    asyncio.run(scenario())


def test_disabling_autoplay_during_preparation_returns_to_idle(manager):
    async def scenario():
        player = manager.get_player(1)
        player.voice_client = FakeVoice()
        player.autoplay_enabled = True
        player.recent_songs.append("seed")
        player._prefetch_task = asyncio.create_task(asyncio.Event().wait())
        manager.start_playback(1)
        await settle()
        assert player.is_starting
        manager.toggle_autoplay(1)
        await settle()
        assert player.phase == "idle"
        assert not player.is_starting
        assert not player.voice_client.sources
        await manager.disconnect(1)

    asyncio.run(scenario())
