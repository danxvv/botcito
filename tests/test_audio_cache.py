"""Verify bounded startup waits and shared download ownership."""

import asyncio
from threading import Event
from time import monotonic
from unittest.mock import AsyncMock, Mock

import pytest
from yt_dlp.utils import DownloadError

import youtube
from audio_cache import AudioCache
from conftest import settle
from youtube import INFO_REUSE_SECONDS


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


# ============== Reusing the extraction ==============


class FakeYDL:
    """Stands in for yt-dlp, recording whether the song was extracted again."""

    def __init__(self, process_error=None):
        self.process_error = process_error
        self.processed = []
        self.extracted = []

    def process_ie_result(self, info, download):
        assert download
        self.processed.append(info)
        if self.process_error:
            raise self.process_error
        return {"processed": True}

    def extract_info(self, url, download):
        assert download
        self.extracted.append(url)
        return {"extracted": True}


def test_download_reuses_a_recent_extraction(song_factory):
    song = song_factory()
    song.info = {"formats": [{"url": "https://audio.example/a"}]}
    ydl = FakeYDL()
    assert AudioCache._download_info(ydl, song, Event()) == {"processed": True}
    assert ydl.extracted == []
    # yt-dlp may modify what it is given; the song's own copy must stay intact.
    assert ydl.processed[0] == song.info and ydl.processed[0] is not song.info


@pytest.mark.parametrize("state", ["missing", "stale"])
def test_download_extracts_again_without_a_usable_extraction(state, song_factory):
    song = song_factory()
    if state == "stale":
        song.info = {"formats": [{}]}
        song.extracted_at = monotonic() - INFO_REUSE_SECONDS - 1
    ydl = FakeYDL()
    assert AudioCache._download_info(ydl, song, Event()) == {"extracted": True}
    assert ydl.processed == []
    assert ydl.extracted == [song.webpage_url]


def test_download_extracts_again_if_the_old_extraction_fails(song_factory):
    song = song_factory()
    song.info = {"formats": [{}]}
    ydl = FakeYDL(process_error=DownloadError("format expired"))
    assert AudioCache._download_info(ydl, song, Event()) == {"extracted": True}
    assert ydl.extracted == [song.webpage_url]


def test_cancelled_download_does_not_start_over(song_factory):
    song = song_factory()
    song.info = {"formats": [{}]}
    cancelled = Event()
    cancelled.set()
    ydl = FakeYDL(process_error=DownloadError("Download cancelled"))
    with pytest.raises(DownloadError):
        AudioCache._download_info(ydl, song, cancelled)
    assert ydl.extracted == []


# ============== Lazily imported songs ==============


def fresh_song(**overrides):
    values = dict(
        url="https://audio.example/fresh",
        title="Full title",
        duration=180,
        thumbnail="",
        video_id="abcdefghijk",
        webpage_url="https://www.youtube.com/watch?v=abcdefghijk",
        info={"formats": [{}]},
    )
    return youtube.SongInfo(**{**values, **overrides})


def test_playlist_entry_is_extracted_once_before_its_download(tmp_path, monkeypatch):
    async def scenario():
        cache = AudioCache(tmp_path)
        entry = youtube.playlist_entry_song({"video_id": "abcdefghijk", "title": "Flat"})
        extract = AsyncMock(return_value=fresh_song())
        monkeypatch.setattr(youtube, "extract_song_info", extract)
        seen = []

        def download(song, cancelled):
            seen.append((song.resolved, song.title, song.fresh_info() is not None))
            path = tmp_path / "entry.webm"
            path.write_bytes(b"audio")
            return path

        monkeypatch.setattr(cache, "_download_sync", download)
        cache.retain(entry)
        assert await cache.ensure_downloaded(entry, timeout=2)
        assert seen == [(True, "Full title", True)]  # Resolved, with data to reuse.
        extract.assert_awaited_once_with("abcdefghijk")

    asyncio.run(scenario())


def test_unavailable_playlist_entry_is_never_downloaded(tmp_path, monkeypatch):
    async def scenario():
        cache = AudioCache(tmp_path)
        entry = youtube.playlist_entry_song({"video_id": "abcdefghijk"})
        monkeypatch.setattr(youtube, "extract_song_info", AsyncMock(return_value=None))
        download = Mock()
        monkeypatch.setattr(cache, "_download_sync", download)
        cache.retain(entry)
        assert not await cache.ensure_downloaded(entry, timeout=2)
        download.assert_not_called()

    asyncio.run(scenario())


def test_live_stream_found_after_resolving_is_streamed_not_downloaded(tmp_path, monkeypatch):
    async def scenario():
        cache = AudioCache(tmp_path)
        entry = youtube.playlist_entry_song({"video_id": "abcdefghijk"})
        monkeypatch.setattr(
            youtube, "extract_song_info", AsyncMock(return_value=fresh_song(is_live=True))
        )
        download = Mock()
        monkeypatch.setattr(cache, "_download_sync", download)
        cache.retain(entry)
        assert not await cache.ensure_downloaded(entry, timeout=2)
        assert entry.is_live and entry.resolved
        download.assert_not_called()

    asyncio.run(scenario())
