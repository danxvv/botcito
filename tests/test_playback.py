"""Exercise playback races, recovery, and preparation without network access."""

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

import background
import music_player
import youtube
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


# ============== Empty channel ==============


def start_playing(manager, song_factory, **song_args):
    """Begin playing one song on a fake voice connection and return the pieces."""
    voice = FakeVoice()
    player = manager.get_player(1)
    player.voice_client = voice
    return voice, player, song_factory(**song_args)


def test_bot_leaves_when_everyone_left_even_if_autoplay_has_music(
    manager, monkeypatch, song_factory
):
    async def scenario():
        monkeypatch.setattr(music_player, "EMPTY_CHANNEL_TIMEOUT", 0.05)
        voice, player, song = start_playing(manager, song_factory)
        player.autoplay_enabled = True
        manager._get_blended_recommendations = AsyncMock(return_value=[])
        await manager.add_to_queue(1, song)
        await manager.add_to_queue(1, song_factory(title="Next"))
        manager.start_playback(1)
        await voice.started.wait()
        voice.set_listeners()
        manager.check_listeners(1)
        await asyncio.sleep(0.3)
        assert player.voice_client is None
        assert not voice.connected
        assert player.phase == "disconnected"
        assert "everyone left" in player.notice

    asyncio.run(scenario())


def test_someone_returning_cancels_the_countdown(manager, monkeypatch, song_factory):
    async def scenario():
        monkeypatch.setattr(music_player, "EMPTY_CHANNEL_TIMEOUT", 0.1)
        voice, player, _ = start_playing(manager, song_factory)
        voice.set_listeners(7)
        manager.check_listeners(1)
        assert player._empty_task is None
        voice.set_listeners()
        manager.check_listeners(1)
        countdown = player._empty_task
        assert countdown and not countdown.done()
        manager.check_listeners(1)  # More events must not restart or duplicate it.
        assert player._empty_task is countdown
        voice.set_listeners(7)
        manager.check_listeners(1)
        await asyncio.sleep(0)
        assert countdown.cancelled() and player._empty_task is None
        await asyncio.sleep(0.2)
        assert voice.connected and player.voice_client is voice

    asyncio.run(scenario())


def test_bots_do_not_keep_an_empty_channel_alive(manager, monkeypatch, song_factory):
    async def scenario():
        monkeypatch.setattr(music_player, "EMPTY_CHANNEL_TIMEOUT", 60)
        voice, player, _ = start_playing(manager, song_factory)
        voice.set_listeners(bots=(8, 9))
        manager.check_listeners(1)
        assert player._empty_task is not None
        voice.set_listeners(7, bots=(8,))
        manager.check_listeners(1)
        await asyncio.sleep(0)
        assert player._empty_task is None

    asyncio.run(scenario())


def test_uncached_users_are_assumed_to_be_listening(manager, song_factory):
    async def scenario():
        voice, player, _ = start_playing(manager, song_factory)
        voice.channel.voice_states[55] = object()  # No member object cached for them.
        manager.check_listeners(1)
        assert player._empty_task is None

    asyncio.run(scenario())


def test_listener_checks_ignore_servers_without_a_session(manager):
    manager.check_listeners(123)
    assert 123 not in manager.players


def test_disconnecting_cancels_the_empty_channel_countdown(manager, song_factory):
    async def scenario():
        voice, player, _ = start_playing(manager, song_factory)
        voice.set_listeners()
        manager.check_listeners(1)
        countdown = player._empty_task
        await manager.disconnect(1)
        await asyncio.sleep(0)
        assert countdown.cancelled() and player._empty_task is None

    asyncio.run(scenario())


# ============== Seek and resume ==============


