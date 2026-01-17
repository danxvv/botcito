"""SQLite settings management for the bot."""

import sqlite3
from pathlib import Path

# Ensure data directory exists
DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

DB_PATH = DATA_DIR / "settings.db"

# Available LLM models
AVAILABLE_MODELS = [
    "openai/gpt-5.2",
    "x-ai/grok-4.1-fast",
    "google/gemini-3-pro-preview",
    "anthropic/claude-sonnet-4.5",
    "anthropic/claude-haiku-4.5",
    "google/gemini-3-flash-preview"
]

DEFAULT_MODEL = "google/gemini-3-flash-preview"


def _get_connection() -> sqlite3.Connection:
    """Get a database connection."""
    return sqlite3.connect(DB_PATH)


def init_db() -> None:
    """Initialize the settings database table."""
    with _get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        # Set default model if not exists
        conn.execute("""
            INSERT OR IGNORE INTO settings (key, value) VALUES ('llm_model', ?)
        """, (DEFAULT_MODEL,))
        conn.commit()


def get_setting(key: str, default: str | None = None) -> str | None:
    """Get a setting value by key."""
    with _get_connection() as conn:
        cursor = conn.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row[0] if row else default


def set_setting(key: str, value: str) -> None:
    """Set a setting value."""
    with _get_connection() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)
        """, (key, value))
        conn.commit()


def get_llm_model() -> str:
    """Get the current LLM model."""
    return get_setting("llm_model", DEFAULT_MODEL)


def set_llm_model(model: str) -> bool:
    """
    Set the LLM model.

    Returns True if successful, False if model is not in the allowed list.
    """
    if model not in AVAILABLE_MODELS:
        return False
    set_setting("llm_model", model)
    return True


# Initialize database on module import
init_db()
