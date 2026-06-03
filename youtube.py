"""YouTube handler for extracting audio URLs using yt-dlp."""

import atexit
import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import yt_dlp
from yt_dlp.utils import DownloadError, ExtractorError


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


# yt-dlp options for playlist extraction (flat mode)
_YDL_OPTIONS_PLAYLIST = {
    "format": "251/250/249/140/139/bestaudio/best",
    "noplaylist": False,
    "quiet": False,
    "no_warnings": False,
    "extract_flat": "in_playlist",
    "ignoreerrors": True,
    "socket_timeout": 15,
    "retries": 2,
    "fragment_retries": 2,
    "extractor_retries": 2,
    # Enable multiple JS runtimes as fallback
    "js_runtimes": {"deno": {}, "node": {}, "bun": {}},
    # Enable remote EJS challenge solver scripts
    "remote_components": {"ejs:github": {}},
    # Use TV client which tends to work better
    "extractor_args": {
        "youtube": {
            "player_client": ["tv", "web"],
            "player_js_variant": ["tv"],
        }
    },
}

# User-Agent to use for requests (needed for FFmpeg too)
_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# Cookie file path (place cookies.txt in project root to use)
_COOKIES_FILE = Path(__file__).parent / "cookies.txt"

# yt-dlp options for single video extraction
_YDL_OPTIONS_SINGLE = {
    # Prefer audio-only, fallback to best available (let FFmpeg handle transcoding)
    "format": "251/250/249/140/139/bestaudio/best",
    "noplaylist": True,
    "quiet": False,
    "no_warnings": False,
    # Add http headers to help with 403 issues
    "http_headers": {"User-Agent": _USER_AGENT},
    "socket_timeout": 15,
    "retries": 2,
    "fragment_retries": 2,
    "extractor_retries": 2,
    # Enable multiple JS runtimes as fallback
    "js_runtimes": {"deno": {}, "node": {}, "bun": {}},
    # Enable remote EJS challenge solver scripts
    "remote_components": {"ejs:github": {}},
    # Use TV client which tends to work better with cookies
    "extractor_args": {
        "youtube": {
            "player_client": ["tv", "web"],
            "player_js_variant": ["tv"],
        }
    },
}

# Thread pool for running blocking yt-dlp operations
_executor = ThreadPoolExecutor(max_workers=3)
_extract_semaphore = asyncio.Semaphore(3)
EXTRACT_TIMEOUT = 45
atexit.register(_executor.shutdown, wait=False)


def _get_options(playlist: bool = False) -> dict:
    """Get yt-dlp options with cookies if available."""
    opts = dict(_YDL_OPTIONS_PLAYLIST if playlist else _YDL_OPTIONS_SINGLE)
    if _COOKIES_FILE.exists():
        opts["cookiefile"] = str(_COOKIES_FILE)
        print(f"[DEBUG] Using cookies from: {_COOKIES_FILE}")
    return opts


def _extract_info(url: str, *, playlist: bool = False) -> dict | None:
    """Extract info from URL (blocking operation)."""
    opts = _get_options(playlist)
    with yt_dlp.YoutubeDL(opts) as ydl:
        try:
            return ydl.extract_info(url, download=False)
        except DownloadError as e:
            error_msg = str(e)
            if "JavaScript" in error_msg or "nsig" in error_msg:
                print("Error: yt-dlp requires Deno/Node.js for YouTube.")
                print("Install Deno: https://deno.land")
            return None
        except (ExtractorError, OSError):
            return None


async def _run_extract(query: str, *, playlist: bool = False) -> dict | None:
    """Run yt-dlp in the bounded extraction pool."""
    loop = asyncio.get_running_loop()
    async with _extract_semaphore:
        try:
            return await asyncio.wait_for(
                loop.run_in_executor(_executor, lambda: _extract_info(query, playlist=playlist)),
                timeout=EXTRACT_TIMEOUT,
            )
        except asyncio.TimeoutError:
            print(f"[ERROR] yt-dlp extraction timed out for: {query}")
            return None


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
            return await _run_extract(f"https://www.youtube.com/watch?v={video_id}")
        entry_url = entry.get("webpage_url") or entry.get("url")
        if entry_url:
            return await _run_extract(entry_url)
    return None


async def extract_song_info(query: str) -> SongInfo | None:
    """
    Extract song information from a URL or video ID.

    Args:
        query: YouTube URL, video ID, or search query

    Returns:
        SongInfo object or None if extraction failed
    """
    # Handle video IDs from ytmusicapi
    if len(query) == 11 and not query.startswith("http"):
        query = f"https://www.youtube.com/watch?v={query}"

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
    )


async def extract_playlist(url: str) -> list[dict]:
    """
    Extract all video entries from a playlist URL.

    Args:
        url: YouTube playlist URL

    Returns:
        List of video entries with basic info (id, title)
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
                "url": e.get("url") or f"https://www.youtube.com/watch?v={e.get('id')}",
            }
            for e in entries
            if e and e.get("id")
        ]

    # Single video
    return [
        {
            "video_id": info.get("id"),
            "title": info.get("title", "Unknown"),
            "url": info.get("webpage_url", url),
        }
    ]


def is_playlist_url(url: str) -> bool:
    """Check if the URL is a playlist."""
    return "list=" in url or "/playlist" in url


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