def test_seek_restarts_the_song_at_the_requested_position(manager, song_factory):
    async def scenario():
        voice, player, song = start_playing(manager, song_factory, duration=200)
        await manager.add_to_queue(1, song)
        manager.start_playback(1)
        await voice.started.wait()
        old_source = voice.source
        voice.started.clear()
        assert manager.seek(1, 75) == 75
        await asyncio.wait_for(voice.started.wait(), 1)
        await settle()
        kwargs = manager._create_audio_source.call_args.kwargs
        assert kwargs["start_at"] == 75 and kwargs["retry"] is False
        assert player.current_song is song and len(voice.sources) == 2
        assert old_source.cleaned
        assert 75 <= manager.get_elapsed_seconds(1) <= 76
        manager._log_play.assert_called_once()  # A seek is not a new play.
        await manager.disconnect(1)

    asyncio.run(scenario())


def test_seek_does_not_skip_or_retry_when_the_old_audio_ends(manager, song_factory):
    async def scenario():
        voice, player, song = start_playing(manager, song_factory, duration=200)
        second = song_factory(title="Next")
        await manager.add_to_queue(1, song)
        await manager.add_to_queue(1, second)
        manager.start_playback(1)
        await voice.started.wait()
        voice.started.clear()
        manager.seek(1, 30)
        await asyncio.wait_for(voice.started.wait(), 1)
        await settle()
        assert player.current_song is song
        assert list(player.queue) == [second]
        assert len(voice.sources) == 2
        await manager.disconnect(1)

    asyncio.run(scenario())


def test_seek_while_paused_resumes_playback(manager, song_factory):
    async def scenario():
        voice, player, song = start_playing(manager, song_factory, duration=200)
        await manager.add_to_queue(1, song)
        manager.start_playback(1)
        await voice.started.wait()
        assert manager.pause(1)
        voice.started.clear()
        assert manager.seek(1, 10) == 10
        await asyncio.wait_for(voice.started.wait(), 1)
        await settle()
        assert not manager.is_paused(1) and voice.is_playing()
        assert player.phase == "playing" and player.paused_at is None
        assert 10 <= manager.get_elapsed_seconds(1) <= 11
        await manager.disconnect(1)

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "requested, expected", [(75, 75), (0, 0), (-30, 0), (200, 199), (10_000, 199)]
)
def test_seek_stays_inside_the_song(requested, expected, manager, song_factory):
    async def scenario():
        voice, player, song = start_playing(manager, song_factory, duration=200)
        await manager.add_to_queue(1, song)
        manager.start_playback(1)
        await voice.started.wait()
        assert manager.seek(1, requested) == expected
        await settle()
        await manager.disconnect(1)

    asyncio.run(scenario())


def test_seek_refuses_what_cannot_be_seeked(manager, song_factory):
    async def scenario():
        voice, player, song = start_playing(manager, song_factory, duration=200)
        assert manager.seek(1, 10) is None  # Nothing playing.
        player.current_song = song
        song.is_live = True
        assert manager.seek(1, 10) is None  # Live streams have no timeline.
        song.is_live, song.duration = False, 0
        assert manager.seek(1, 10) is None  # Unknown length.
        song.duration = 200
        player.is_starting = True
        assert manager.seek(1, 10) is None  # Still starting.
        player.is_starting = False
        player.voice_client = None
        assert manager.seek(1, 10) is None  # Not connected.
        assert len(voice.sources) == 0

    asyncio.run(scenario())


def test_interrupted_song_resumes_where_it_stopped(manager, song_factory):
    async def scenario():
        voice, player, song = start_playing(manager, song_factory, duration=300)
        await manager.add_to_queue(1, song)
        manager.start_playback(1)
        await voice.started.wait()
        player.song_start_time = time.time() - 60  # A minute of the song had played.
        voice.finish()
        await settle()
        kwargs = manager._create_audio_source.call_args.kwargs
        assert kwargs["retry"] and 59 <= kwargs["start_at"] <= 61
        assert 59 <= manager.get_elapsed_seconds(1) <= 62
        await manager.disconnect(1)

    asyncio.run(scenario())


def test_song_interrupted_at_the_start_restarts_from_the_beginning(manager, song_factory):
    async def scenario():
        voice, player, song = start_playing(manager, song_factory, duration=300)
        await manager.add_to_queue(1, song)
        manager.start_playback(1)
        await voice.started.wait()
        voice.finish()
        await settle()
        assert manager._create_audio_source.call_args.kwargs["start_at"] == 0
        await manager.disconnect(1)

    asyncio.run(scenario())


