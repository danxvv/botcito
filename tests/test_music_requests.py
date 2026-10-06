"""Verify search routing, playlist choices, progress, and cancellation."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from commands import music_requests
from conftest import FakeVoice, settle
from youtube import is_playlist_url, single_video_url


@pytest.fixture
def job(manager, monkeypatch, interaction):
    monkeypatch.setattr(music_requests, "player_manager", manager)
    message = interaction.edit_original_response.return_value
    job = music_requests.MusicRequest(interaction, message, "hello world", "search")
    job.connect = AsyncMock()
    manager.get_player(1).voice_client = FakeVoice()
    return job


def test_eleven_character_text_is_searched(job, monkeypatch, song_factory):
    async def scenario():
        song = song_factory()
        search = AsyncMock(return_value=song)
        extract = AsyncMock()
        monkeypatch.setattr(
            music_requests.ytmusic, "search_songs_async", AsyncMock(return_value=[])
        )
        monkeypatch.setattr(music_requests, "search_youtube", search)
        monkeypatch.setattr(music_requests, "extract_song_info", extract)
        assert await job.resolve_song("hello world") is song
        search.assert_awaited_once_with("hello world")
        extract.assert_not_awaited()

    asyncio.run(scenario())


def test_autocomplete_selection_extracts_directly(job, monkeypatch, song_factory):
    async def scenario():
        song = song_factory()
        extract = AsyncMock(return_value=song)
        monkeypatch.setattr(music_requests, "extract_song_info", extract)
        assert await job.resolve_song(f"yt:{song.video_id}") is song
        extract.assert_awaited_once_with(song.video_id)

    asyncio.run(scenario())


@pytest.mark.parametrize("choice", ["song", "playlist"])
def test_ambiguous_url_respects_user_choice(choice, job, manager, song_factory):
    async def scenario():
        job.query = "https://www.youtube.com/watch?v=abcdefghijk&list=PL123"
        job.choose = AsyncMock(return_value=choice)
        job.import_playlist = AsyncMock()
        job.resolve_song = AsyncMock(return_value=song_factory())
        await job.run()
        job.choose.assert_awaited_once()
        if choice == "playlist":
            job.import_playlist.assert_awaited_once()
            job.resolve_song.assert_not_awaited()
        else:
            job.resolve_song.assert_awaited_once_with(
                "https://www.youtube.com/watch?v=abcdefghijk"
            )
            job.import_playlist.assert_not_awaited()
        await settle()
        await manager.disconnect(1)

    asyncio.run(scenario())


def test_playlist_is_queued_without_extracting_every_song(
    job, manager, monkeypatch
):
    async def scenario():
        job.query = "https://www.youtube.com/playlist?list=PL123"
        monkeypatch.setattr(
            music_requests,
            "extract_playlist",
            AsyncMock(
                return_value=[
                    {"video_id": "first", "title": "First", "duration": 200},
                    {"video_id": "second", "title": "Second", "duration": 0},
                    {"video_id": "third", "title": "Third", "duration": 90},
                ]
            ),
        )
        extract = AsyncMock()
        monkeypatch.setattr(music_requests, "extract_song_info", extract)
        await job.run()
        voice = manager.get_player(1).voice_client
        await asyncio.wait_for(voice.started.wait(), 1)
        extract.assert_not_awaited()
        current = manager.get_current_song(1)
        assert (current.title, current.duration, current.resolved) == ("First", 200, False)
        assert [song.title for song in manager.get_queue(1)] == ["Second", "Third"]
        assert all(song.source_type == "playlist" for song in manager.get_queue(1))
        assert job.added == 3
        assert "**3**" in job.message.edit.call_args.kwargs["content"]
        await manager.disconnect(1)

    asyncio.run(scenario())


def test_stopping_playlist_prevents_late_entries(job, manager, monkeypatch):
    async def scenario():
        job.query = "https://www.youtube.com/playlist?list=PL123"
        monkeypatch.setattr(
            music_requests,
            "extract_playlist",
            AsyncMock(
                return_value=[{"video_id": name} for name in ("first", "second", "third")]
            ),
        )
        enqueue, calls = job.enqueue, []

        async def stop_during_second_entry(song, source):
            calls.append(song.video_id)
            if len(calls) == 2:
                await manager.disconnect(1)
            return await enqueue(song, source)

        job.enqueue = stop_during_second_entry
        await job.run()
        assert calls == ["first", "second"]
        assert not manager.get_queue(1)
        assert manager.get_current_song(1) is None
        assert "cancelled" in job.message.edit.call_args.kwargs["content"]

    asyncio.run(scenario())


def test_playlist_reports_unavailable_songs(job, manager, monkeypatch):
    async def scenario():
        monkeypatch.setattr(
            music_requests,
            "extract_playlist",
            AsyncMock(
                return_value=[
                    {"video_id": "bad", "title": "[Private video]", "available": False},
                    {"video_id": "good", "title": "Good"},
                ]
            ),
        )
        await job.import_playlist()
        assert job.added == 1
        assert job.unavailable == 1
        assert "**1** unavailable" in job.message.edit.call_args.kwargs["content"]
        await settle()
        await manager.disconnect(1)

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "url, expected",
    [
        ("my list=songs", False),
        ("https://example.com/playlist?list=123", False),
        ("https://evil.example/watch?v=abcdefghijk&list=123", False),
        ("https://www.youtube.com.evil.example/playlist?list=123", False),
        ("https://www.youtube.com/watch?v=abcdefghijk", False),
        ("https://youtu.be/abcdefghijk", False),
        ("https://music.youtube.com/watch?v=abcdefghijk&list=123", True),
        ("https://www.youtube.com/playlist?list=PL123", True),
        ("https://www.youtube.com/playlist", True),
        ("https://m.youtube.com/watch?v=abcdefghijk&list=RD123", True),
        ("https://youtu.be/abcdefghijk?list=123", True),
        ("", False),
    ],
)
def test_is_playlist_url(url, expected):
    assert is_playlist_url(url) is expected


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://youtu.be/abcdefghijk?list=123&t=2", "https://www.youtube.com/watch?v=abcdefghijk"),
        ("https://www.youtube.com/watch?v=abcdefghijk&list=1", "https://www.youtube.com/watch?v=abcdefghijk"),
        ("https://music.youtube.com/watch?v=abcdefghijk", "https://www.youtube.com/watch?v=abcdefghijk"),
        ("https://www.youtube.com/shorts/abcdefghijk", "https://www.youtube.com/watch?v=abcdefghijk"),
        ("https://www.youtube.com/live/abcdefghijk?feature=share", "https://www.youtube.com/watch?v=abcdefghijk"),
        ("https://www.youtube.com/playlist?list=123", None),
        ("https://www.youtube.com/shorts/", None),
        ("https://youtu.be/", None),
        ("https://example.com/watch?v=abcdefghijk", None),
        ("not a url", None),
    ],
)
def test_single_video_url(url, expected):
    assert single_video_url(url) == expected


def test_play_request_connects_the_controls_and_starts_audio(
    manager, monkeypatch, interaction, song_factory
):
    async def scenario():
        import discord
        from unittest.mock import Mock

        song = song_factory()
        voice = FakeVoice(channel_id=10)
        manager.get_player(1).voice_client = voice
        interaction.channel.id = 10
        interaction.channel.permissions_for = Mock(
            return_value=Mock(connect=True, speak=True)
        )
        interaction.user = Mock(spec=discord.Member)
        interaction.user.id = 42
        interaction.user.display_name = "Listener"
        interaction.user.voice = Mock(channel=interaction.channel)
        monkeypatch.setattr(music_requests, "player_manager", manager)
        monkeypatch.setattr(
            music_requests, "extract_song_info", AsyncMock(return_value=song)
        )
        ensure_panel = AsyncMock()
        monkeypatch.setattr(music_requests.panels, "ensure", ensure_panel)
        await music_requests.request_play(interaction, f"yt:{song.video_id}")
        await asyncio.wait_for(voice.started.wait(), 1)
        assert manager.get_current_song(1) is song
        assert not manager.get_player(1)._request_tasks
        ensure_panel.assert_awaited_once_with(interaction)
        assert (
            "Preparing"
            in interaction.edit_original_response.return_value.edit.call_args.kwargs[
                "content"
            ]
        )
        await manager.disconnect(1)

    asyncio.run(scenario())
