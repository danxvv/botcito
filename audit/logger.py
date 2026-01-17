"""Audit logging for Discord bot commands."""

import functools
import json
import threading
from typing import Any, Callable

import discord

from .database import get_connection, init_db


class AuditLogger:
    """Logger for audit events."""

    _initialized = False
    _lock = threading.Lock()

    @classmethod
    def _ensure_db(cls) -> None:
        """Ensure database is initialized (thread-safe)."""
        if not cls._initialized:
            with cls._lock:
                if not cls._initialized:  # Double-check pattern
                    init_db()
                    cls._initialized = True

    @classmethod
    def log_command(
        cls,
        guild_id: int,
        guild_name: str,
        user_id: int,
        user_name: str,
        command_name: str,
        args: dict[str, Any] | None = None,
        success: bool = True,
        error_message: str | None = None,
    ) -> None:
        """Log a command execution."""
        cls._ensure_db()

        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO command_logs
                (guild_id, guild_name, user_id, user_name, command_name, command_args, success, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    guild_id,
                    guild_name,
                    user_id,
                    user_name,
                    command_name,
                    json.dumps(args) if args else None,
                    success,
                    error_message,
                ),
            )
            conn.commit()

    @classmethod
    def log_music(
        cls,
        guild_id: int,
        guild_name: str,
        user_id: int,
        user_name: str,
        video_id: str,
        title: str,
        duration: int | None,
        source: str,
        action: str,
    ) -> None:
        """Log a music playback event."""
        cls._ensure_db()

        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO music_logs
                (guild_id, guild_name, user_id, user_name, video_id, title, duration, source, action)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    guild_id,
                    guild_name,
                    user_id,
                    user_name,
                    video_id,
                    title,
                    duration,
                    source,
                    action,
                ),
            )
            conn.commit()


def log_command(func: Callable) -> Callable:
    """Decorator to automatically log command usage."""

    @functools.wraps(func)
    async def wrapper(interaction: discord.Interaction, *args, **kwargs) -> Any:
        command_name = func.__name__
        guild_id = interaction.guild_id or 0
        guild_name = interaction.guild.name if interaction.guild else "DM"
        user_id = interaction.user.id
        user_name = str(interaction.user)

        # Convert args to loggable format (exclude large objects)
        loggable_kwargs = {}
        for key, value in kwargs.items():
            if isinstance(value, (str, int, float, bool, type(None))):
                loggable_kwargs[key] = value
            elif hasattr(value, "value"):  # Handle Choice objects
                loggable_kwargs[key] = value.value
            else:
                loggable_kwargs[key] = str(value)[:100]

        try:
            result = await func(interaction, *args, **kwargs)
            AuditLogger.log_command(
                guild_id,
                guild_name,
                user_id,
                user_name,
                command_name,
                loggable_kwargs,
                success=True,
            )
            return result
        except Exception as e:
            AuditLogger.log_command(
                guild_id,
                guild_name,
                user_id,
                user_name,
                command_name,
                loggable_kwargs,
                success=False,
                error_message=str(e)[:500],
            )
            raise

    return wrapper
