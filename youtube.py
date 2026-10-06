"""YouTube handler for extracting audio URLs using yt-dlp."""

import asyncio
import atexit
import logging
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from time import monotonic
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import yt_dlp
from yt_dlp.utils import DownloadCancelled, DownloadError, ExtractorError

logger = logging.getLogger(__name__)

VIDEO_ID_RE = re.compile(r"[A-Za-z0-9_-]{11}")
# Streaming URLs expire after hours; extraction data is only trusted for a few minutes.
INFO_REUSE_SECONDS = 300
# A song that could not be extracted is not tried again for this long.
RESOLVE_RETRY_SECONDS = 30
UNAVAILABLE_TITLES = {"[Private video]", "[Deleted video]"}


@dataclass
class SongInfo:
    """Information about a song."""

    url: str
    title: str
    duration: int  # in seconds
    thumbnail: str
    video_id: str
    webpage_url: str
    local_path: str | None = None  # Path to cached audio file
    requested_by_id: int = 0
    requested_by_name: str = "Autoplay"
    guild_name: str = "Unknown"
    source_type: str = "search"
    entry_id: str = field(default_factory=lambda: uuid4().hex)
    extracted_at: float = field(default_factory=monotonic)
    is_live: bool = False
    # False for lazily imported playlist entries that still need a full extraction.
    resolved: bool = True
    # The yt-dlp result, kept briefly so the audio download can skip a second extraction.
    info: dict | None = field(default=None, repr=False, compare=False)
    _resolving: asyncio.Future | None = field(
        default=None, init=False, repr=False, compare=False
    )
    _failed_at: float | None = field(default=None, init=False, repr=False, compare=False)

    def fresh_info(self) -> dict | None:
        """Return the extraction data if it is recent enough to download from."""
        if self.info is not None and monotonic() - self.extracted_at < INFO_REUSE_SECONDS:
            return self.info
        return None

    def update_from(self, fresh: "SongInfo") -> None:
        """Take extraction results from a fresh copy, keeping who requested the song."""
        self.url = fresh.url
        self.title = fresh.title
        self.duration = fresh.duration
        self.thumbnail = fresh.thumbnail
        self.webpage_url = fresh.webpage_url
        self.extracted_at = fresh.extracted_at
        self.is_live = fresh.is_live
        self.info = fresh.info
        self.resolved = True


def is_video_id(value: str) -> bool:
    """Check whether a string is an 11-character YouTube video ID."""
    return VIDEO_ID_RE.fullmatch(value) is not None


def watch_url(video_id: str) -> str:
    """Build the canonical watch URL for a video ID."""
    return f"https://www.youtube.com/watch?v={video_id}"


_YDL_LOGGER = logging.getLogger("yt_dlp")

# Options shared by every yt-dlp call.
_YDL_COMMON_OPTIONS = {
    "format": "251/250/249/140/139/bestaudio/best",
    # yt-dlp's output goes through logging (progress chatter is DEBUG-level).
    "logger": _YDL_LOGGER,
    "no_warnings": False,
    "socket_timeout": 15,
    "retries": 2,
    "fragment_retries": 2,
    "extractor_retries": 2,
    # The generic extractor fetches any URL it is given, including internal
    # addresses, so only site-specific extractors are allowed.
    "allowed_extractors": ["default", "-generic"],
    # Enable multiple JS runtimes as fallback
    "js_runtimes": {"deno": {}, "node": {}, "bun": {}},
    # The yt-dlp-ejs package (yt-dlp[default]) ships the challenge solver; this
    # only downloads it from GitHub if the package is missing.
    "remote_components": {"ejs:github": {}},
    # Use TV client which tends to work better
    "extractor_args": {
        "youtube": {
            "player_client": ["tv", "web"],
            "player_js_variant": ["tv"],
        }
    },
}

# yt-dlp options for playlist extraction (flat mode)
_YDL_OPTIONS_PLAYLIST = {
    **_YDL_COMMON_OPTIONS,
    "noplaylist": False,
    "extract_flat": "in_playlist",
    "ignoreerrors": True,
}

# User-Agent to use for requests (needed for FFmpeg too)
_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# Cookie file path (place cookies.txt in project root to use)
_COOKIES_FILE = Path(__file__).parent / "cookies.txt"

# yt-dlp options for single video extraction
_YDL_OPTIONS_SINGLE = {
    **_YDL_COMMON_OPTIONS,
    "noplaylist": True,
    # Add http headers to help with 403 issues
    "http_headers": {"User-Agent": _USER_AGENT},
}

