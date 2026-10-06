"""Container health check and runtime environment checks."""

import sys
import time
from datetime import date
from pathlib import Path

HEARTBEAT_PATH = Path(__file__).parent / "data" / "heartbeat"
# The bot refreshes the file every HEARTBEAT_INTERVAL seconds while connected to Discord.
HEARTBEAT_INTERVAL = 30
MAX_HEARTBEAT_AGE = 3 * HEARTBEAT_INTERVAL
# YouTube changes often enough that a yt-dlp release older than this is likely to break playback.
YTDLP_MAX_AGE_DAYS = 45


def write_heartbeat(path: Path = HEARTBEAT_PATH) -> None:
    """Record that the bot is connected and responsive."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(time.time()))


def clear_heartbeat(path: Path = HEARTBEAT_PATH) -> None:
    """Forget a heartbeat left by an earlier run so it cannot hide a failed start."""
    path.unlink(missing_ok=True)


def is_healthy(path: Path = HEARTBEAT_PATH, now: float | None = None) -> bool:
    """Check that the heartbeat was refreshed recently."""
    try:
        beat = float(path.read_text())
    except (OSError, ValueError):
        return False
    return (now if now is not None else time.time()) - beat < MAX_HEARTBEAT_AGE


def ytdlp_age_days(version: str, today: date | None = None) -> int | None:
    """Days since a yt-dlp release, read from its YYYY.MM.DD[.suffix] version."""
    try:
        year, month, day = (int(part) for part in version.split(".")[:3])
        released = date(year, month, day)
    except ValueError:
        return None
    return ((today or date.today()) - released).days


if __name__ == "__main__":
    sys.exit(0 if is_healthy() else 1)
