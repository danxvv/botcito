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


# yt-dlp options for playlist extraction (flat mode)
_YDL_OPTIONS_PLAYLIST = {
    "format": "251/250/249/140/139/bestaudio/best",
    "noplaylist": False,
    "quiet": False,
    "no_warnings": False,
    "extract_flat": "in_playlist",
    "ignoreerrors": True,
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
        except ExtractorError:
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

    loop = asyncio.get_running_loop()
    info = await loop.run_in_executor(_executor, _extract_info, query)

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
    loop = asyncio.get_running_loop()
    info = await loop.run_in_executor(_executor, lambda: _extract_info(url, playlist=True))

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