# Thread pool for running blocking yt-dlp operations
_executor = ThreadPoolExecutor(max_workers=3)
_extract_semaphore = asyncio.Semaphore(3)
EXTRACT_TIMEOUT = 45
atexit.register(_executor.shutdown, wait=False)


class CancellableYDL(yt_dlp.YoutubeDL):
    """YoutubeDL that stops at its next network request once cancelled."""

    def __init__(self, params: dict, cancelled: threading.Event) -> None:
        self._cancelled = cancelled
        super().__init__(params)

    def urlopen(self, req):
        if self._cancelled.is_set():
            raise DownloadCancelled("Extraction cancelled")
        return super().urlopen(req)


def _get_options(playlist: bool = False) -> dict:
    """Get yt-dlp options with cookies if available."""
    opts = dict(_YDL_OPTIONS_PLAYLIST if playlist else _YDL_OPTIONS_SINGLE)
    if _COOKIES_FILE.exists():
        opts["cookiefile"] = str(_COOKIES_FILE)
        logger.debug("Using cookies from %s", _COOKIES_FILE)
    return opts


def _extract_info(
    url: str, *, playlist: bool = False, cancelled: threading.Event | None = None
) -> dict | None:
    """Extract info from URL (blocking operation)."""
    cancelled = cancelled or threading.Event()
    if cancelled.is_set():
        return None
    with CancellableYDL(_get_options(playlist), cancelled) as ydl:
        try:
            return ydl.extract_info(url, download=False)
        except DownloadCancelled:
            return None
        except DownloadError as e:
            error_msg = str(e)
            if "JavaScript" in error_msg or "nsig" in error_msg:
                logger.error(
                    "yt-dlp requires Deno, Node.js, or Bun for YouTube extraction."
                )
            else:
                logger.warning("yt-dlp could not extract %s: %s", url, error_msg)
            return None
        except (ExtractorError, OSError):
            logger.warning("yt-dlp could not extract %s", url, exc_info=True)
            return None


async def _run_extract(query: str, *, playlist: bool = False) -> dict | None:
    """Run yt-dlp in the bounded extraction pool."""
    loop = asyncio.get_running_loop()
    try:
        await asyncio.wait_for(_extract_semaphore.acquire(), EXTRACT_TIMEOUT)
    except asyncio.TimeoutError:
        logger.error("yt-dlp extraction pool is busy; gave up on %s", query)
        return None

    cancelled = threading.Event()
    try:
        future = loop.run_in_executor(
            _executor,
            partial(_extract_info, query, playlist=playlist, cancelled=cancelled),
        )
    except BaseException:
        _extract_semaphore.release()
        raise

    def finished(done: asyncio.Future) -> None:
        # A slot frees when the worker thread really exits, not when we stop waiting,
        # so stuck extractions can never pile up more than the pool size.
        _extract_semaphore.release()
        if not done.cancelled():
            done.exception()  # Mark a late failure as retrieved.

    future.add_done_callback(finished)
    try:
        return await asyncio.wait_for(asyncio.shield(future), EXTRACT_TIMEOUT)
    except asyncio.TimeoutError:
        logger.error("yt-dlp extraction timed out for %s", query)
        cancelled.set()  # The worker stops at its next network request.
        return None
    except asyncio.CancelledError:
        cancelled.set()
        raise


async def _unwrap_search_result(info: dict) -> dict | None:
    """Return the first playable entry from a yt-dlp search/playlist result."""
    entries = info.get("entries")
    if not entries:
        return info

    for entry in entries:
        if not entry:
            continue
        if entry.get("url") and (entry.get("formats") or entry.get("acodec")):
            return entry
        video_id = entry.get("id")
        if video_id:
            return await _run_extract(watch_url(video_id))
        entry_url = entry.get("webpage_url") or entry.get("url")
        if entry_url:
            return await _run_extract(entry_url)
    return None


def _is_extractable(query: str) -> bool:
    """Allow only web URLs and the internal search prefix, never local paths or other schemes."""
    return query.startswith(("https://", "http://", "ytsearch1:"))


