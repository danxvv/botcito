"""Cover extraction safety, cancellation, and lazily imported songs without network access."""

import asyncio
import dataclasses
import threading
from time import monotonic
from unittest.mock import AsyncMock

import pytest
import yt_dlp
from yt_dlp.utils import DownloadCancelled, DownloadError

import youtube
from youtube import SongInfo


@pytest.mark.parametrize(
    "value, expected",
    [
        ("dQw4w9WgXcQ", True),
        ("abcdefghijk", True),
        ("a-b_c-d_e-f", True),
        ("hello world", False),
        ("short", False),
        ("twelve_chars", False),
        ("", False),
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", False),
    ],
)
def test_is_video_id(value, expected):
    assert youtube.is_video_id(value) is expected


@pytest.mark.parametrize(
    "query",
    [
        "hello world",
        "file:///etc/passwd",
        "ftp://example.com/song.mp3",
        "/etc/passwd",
        "javascript:alert(1)",
    ],
)
def test_extraction_refuses_anything_but_web_urls_and_video_ids(query, monkeypatch):
    async def scenario():
        run = AsyncMock()
        monkeypatch.setattr(youtube, "_run_extract", run)
        assert await youtube.extract_song_info(query) is None
        run.assert_not_awaited()

    asyncio.run(scenario())


