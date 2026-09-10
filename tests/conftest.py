"""Offline fixtures for music playback and Discord interactions."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

import music_player
from youtube import SongInfo


class FakeSource:
    def __init__(self):
        self.cleaned = False
        self.volume = 1.0

    def cleanup(self):
        self.cleaned = True


class FakeVoice:
    def __init__(self, channel_id=10):
        self.channel = SimpleNamespace(id=channel_id)
        self.connected = True
        self.playing = False
        self.paused = False
        self.source = None
        self.after = None
        self.sources = []
        self.started = asyncio.Event()

    @property
    def loop(self):
        return asyncio.get_running_loop()

    def is_connected(self):
        return self.connected

    def is_playing(self):
        return self.playing

    def is_paused(self):
        return self.paused

    def play(self, source, *, after):
        self.source = source
        self.after = after
        self.sources.append(source)
        self.playing = True
        self.started.set()

    def finish(self, error=None):
        self.playing = self.paused = False
        callback, self.after = self.after, None
        if self.source:
            self.source.cleanup()
        if callback:
            callback(error)

    def stop(self):
        self.finish()

    def pause(self):
        self.playing, self.paused = False, True

    def resume(self):
        self.playing, self.paused = True, False

    async def disconnect(self):
        self.connected = False


@pytest.fixture
def song_factory():
    def make(video_id="abcdefghijk", title="A song", duration=180):
        return SongInfo(
            url="https://audio.example/song",
            title=title,
            duration=duration,
            thumbnail="",
            video_id=video_id,
            webpage_url=f"https://www.youtube.com/watch?v={video_id}",
        )

    return make


@pytest.fixture
def manager(monkeypatch):
    manager = music_player.MusicPlayerManager()
    cache = Mock()
    cache.is_ready.return_value = False
    cache.ensure_downloaded = AsyncMock(return_value=False)
    monkeypatch.setattr(music_player, "audio_cache", cache)
    monkeypatch.setattr(manager, "_log_play", Mock())
    monkeypatch.setattr(
        manager,
        "_create_audio_source",
        AsyncMock(side_effect=lambda *a, **kw: FakeSource()),
    )
    return manager


@pytest.fixture
def interaction():
    message = SimpleNamespace(
        id=100, jump_url="https://discord.com/channels/1/2/100", edit=AsyncMock()
    )
    channel = SimpleNamespace(
        id=2,
        send=AsyncMock(return_value=message),
        fetch_message=AsyncMock(return_value=message),
    )
    message.channel = channel
    return SimpleNamespace(
        guild_id=1,
        guild=SimpleNamespace(id=1, name="Test server", me=Mock()),
        user=SimpleNamespace(
            id=42, display_name="Listener", voice=SimpleNamespace(channel=channel)
        ),
        channel=channel,
        response=SimpleNamespace(
            is_done=Mock(return_value=False),
            send_message=AsyncMock(),
            defer=AsyncMock(),
            edit_message=AsyncMock(),
            send_modal=AsyncMock(),
        ),
        followup=SimpleNamespace(send=AsyncMock()),
        edit_original_response=AsyncMock(return_value=message),
        original_response=AsyncMock(return_value=message),
    )


async def settle():
    for _ in range(15):
        await asyncio.sleep(0)