async def extract_song_info(query: str) -> SongInfo | None:
    """
    Extract song information from a URL or video ID.

    Free text is not accepted here; use search_youtube() for that.

    Args:
        query: YouTube URL or video ID

    Returns:
        SongInfo object or None if extraction failed
    """
    # Handle video IDs from ytmusicapi
    if is_video_id(query):
        query = watch_url(query)
    if not _is_extractable(query):
        logger.warning("Refusing to extract unsupported query %r", query[:100])
        return None

    info = await _run_extract(query)

    if not info:
        return None

    info = await _unwrap_search_result(info)
    if not info:
        return None

    # Get the best audio URL
    url = info.get("url")
    if not url:
        # Try to get from formats
        formats = info.get("formats", [])
        audio_formats = [f for f in formats if f.get("acodec") != "none"]
        if audio_formats:
            url = audio_formats[-1].get("url")

    if not url:
        return None

    return SongInfo(
        url=url,
        title=info.get("title", "Unknown"),
        duration=info.get("duration", 0) or 0,
        thumbnail=info.get("thumbnail", ""),
        video_id=info.get("id", ""),
        webpage_url=info.get("webpage_url", query),
        is_live=bool(info.get("is_live")),
        info=info if info.get("formats") else None,
    )


def playlist_entry_song(entry: dict) -> SongInfo:
    """Create an unresolved song from a flat playlist entry; it is extracted when needed."""
    video_id = entry["video_id"]
    return SongInfo(
        url="",
        title=entry.get("title") or "Unknown",
        duration=int(entry.get("duration") or 0),
        thumbnail=entry.get("thumbnail") or "",
        video_id=video_id,
        webpage_url=watch_url(video_id),
        resolved=False,
    )


async def ensure_resolved(song: SongInfo) -> bool:
    """Extract a lazily imported song once, sharing the work between concurrent callers."""
    if song.resolved:
        return True
    if song._failed_at is not None and monotonic() - song._failed_at < RESOLVE_RETRY_SECONDS:
        return False
    if song._resolving is None or song._resolving.done():
        song._resolving = asyncio.ensure_future(_resolve(song))
    return await asyncio.shield(song._resolving)


async def _resolve(song: SongInfo) -> bool:
    fresh = await extract_song_info(song.video_id)
    if fresh is None:
        song._failed_at = monotonic()
        return False
    song._failed_at = None
    song.update_from(fresh)
    return True


async def extract_playlist(url: str) -> list[dict]:
    """
    Extract all video entries from a playlist URL.

    Args:
        url: YouTube playlist URL

    Returns:
        List of video entries with basic info (video_id, title, duration, url);
        private and deleted videos are included with ``available`` set to False
    """
    info = await _run_extract(url, playlist=True)

    if not info:
        return []

    # Check if it's a playlist
    if info.get("_type") == "playlist" or "entries" in info:
        entries = info.get("entries", [])
        return [
            {
                "video_id": e.get("id"),
                "title": e.get("title", "Unknown"),
                "duration": e.get("duration") or 0,
                "url": e.get("url") or watch_url(e.get("id")),
                "available": e.get("title") not in UNAVAILABLE_TITLES,
            }
            for e in entries
            if e and e.get("id")
        ]

    # Single video
    return [
        {
            "video_id": info.get("id"),
            "title": info.get("title", "Unknown"),
            "duration": info.get("duration") or 0,
            "url": info.get("webpage_url", url),
            "available": True,
        }
    ]


_YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "music.youtube.com", "m.youtube.com"}


def is_playlist_url(url: str) -> bool:
    """Check if the URL is a playlist."""
    parsed = urlparse(url)
    return parsed.hostname in {*_YOUTUBE_HOSTS, "youtu.be"} and (
        bool(parse_qs(parsed.query).get("list")) or parsed.path == "/playlist"
    )


def single_video_url(url: str) -> str | None:
    """Return the individual video in a YouTube URL, without its playlist."""
    parsed = urlparse(url)
    if parsed.hostname == "youtu.be":
        video_id = parsed.path.strip("/").split("/")[0]
    elif parsed.hostname in _YOUTUBE_HOSTS:
        video_id = parse_qs(parsed.query).get("v", [""])[0]
        if parsed.path.startswith(("/shorts/", "/live/")):
            video_id = parsed.path.split("/")[2]
    else:
        return None
    return watch_url(video_id) if video_id else None


async def search_youtube(query: str) -> SongInfo | None:
    """
    Search YouTube and return the first result.

    Args:
        query: Search query

    Returns:
        SongInfo for the first result or None
    """
    search_url = f"ytsearch1:{query}"
    return await extract_song_info(search_url)
