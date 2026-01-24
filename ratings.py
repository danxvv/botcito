"""Song rating storage and queries for influencing autoplay."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

# Database path
DATA_DIR = Path(__file__).parent / "data"
RATINGS_DB_PATH = DATA_DIR / "ratings.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS song_ratings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    video_id TEXT NOT NULL,
    rating INTEGER NOT NULL,  -- +1 for like, -1 for dislike
    rated_by INTEGER NOT NULL,
    title TEXT,
    artist TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(guild_id, video_id, rated_by)
);

CREATE INDEX IF NOT EXISTS idx_ratings_guild ON song_ratings(guild_id);
CREATE INDEX IF NOT EXISTS idx_ratings_video ON song_ratings(video_id);
CREATE INDEX IF NOT EXISTS idx_ratings_guild_video ON song_ratings(guild_id, video_id);
"""


def _ensure_data_dir() -> None:
    """Ensure data directory exists."""
    DATA_DIR.mkdir(exist_ok=True)


@contextmanager
def get_connection() -> Generator[sqlite3.Connection, None, None]:
    """Get a database connection as a context manager."""
    _ensure_data_dir()
    conn = sqlite3.connect(RATINGS_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    """Initialize the ratings database with the schema."""
    with get_connection() as conn:
        conn.executescript(SCHEMA)
        conn.commit()


# Initialize on import
init_db()


def rate_song(
    guild_id: int,
    video_id: str,
    user_id: int,
    rating: int,
    title: str | None = None,
    artist: str | None = None,
) -> bool:
    """Rate a song. Returns True if rating was added/updated.

    Args:
        guild_id: Discord guild ID
        video_id: YouTube video ID
        user_id: Discord user ID
        rating: +1 for like, -1 for dislike
        title: Song title (optional)
        artist: Song artist (optional)
    """
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO song_ratings (guild_id, video_id, rating, rated_by, title, artist)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(guild_id, video_id, rated_by) DO UPDATE SET
                rating = excluded.rating,
                title = COALESCE(excluded.title, title),
                artist = COALESCE(excluded.artist, artist),
                created_at = CURRENT_TIMESTAMP
            """,
            (guild_id, video_id, rating, user_id, title, artist),
        )
        conn.commit()
        return True


def remove_rating(guild_id: int, video_id: str, user_id: int) -> bool:
    """Remove a user's rating for a song. Returns True if a rating was removed."""
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM song_ratings WHERE guild_id = ? AND video_id = ? AND rated_by = ?",
            (guild_id, video_id, user_id),
        )
        conn.commit()
        return cursor.rowcount > 0


def get_song_rating_score(guild_id: int, video_id: str) -> int:
    """Get the total rating score for a song (sum of all ratings)."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(rating), 0) as score FROM song_ratings WHERE guild_id = ? AND video_id = ?",
            (guild_id, video_id),
        ).fetchone()
        return row["score"] if row else 0


def get_user_rating(guild_id: int, video_id: str, user_id: int) -> int | None:
    """Get a user's rating for a song. Returns +1, -1, or None if not rated."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT rating FROM song_ratings WHERE guild_id = ? AND video_id = ? AND rated_by = ?",
            (guild_id, video_id, user_id),
        ).fetchone()
        return row["rating"] if row else None


def get_guild_ratings(guild_id: int) -> dict[str, int]:
    """Get all song ratings for a guild.

    Returns: {video_id: total_score, ...}
    """
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT video_id, SUM(rating) as score
            FROM song_ratings
            WHERE guild_id = ?
            GROUP BY video_id
            """,
            (guild_id,),
        ).fetchall()
        return {row["video_id"]: row["score"] for row in rows}


def get_rating_counts(guild_id: int, video_id: str) -> tuple[int, int]:
    """Get like and dislike counts for a song.

    Returns: (likes, dislikes)
    """
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT
                SUM(CASE WHEN rating > 0 THEN 1 ELSE 0 END) as likes,
                SUM(CASE WHEN rating < 0 THEN 1 ELSE 0 END) as dislikes
            FROM song_ratings
            WHERE guild_id = ? AND video_id = ?
            """,
            (guild_id, video_id),
        ).fetchone()
        return (row["likes"] or 0, row["dislikes"] or 0)
