"""YouTube handler for extracting audio URLs using yt-dlp."""

import atexit
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import yt_dlp
from yt_dlp.utils import DownloadError, ExtractorError

logger = logging.getLogger(__name__)


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


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
HTTP_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
}
COOKIES_FILE = Path(__file__).parent / "cookies.txt"
YTDLP_AUDIO_FORMAT = "bestaudio[acodec=opus]/bestaudio[ext=m4a]/bestaudio/best"


_YDL_COMMON_OPTIONS = {
    "format": YTDLP_AUDIO_FORMAT,
    "quiet": True,
    "no_warnings": True,
    "http_headers": HTTP_HEADERS,
    "socket_timeout": 15,
    "retries": 3,
    "fragment_retries": 3,
    "extractor_retries": 3,
    # Enable multiple JS runtimes as fallback for YouTube signature challenges.
    "js_runtimes": {"deno": {}, "node": {}, "bun": {}},
    "extractor_args": {
        "youtube": {
            "player_client": ["android", "web"],
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

# yt-dlp options for single video extraction
_YDL_OPTIONS_SINGLE = {
    **_YDL_COMMON_OPTIONS,
    "noplaylist": True,
}

# Thread pool for running blocking yt-dlp operations
_executor = ThreadPoolExecutor(max_workers=3)
atexit.register(_executor.shutdown, wait=False)


def _get_options(playlist: bool = False) -> dict:
    """Get yt-dlp options with cookies if available."""
    opts = dict(_YDL_OPTIONS_PLAYLIST if playlist else _YDL_OPTIONS_SINGLE)
    if COOKIES_FILE.exists():
        opts["cookiefile"] = str(COOKIES_FILE)
        logger.debug("Using yt-dlp cookies from %s", COOKIES_FILE)
    return opts


def _select_audio_url(info: dict) -> str | None:
    """Select a playable audio URL from yt-dlp extraction data."""
    url = info.get("url")
    if url:
        return url

    formats = info.get("formats") or []
    audio_formats = [
        fmt
        for fmt in formats
        if fmt.get("url") and fmt.get("acodec") and fmt.get("acodec") != "none"
    ]
    if not audio_formats:
        return None

    def score(fmt: dict) -> tuple[int, int, int]:
        acodec = str(fmt.get("acodec") or "")
        ext = str(fmt.get("ext") or "")
        abr = int(fmt.get("abr") or fmt.get("tbr") or 0)
        codec_score = 2 if acodec.startswith("opus") else 1 if ext == "m4a" else 0
        return (codec_score, abr, int(fmt.get("filesize") or fmt.get("filesize_approx") or 0))

    return max(audio_formats, key=score).get("url")


def _extract_info(url: str, *, playlist: bool = False) -> dict | None:
    """Extract info from URL (blocking operation)."""
    opts = _get_options(playlist)
    with yt_dlp.YoutubeDL(opts) as ydl:
        try:
            return ydl.extract_info(url, download=False)
        except DownloadError as e:
            error_msg = str(e)
            if "JavaScript" in error_msg or "nsig" in error_msg:
                logger.error(
                    "yt-dlp requires Deno or Node.js for YouTube signature extraction."
                )
            else:
                logger.warning("yt-dlp download error for %s: %s", url, e)
            return None
        except ExtractorError as e:
            logger.warning("yt-dlp extractor error for %s: %s", url, e)
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

    url = _select_audio_url(info)
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