def test_live_streams_restart_instead_of_resuming(manager, song_factory):
    async def scenario():
        voice, player, song = start_playing(manager, song_factory, duration=0)
        song.is_live = True
        await manager.add_to_queue(1, song)
        manager.start_playback(1)
        await voice.started.wait()
        player.song_start_time = time.time() - 60
        voice.finish()
        await settle()
        assert manager._create_audio_source.call_args.kwargs["start_at"] == 0
        await manager.disconnect(1)

    asyncio.run(scenario())


def test_ffmpeg_diagnostics_go_to_a_real_file_so_discord_py_starts_no_reader(
    manager, monkeypatch, song_factory
):
    async def scenario():
        ffmpeg = Mock(return_value=FakeSource())
        monkeypatch.setattr(music_player.discord, "FFmpegPCMAudio", ffmpeg)
        monkeypatch.setattr(
            music_player.discord, "PCMVolumeTransformer", lambda source, volume: source
        )
        await music_player.MusicPlayerManager._create_audio_source(
            manager, song_factory(), manager.get_player(1)
        )
        stderr = ffmpeg.call_args.kwargs["stderr"]
        # An int such as subprocess.DEVNULL has no fileno(), so discord.py would pipe
        # FFmpeg's stderr to a reader thread that raises on every write.
        assert not isinstance(stderr, int) and isinstance(stderr.fileno(), int)

    asyncio.run(scenario())


@pytest.mark.parametrize("local", [False, True])
def test_start_position_is_passed_to_ffmpeg(local, manager, monkeypatch, song_factory):
    async def scenario():
        song = song_factory()
        if local:
            song.local_path = "/cache/song.webm"
            music_player.audio_cache.ensure_downloaded = AsyncMock(return_value=True)
        ffmpeg = Mock(return_value=FakeSource())
        monkeypatch.setattr(music_player.discord, "FFmpegPCMAudio", ffmpeg)
        monkeypatch.setattr(
            music_player.discord, "PCMVolumeTransformer", lambda source, volume: source
        )
        build = music_player.MusicPlayerManager._create_audio_source
        player = manager.get_player(1)

        await build(manager, song, player, start_at=75.9)
        before = ffmpeg.call_args.kwargs["before_options"]
        if local:
            assert before == "-ss 75"
        else:
            assert before.startswith("-ss 75 ") and "-reconnect 1" in before

        await build(manager, song, player)
        before = ffmpeg.call_args.kwargs["before_options"]
        if local:
            assert before is None
        else:
            assert "-ss" not in before and "-reconnect 1" in before

    asyncio.run(scenario())


# ============== Lazily imported songs ==============


def stub_song(video_id="abcdefghijk"):
    return youtube.playlist_entry_song({"video_id": video_id, "title": "Flat", "duration": 120})


def resolved_copy(**overrides):
    song = youtube.SongInfo(
        url="https://audio.example/resolved",
        title="Resolved title",
        duration=123,
        thumbnail="",
        video_id="abcdefghijk",
        webpage_url="https://www.youtube.com/watch?v=abcdefghijk",
        info={"formats": [{}]},
    )
    for key, value in overrides.items():
        setattr(song, key, value)
    return song


def patch_ffmpeg(monkeypatch):
    ffmpeg = Mock(return_value=FakeSource())
    monkeypatch.setattr(music_player.discord, "FFmpegPCMAudio", ffmpeg)
    monkeypatch.setattr(
        music_player.discord, "PCMVolumeTransformer", lambda source, volume: source
    )
    return ffmpeg


def test_playlist_entry_is_extracted_when_it_is_about_to_play(manager, monkeypatch):
    async def scenario():
        extract = AsyncMock(return_value=resolved_copy())
        monkeypatch.setattr(youtube, "extract_song_info", extract)
        ffmpeg = patch_ffmpeg(monkeypatch)
        song = stub_song()
        await music_player.MusicPlayerManager._create_audio_source(
            manager, song, manager.get_player(1)
        )
        extract.assert_awaited_once_with("abcdefghijk")
        assert ffmpeg.call_args.args[0] == "https://audio.example/resolved"
        assert (song.resolved, song.title, song.duration) == (True, "Resolved title", 123)
        assert song.info is None  # Released once the audio source exists.

    asyncio.run(scenario())


