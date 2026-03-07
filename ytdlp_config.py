"""Shared yt-dlp configuration helpers."""

import os
from pathlib import Path

_FALLBACK_COOKIES_FILE = Path(__file__).parent / "cookies.txt"


def get_cookies_file() -> Path:
    """Return path from YT_DLP_COOKIES_FILE (with ~ expansion) or ./cookies.txt."""
    configured_path = os.getenv("YT_DLP_COOKIES_FILE")
    if configured_path:
        return Path(configured_path).expanduser()
    return _FALLBACK_COOKIES_FILE
