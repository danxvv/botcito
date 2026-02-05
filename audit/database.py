"""SQLite database for audit logging."""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Generator

from .config import get_audit_db_path

SCHEMA = """
-- Command usage logs
CREATE TABLE IF NOT EXISTS command_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    guild_id INTEGER NOT NULL,
    guild_name TEXT,
    user_id INTEGER NOT NULL,
    user_name TEXT,
    command_name TEXT NOT NULL,
    command_args TEXT,
    success BOOLEAN DEFAULT 1,
    error_message TEXT
);

-- Music playback history
CREATE TABLE IF NOT EXISTS music_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    guild_id INTEGER NOT NULL,
    guild_name TEXT,
    user_id INTEGER NOT NULL,
    user_name TEXT,
    video_id TEXT NOT NULL,
    title TEXT NOT NULL,
    duration INTEGER,
    source TEXT,
    action TEXT
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_command_logs_guild ON command_logs(guild_id);
CREATE INDEX IF NOT EXISTS idx_command_logs_timestamp ON command_logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_command_logs_user ON command_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_music_logs_guild ON music_logs(guild_id);
CREATE INDEX IF NOT EXISTS idx_music_logs_timestamp ON music_logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_music_logs_user ON music_logs(user_id);
"""


@contextmanager
def get_connection() -> Generator[sqlite3.Connection, None, None]:
    """Get a database connection as a context manager."""
    conn = sqlite3.connect(get_audit_db_path())
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    """Initialize the database with the schema."""
    with get_connection() as conn:
        conn.executescript(SCHEMA)
        conn.commit()


# ============== Command Logs Queries ==============


def get_command_stats_by_guild(guild_id: int | None = None, hours: int = 24) -> list[dict]:
    """Get command usage statistics, optionally filtered by guild."""
    since = datetime.now() - timedelta(hours=hours)

    with get_connection() as conn:
        if guild_id:
            rows = conn.execute("""
                SELECT command_name, COUNT(*) as count,
                       SUM(CASE WHEN success THEN 1 ELSE 0 END) as success_count,
                       MAX(timestamp) as last_used
                FROM command_logs
                WHERE guild_id = ? AND timestamp > ?
                GROUP BY command_name
                ORDER BY count DESC
            """, (guild_id, since.isoformat())).fetchall()
        else:
            rows = conn.execute("""
                SELECT command_name, COUNT(*) as count,
                       SUM(CASE WHEN success THEN 1 ELSE 0 END) as success_count,
                       MAX(timestamp) as last_used
                FROM command_logs
                WHERE timestamp > ?
                GROUP BY command_name
                ORDER BY count DESC
            """, (since.isoformat(),)).fetchall()

        return [dict(row) for row in rows]


def get_command_stats_by_user(guild_id: int | None = None, hours: int = 24) -> list[dict]:
    """Get command usage by user."""
    since = datetime.now() - timedelta(hours=hours)

    with get_connection() as conn:
        if guild_id:
            rows = conn.execute("""
                SELECT user_id, user_name, COUNT(*) as command_count,
                       MAX(timestamp) as last_active
                FROM command_logs
                WHERE guild_id = ? AND timestamp > ?
                GROUP BY user_id
                ORDER BY command_count DESC
            """, (guild_id, since.isoformat())).fetchall()
        else:
            rows = conn.execute("""
                SELECT user_id, user_name, COUNT(*) as command_count,
                       MAX(timestamp) as last_active
                FROM command_logs
                WHERE timestamp > ?
                GROUP BY user_id
                ORDER BY command_count DESC
            """, (since.isoformat(),)).fetchall()

        return [dict(row) for row in rows]