def test_unresolvable_playlist_entry_is_unavailable(manager, monkeypatch):
    async def scenario():
        monkeypatch.setattr(youtube, "extract_song_info", AsyncMock(return_value=None))
        ffmpeg = patch_ffmpeg(monkeypatch)
        with pytest.raises(music_player.SongUnavailableError):
            await music_player.MusicPlayerManager._create_audio_source(
                manager, stub_song(), manager.get_player(1)
            )
        ffmpeg.assert_not_called()

    asyncio.run(scenario())


def test_unavailable_song_is_skipped_without_retrying(manager, song_factory):
    async def scenario():
        voice, player, gone = start_playing(manager, song_factory, title="Gone")
        fine = song_factory(title="Fine")
        attempts = []

        async def source(song, player, **kwargs):
            attempts.append(song.title)
            if song is gone:
                raise music_player.SongUnavailableError(song.title)
            return FakeSource()

        manager._create_audio_source = source
        await manager.add_to_queue(1, gone)
        await manager.add_to_queue(1, fine)
        manager.start_playback(1)
        await asyncio.wait_for(voice.started.wait(), 1)
        assert attempts == ["Gone", "Fine"]
        assert player.current_song is fine
        assert "Gone is unavailable" in player.notice
        music_player.audio_cache.release.assert_any_call(gone)
        await manager.disconnect(1)

    asyncio.run(scenario())


def test_songs_far_back_in_the_queue_drop_their_extraction_data(manager, song_factory):
    async def scenario():
        songs = [song_factory(title=str(i)) for i in range(4)]
        for song in songs:
            song.info = {"formats": [{}]}
            await manager.add_to_queue(1, song)
        kept = [song.info is not None for song in songs]
        assert kept == [True, True, False, False]

    asyncio.run(scenario())


# ============== Autoplay ==============


def ids(recommendations):
    return "".join(rec["videoId"] for rec in recommendations)


RECOMMENDATIONS = [{"videoId": name} for name in "abcde"]


@pytest.mark.parametrize(
    "ratings, skips, expected",
    [
        ({}, {}, "abcde"),  # No signal keeps the recommended order.
        ({"c": 2, "d": 1}, {}, "cdabe"),  # Liked songs first, best first.
        ({"b": -1}, {}, "acdeb"),  # Disliked songs last.
        ({"b": -2}, {}, "acde"),  # Heavily disliked songs are never played.
        ({"a": -9}, {}, "bcde"),
        ({}, {"a": 1}, "abcde"),  # A single skip is noise.
        ({}, {"a": 2}, "bcdea"),  # Two skips count as one dislike.
        ({}, {"a": 4}, "bcde"),  # Four skips count as two: excluded.
        ({}, {"a": 500}, "bcde"),  # The penalty is capped but still excludes.
        ({"b": 2}, {"b": 4}, "abcde"),  # Likes and skips offset each other.
        ({"c": 1}, {"c": 2}, "abcde"),
        ({"a": -1, "b": -1}, {"b": 2}, "cdea"),
    ],
)
def test_rank_recommendations(ratings, skips, expected):
    assert ids(music_player.rank_recommendations(RECOMMENDATIONS, ratings, skips)) == expected
    assert ids(RECOMMENDATIONS) == "abcde"  # The input is not modified.


