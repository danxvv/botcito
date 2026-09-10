"""Verify bounded startup waits and shared download ownership."""

import asyncio
from threading import Event

from audio_cache import AudioCache
from conftest import settle


def test_slow_download_does_not_delay_startup_or_get_cancelled(
    tmp_path, monkeypatch, song_factory
):
    async def scenario():
        cache = AudioCache(tmp_path)
        song = song_factory()
        release = Event()
        calls = []

        def download(song, cancelled):
            calls.append(song.video_id)
            release.wait(2)
            path = tmp_path / "song.webm"
            path.write_bytes(b"audio")
            return path

        monkeypatch.setattr(cache, "_download_sync", download)
        cache.retain(song)
        assert not await cache.ensure_downloaded(song, timeout=0.01)
        task = cache._download_tasks[song.video_id]
        assert not task.done()
        release.set()
        await asyncio.wait_for(task, 1)
        assert await cache.ensure_downloaded(song, timeout=0.01)
        assert calls == [song.video_id]
        cache.release(song)
        assert not list(tmp_path.iterdir())

    asyncio.run(scenario())


def test_duplicate_requests_share_one_download_and_do_not_delete_each_other(
    tmp_path, monkeypatch, song_factory
):
    async def scenario():
        cache = AudioCache(tmp_path)
        first, second = song_factory(), song_factory()
        calls = []

        def download(song, cancelled):
            calls.append(song.video_id)
            path = tmp_path / "shared.webm"
            path.write_bytes(b"audio")
            return path

        monkeypatch.setattr(cache, "_download_sync", download)
        cache.retain(first)
        cache.retain(second)
        await asyncio.gather(
            cache.ensure_downloaded(first), cache.ensure_downloaded(second)
        )
        assert len(calls) == 1
        cache.release(first)
        assert cache.is_ready(second.video_id)
        cache.release(second)
        assert not cache.is_ready(second.video_id)

    asyncio.run(scenario())


def test_cancelled_worker_cannot_leave_a_late_file(tmp_path, monkeypatch, song_factory):
    async def scenario():
        cache = AudioCache(tmp_path)
        song = song_factory()
        release = Event()
        worker_done = asyncio.Event()
        loop = asyncio.get_running_loop()

        def download(song, cancelled):
            release.wait(2)
            path = tmp_path / "late.webm"
            path.write_bytes(b"audio")
            loop.call_soon_threadsafe(worker_done.set)
            return path

        monkeypatch.setattr(cache, "_download_sync", download)
        cache.retain(song)
        await cache.ensure_downloaded(song, timeout=0.01)
        cache.release(song)
        await settle()
        release.set()
        await asyncio.wait_for(worker_done.wait(), 1)
        await settle()
        assert not cache.is_ready(song.video_id)
        assert not list(tmp_path.iterdir())

    asyncio.run(scenario())


def test_live_audio_is_streamed_without_downloading(
    tmp_path, monkeypatch, song_factory
):
    async def scenario():
        cache = AudioCache(tmp_path)
        song = song_factory()
        song.is_live = True
        assert not await cache.ensure_downloaded(song)
        assert not cache._download_tasks

    asyncio.run(scenario())