def test_video_ids_and_searches_are_extracted(monkeypatch):
    async def scenario():
        run = AsyncMock(return_value=None)
        monkeypatch.setattr(youtube, "_run_extract", run)
        await youtube.extract_song_info("dQw4w9WgXcQ")
        run.assert_awaited_with("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        await youtube.search_youtube("hello world")
        run.assert_awaited_with("ytsearch1:hello world")

    asyncio.run(scenario())


def test_generic_extractor_is_never_loaded_so_internal_urls_are_not_fetched():
    options = youtube._get_options()
    assert "-generic" in options["allowed_extractors"]
    with yt_dlp.YoutubeDL({"logger": None, "quiet": True}) as control:
        assert "Generic" in control._ies  # yt-dlp loads it unless told otherwise
    with yt_dlp.YoutubeDL({**options, "logger": None, "quiet": True}) as ydl:
        assert "Generic" not in ydl._ies
        for url in (
            "http://127.0.0.1:9/audio.mp3",
            "http://169.254.169.254/latest/meta-data/",
            "http://localhost/internal",
        ):
            with pytest.raises(DownloadError, match="No suitable extractor"):
                ydl.extract_info(url, download=False)


def test_extractor_options_route_output_through_logging():
    assert youtube._get_options()["logger"] is youtube._YDL_LOGGER
    assert youtube._get_options(playlist=True)["extract_flat"] == "in_playlist"
    assert youtube._get_options()["noplaylist"] is True


def test_cancelled_extraction_stops_at_its_next_request(monkeypatch):
    cancelled = threading.Event()
    seen = []
    monkeypatch.setattr(yt_dlp.YoutubeDL, "urlopen", lambda self, req: seen.append(req))
    with youtube.CancellableYDL({"logger": None}, cancelled) as ydl:
        ydl.urlopen("https://example.com/one")
        cancelled.set()
        with pytest.raises(DownloadCancelled):
            ydl.urlopen("https://example.com/two")
    assert seen == ["https://example.com/one"]


def test_extraction_that_is_already_cancelled_does_no_work(monkeypatch):
    cancelled = threading.Event()
    cancelled.set()
    monkeypatch.setattr(
        youtube,
        "CancellableYDL",
        lambda *a, **k: pytest.fail("yt-dlp should not start"),
    )
    assert youtube._extract_info("https://www.youtube.com/watch?v=x", cancelled=cancelled) is None


def test_timed_out_extraction_is_cancelled_and_keeps_its_slot_until_it_exits(monkeypatch):
    async def scenario():
        monkeypatch.setattr(youtube, "EXTRACT_TIMEOUT", 0.05)
        monkeypatch.setattr(youtube, "_extract_semaphore", asyncio.Semaphore(3))
        started, flags, release = [], [], threading.Event()

        def stuck(url, *, playlist=False, cancelled=None):
            started.append(url)
            flags.append(cancelled)
            release.wait(2)  # Ignores the cancel flag, like a thread stuck in a socket read.
            return {"id": url}

        monkeypatch.setattr(youtube, "_extract_info", stuck)
        timed_out = await asyncio.gather(*(youtube._run_extract(f"u{i}") for i in range(3)))
        assert timed_out == [None] * 3
        assert all(flag.is_set() for flag in flags)  # Each worker was told to stop.
        # The callers gave up, but all three worker threads are still stuck, so a new
        # request must wait for a slot instead of piling a fourth thread on top.
        assert await youtube._run_extract("fourth") is None
        assert len(started) == 3
        release.set()
        await asyncio.sleep(0.2)
        # Slots free up as the workers really exit.
        assert await youtube._run_extract("later") == {"id": "later"}
        assert len(started) == 4

    asyncio.run(scenario())


def test_cancelling_the_caller_cancels_the_worker(monkeypatch):
    async def scenario():
        monkeypatch.setattr(youtube, "_extract_semaphore", asyncio.Semaphore(3))
        flags, entered = [], threading.Event()

        def cooperative(url, *, playlist=False, cancelled=None):
            flags.append(cancelled)
            entered.set()
            cancelled.wait(2)
            return None

        monkeypatch.setattr(youtube, "_extract_info", cooperative)
        task = asyncio.create_task(youtube._run_extract("u"))
        while not entered.is_set():
            await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert flags[0].is_set()

    asyncio.run(scenario())


def test_playlist_entries_become_unresolved_songs():
    song = youtube.playlist_entry_song(
        {"video_id": "abcdefghijk", "title": "Entry", "duration": 211.0}
    )
    assert (song.title, song.duration, song.url) == ("Entry", 211, "")
    assert song.webpage_url == "https://www.youtube.com/watch?v=abcdefghijk"
    assert not song.resolved and song.info is None
    unknown = youtube.playlist_entry_song({"video_id": "abcdefghijk"})
    assert (unknown.title, unknown.duration) == ("Unknown", 0)


def test_playlist_extraction_marks_private_and_deleted_videos(monkeypatch):
    async def scenario():
        monkeypatch.setattr(
            youtube,
            "_run_extract",
            AsyncMock(
                return_value={
                    "_type": "playlist",
                    "entries": [
                        {"id": "aaaaaaaaaaa", "title": "Fine", "duration": 100},
                        {"id": "bbbbbbbbbbb", "title": "[Private video]"},
                        {"id": "ccccccccccc", "title": "[Deleted video]"},
                        None,
                        {"title": "No id"},
                    ],
                }
            ),
        )
        entries = await youtube.extract_playlist("https://www.youtube.com/playlist?list=PL1")
        assert [(e["video_id"], e["available"]) for e in entries] == [
            ("aaaaaaaaaaa", True),
            ("bbbbbbbbbbb", False),
            ("ccccccccccc", False),
        ]
        assert entries[0]["duration"] == 100

    asyncio.run(scenario())


def make_stub(video_id="abcdefghijk"):
    return youtube.playlist_entry_song({"video_id": video_id, "title": "Flat title"})


def make_fresh(video_id="abcdefghijk", **overrides):
    values = dict(
        url="https://audio.example/fresh",
        title="Full title",
        duration=180,
        thumbnail="thumb",
        video_id=video_id,
        webpage_url=f"https://www.youtube.com/watch?v={video_id}",
        info={"formats": [{}]},
    )
    return SongInfo(**{**values, **overrides})


def test_concurrent_callers_share_one_extraction_and_keep_the_requester(monkeypatch):
    async def scenario():
        gate = asyncio.Event()
        calls = []

        async def extract(query):
            calls.append(query)
            await gate.wait()
            return make_fresh()

        monkeypatch.setattr(youtube, "extract_song_info", extract)
        song = make_stub()
        song.requested_by_id, song.requested_by_name = 42, "Listener"
        waiting = [asyncio.create_task(youtube.ensure_resolved(song)) for _ in range(3)]
        await asyncio.sleep(0)
        gate.set()
        assert await asyncio.gather(*waiting) == [True, True, True]
        assert calls == ["abcdefghijk"]
        assert song.resolved and song.url == "https://audio.example/fresh"
        assert (song.title, song.duration, song.thumbnail) == ("Full title", 180, "thumb")
        assert (song.requested_by_id, song.requested_by_name) == (42, "Listener")
        assert song.info is not None
        # Already resolved songs are not extracted again.
        assert await youtube.ensure_resolved(song)
        assert calls == ["abcdefghijk"]

    asyncio.run(scenario())


def test_unavailable_song_is_not_retried_immediately(monkeypatch):
    async def scenario():
        extract = AsyncMock(return_value=None)
        monkeypatch.setattr(youtube, "extract_song_info", extract)
        song = make_stub()
        assert not await youtube.ensure_resolved(song)
        assert not await youtube.ensure_resolved(song)
        assert extract.await_count == 1
        assert not song.resolved
        # After the cool-down it may be tried again.
        song._failed_at = monotonic() - youtube.RESOLVE_RETRY_SECONDS - 1
        extract.return_value = make_fresh()
        assert await youtube.ensure_resolved(song)
        assert extract.await_count == 2

    asyncio.run(scenario())


def test_cancelling_one_caller_does_not_cancel_the_shared_extraction(monkeypatch):
    async def scenario():
        gate = asyncio.Event()

        async def extract(query):
            await gate.wait()
            return make_fresh()

        monkeypatch.setattr(youtube, "extract_song_info", extract)
        song = make_stub()
        impatient = asyncio.create_task(youtube.ensure_resolved(song))
        patient = asyncio.create_task(youtube.ensure_resolved(song))
        await asyncio.sleep(0)
        impatient.cancel()
        gate.set()
        assert await patient is True
        assert song.resolved

    asyncio.run(scenario())


def test_extraction_data_is_only_trusted_for_a_few_minutes():
    song = make_fresh()
    assert song.fresh_info() is song.info
    song.extracted_at = monotonic() - youtube.INFO_REUSE_SECONDS - 1
    assert song.fresh_info() is None
    assert make_fresh(info=None).fresh_info() is None


def test_song_equality_ignores_extraction_data():
    assert make_fresh(info=None).url == make_fresh().url
    first = make_fresh()
    second = dataclasses.replace(first, info={"other": True})
    assert second.info != first.info
    assert first == second