def test_blended_recommendations_use_ratings_and_skips(manager, monkeypatch):
    async def scenario():
        player = manager.get_player(1)
        player.recent_songs.append("seed")
        player.ytmusic.get_recommendations_async = AsyncMock(return_value=RECOMMENDATIONS)
        monkeypatch.setattr(music_player, "get_guild_ratings", lambda guild: {"d": 2, "b": -3})
        seen = []

        def skip_counts(guild_id, hours):
            seen.append((guild_id, hours))
            return {"a": 2}

        monkeypatch.setattr(music_player, "get_skip_counts", skip_counts)
        result = await manager._get_blended_recommendations(1, player, limit=5)
        assert ids(result) == "dcea"  # d liked, b excluded, a sunk by skips
        assert seen == [(1, music_player.SKIP_LOOKBACK_HOURS)]

    asyncio.run(scenario())


def test_forget_older_keeps_only_the_most_recent_songs():
    from autoplay import YouTubeMusicHandler

    handler = YouTubeMusicHandler()
    for number in range(30):
        handler.mark_played(f"video{number:02d}")
    assert handler.forget_older(25) == 5
    assert handler._played_videos_list[0] == "video05"
    assert handler._played_videos_set == set(handler._played_videos_list)
    assert len(handler._played_videos_set) == 25
    assert handler.forget_older(25) == 0
    assert handler.forget_older(100) == 0
    assert handler.forget_older(0) == 25
    assert not handler._played_videos_set


def test_autoplay_mixes_older_songs_back_in_when_everything_was_played(
    manager, monkeypatch, song_factory
):
    async def scenario():
        player = manager.get_player(1)
        player.autoplay_enabled = True
        player.recent_songs.append("seed")
        for number in range(30):
            player.ytmusic.mark_played(f"video{number:02d}")
        calls = []

        async def recommendations(guild_id, player, limit):
            calls.append(limit)
            return [] if len(calls) == 1 else [{"videoId": "video00"}]

        manager._get_blended_recommendations = recommendations
        song = song_factory()
        monkeypatch.setattr(music_player, "extract_song_info", AsyncMock(return_value=song))
        assert await manager._get_autoplay_song(1, player) is song
        assert len(calls) == 2
        assert len(player.ytmusic._played_videos_list) == music_player.AUTOPLAY_HISTORY_KEEP
        assert "mixing earlier" in player.notice
        assert song.source_type == "autoplay"

    asyncio.run(scenario())


def test_autoplay_says_so_when_it_finds_nothing(manager):
    async def scenario():
        player = manager.get_player(1)
        player.autoplay_enabled = True
        player.recent_songs.append("seed")
        manager._get_blended_recommendations = AsyncMock(return_value=[])
        assert await manager._get_autoplay_song(1, player) is None
        assert "could not find anything new" in player.notice

    asyncio.run(scenario())


def test_autoplay_notice_is_not_shown_if_it_was_turned_off(manager):
    async def scenario():
        player = manager.get_player(1)
        player.autoplay_enabled = False
        player.recent_songs.append("seed")
        assert await manager._get_autoplay_song(1, player) is None
        assert player.notice == ""

    asyncio.run(scenario())


# ============== Background tasks ==============


def test_skip_keeps_its_cleanup_task_referenced(manager, song_factory):
    async def scenario():
        voice, player, song = start_playing(manager, song_factory)
        await manager.add_to_queue(1, song)
        manager.start_playback(1)
        await voice.started.wait()
        assert manager.skip(1)
        pending = tuple(background._background_tasks)
        assert pending
        await asyncio.gather(*pending)
        await asyncio.sleep(0)
        assert not background._background_tasks
        await manager.disconnect(1)

    asyncio.run(scenario())


def test_play_log_task_stays_referenced_until_written(manager, monkeypatch, song_factory):
    async def scenario():
        written = Mock()
        monkeypatch.setattr(music_player.AuditLogger, "log_music", written)
        song = song_factory()
        song.guild_name, song.requested_by_id, song.requested_by_name = "Guild", 42, "Listener"
        music_player.MusicPlayerManager._log_play(manager, 1, song)
        pending = tuple(background._background_tasks)
        assert len(pending) == 1
        await asyncio.gather(*pending)
        written.assert_called_once_with(
            1, "Guild", 42, "Listener", song.video_id, song.title, 180, "search", "play"
        )
        await asyncio.sleep(0)
        assert not background._background_tasks

    asyncio.run(scenario())
