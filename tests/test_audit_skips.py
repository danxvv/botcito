"""Check the skip counts that steer autoplay away from songs people skip."""

import sqlite3

import pytest

from audit import database
from audit.logger import AuditLogger


@pytest.fixture
def audit_db(tmp_path, monkeypatch):
    path = tmp_path / "audit.db"
    monkeypatch.setattr(database, "get_audit_db_path", lambda: path)
    monkeypatch.setattr(AuditLogger, "_initialized", False)
    return path


def log(guild_id, video_id, action):
    AuditLogger.log_music(guild_id, "Guild", 1, "User", video_id, "Title", 100, "search", action)


def test_missing_tables_mean_no_skips(audit_db):
    assert database.get_skip_counts(1) == {}


def test_counts_only_skips_in_this_server(audit_db):
    for guild_id, video_id, action in [
        (1, "aaa", "skip"),
        (1, "aaa", "skip"),
        (1, "bbb", "skip"),
        (1, "aaa", "play"),
        (1, "ccc", "stop"),
        (2, "aaa", "skip"),
    ]:
        log(guild_id, video_id, action)
    assert database.get_skip_counts(1) == {"aaa": 2, "bbb": 1}
    assert database.get_skip_counts(2) == {"aaa": 1}
    assert database.get_skip_counts(3) == {}


def test_old_skips_are_forgotten(audit_db):
    log(1, "old", "skip")
    log(1, "new", "skip")
    with database.get_connection() as conn:
        conn.execute("UPDATE music_logs SET timestamp = datetime('now', '-40 days') WHERE video_id = 'old'")
        conn.commit()
    assert database.get_skip_counts(1, hours=24 * 30) == {"new": 1}
    assert database.get_skip_counts(1, hours=24 * 60) == {"old": 1, "new": 1}


def test_other_database_errors_are_not_hidden(audit_db, monkeypatch):
    def broken():
        raise sqlite3.DatabaseError("disk image is malformed")

    monkeypatch.setattr(database, "get_connection", broken)
    with pytest.raises(sqlite3.DatabaseError):
        database.get_skip_counts(1)