def get_recent_commands(guild_id: int | None = None, limit: int = 100) -> list[dict]:
    """Get recent command logs."""
    with get_connection() as conn:
        if guild_id:
            rows = conn.execute("""
                SELECT timestamp, guild_name, user_name, command_name, command_args, success
                FROM command_logs
                WHERE guild_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (guild_id, limit)).fetchall()
        else:
            rows = conn.execute("""
                SELECT timestamp, guild_name, user_name, command_name, command_args, success
                FROM command_logs
                ORDER BY timestamp DESC
                LIMIT ?
            """, (limit,)).fetchall()

        return [dict(row) for row in rows]


def get_guild_command_count(guild_id: int, hours: int = 24) -> int:
    """Get command count for a specific guild in the last N hours."""
    since = datetime.now() - timedelta(hours=hours)

    with get_connection() as conn:
        row = conn.execute("""
            SELECT COUNT(*) as count
            FROM command_logs
            WHERE guild_id = ? AND timestamp > ?
        """, (guild_id, since.isoformat())).fetchone()
        return row["count"] if row else 0


# ============== Music Logs Queries ==============


def get_music_history(
    guild_id: int | None = None,
    search: str | None = None,
    limit: int = 100
) -> list[dict]:
    """Get music playback history."""
    with get_connection() as conn:
        query = """
            SELECT timestamp, guild_name, user_name, title, duration, source, action, video_id
            FROM music_logs
            WHERE 1=1
        """
        params = []

        if guild_id:
            query += " AND guild_id = ?"
            params.append(guild_id)

        if search:
            # Escape LIKE special characters
            search_escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            query += " AND (title LIKE ? ESCAPE '\\' OR user_name LIKE ? ESCAPE '\\')"
            search_term = f"%{search_escaped}%"
            params.extend([search_term, search_term])

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]


def get_guild_song_count(guild_id: int, hours: int = 24) -> int:
    """Get song count for a specific guild in the last N hours."""
    since = datetime.now() - timedelta(hours=hours)

    with get_connection() as conn:
        row = conn.execute("""
            SELECT COUNT(*) as count
            FROM music_logs
            WHERE guild_id = ? AND timestamp > ? AND action = 'play'
        """, (guild_id, since.isoformat())).fetchone()
        return row["count"] if row else 0


def get_user_song_count(user_id: int, guild_id: int | None = None, hours: int = 24) -> int:
    """Get song count for a specific user."""
    since = datetime.now() - timedelta(hours=hours)

    with get_connection() as conn:
        if guild_id:
            row = conn.execute("""
                SELECT COUNT(*) as count
                FROM music_logs
                WHERE user_id = ? AND guild_id = ? AND timestamp > ? AND action = 'play'
            """, (user_id, guild_id, since.isoformat())).fetchone()
        else:
            row = conn.execute("""
                SELECT COUNT(*) as count
                FROM music_logs
                WHERE user_id = ? AND timestamp > ? AND action = 'play'
            """, (user_id, since.isoformat())).fetchone()
        return row["count"] if row else 0


def get_total_stats() -> dict:
    """Get overall statistics."""
    with get_connection() as conn:
        cmd_count = conn.execute("SELECT COUNT(*) as c FROM command_logs").fetchone()["c"]
        music_count = conn.execute("SELECT COUNT(*) as c FROM music_logs").fetchone()["c"]
        guild_count = conn.execute(
            "SELECT COUNT(DISTINCT guild_id) as c FROM command_logs"
        ).fetchone()["c"]
        user_count = conn.execute(
            "SELECT COUNT(DISTINCT user_id) as c FROM command_logs"
        ).fetchone()["c"]

        return {
            "total_commands": cmd_count,
            "total_songs": music_count,
            "unique_guilds": guild_count,
            "unique_users": user_count,
        }


def get_user_music_stats(user_id: int, guild_id: int | None, hours: int | None) -> dict:
    """Get music listening statistics for a user.

    Returns: {songs_played, total_duration, top_songs}
    """
    with get_connection() as conn:
        params = [user_id]
        time_filter = ""
        guild_filter = ""

        if hours:
            since = datetime.now() - timedelta(hours=hours)
            time_filter = " AND timestamp > ?"
            params.append(since.isoformat())

        if guild_id:
            guild_filter = " AND guild_id = ?"
            params.append(guild_id)

        # Get songs played count and total duration
        stats_query = f"""
            SELECT COUNT(*) as songs_played, COALESCE(SUM(duration), 0) as total_duration
            FROM music_logs
            WHERE user_id = ? AND action = 'play'{time_filter}{guild_filter}
        """
        stats_row = conn.execute(stats_query, params).fetchone()

        # Get top songs
        top_params = [user_id]
        if hours:
            top_params.append(since.isoformat())
        if guild_id:
            top_params.append(guild_id)

        top_query = f"""
            SELECT video_id, title, COUNT(*) as play_count
            FROM music_logs
            WHERE user_id = ? AND action = 'play'{time_filter}{guild_filter}
            GROUP BY video_id
            ORDER BY play_count DESC
            LIMIT 5
        """
        top_rows = conn.execute(top_query, top_params).fetchall()

        return {
            "songs_played": stats_row["songs_played"],
            "total_duration": stats_row["total_duration"],
            "top_songs": [dict(row) for row in top_rows],
        }


def get_guild_music_leaderboard(guild_id: int, hours: int | None, limit: int = 10) -> list[dict]:
    """Get music leaderboard for a guild.

    Returns: [{user_id, user_name, songs_played, total_duration}, ...]
    """
    with get_connection() as conn:
        params = [guild_id]
        time_filter = ""

        if hours:
            since = datetime.now() - timedelta(hours=hours)
            time_filter = " AND timestamp > ?"
            params.append(since.isoformat())

        params.append(limit)

        query = f"""
            SELECT user_id, user_name, COUNT(*) as songs_played,
                   COALESCE(SUM(duration), 0) as total_duration
            FROM music_logs
            WHERE guild_id = ? AND action = 'play'{time_filter}
            GROUP BY user_id
            ORDER BY songs_played DESC
            LIMIT ?
        """
        rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]
