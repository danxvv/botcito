"""Shared yt-dlp configuration helpers."""

import os
from pathlib import Path

_FALLBACK_COOKIES_FILE = Path(__file__).parent / "cookies.txt"


def get_cookies_file() -> Path:
    """Return YT_DLP_COOKIES_FILE or fall back to ./cookies.txt, with ~ expansion."""
    return Path(
        os.getenv("YT_DLP_COOKIES_FILE", str(_FALLBACK_COOKIES_FILE))
    ).expanduser()
