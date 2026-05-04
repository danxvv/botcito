"""Shared helper functions used across command modules."""

import discord
from discord import app_commands

from audit.logger import AuditLogger


def period_to_hours(period: app_commands.Choice[str] | None) -> int | None:
    """Convert period choice to hours. Returns None for 'all time'."""
    if period is None:
        return None
    period_map = {"24h": 24, "7d": 168, "30d": 720}
    return period_map.get(period.value)


def format_duration(seconds: int) -> str:
    """Format seconds as MM:SS or HH:MM:SS."""
    if seconds <= 0:
        return "Live"
    minutes, secs = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def render_progress_bar(elapsed: int, total: int, width: int = 20) -> str:
    """Render a progress bar with timestamps."""
    if total <= 0:
        return f"[{'=' * width}] Live"

    progress = min(elapsed / total, 1.0)
    filled = int(width * progress)
    bar = "=" * filled + ">" + " " * (width - filled - 1) if filled < width else "=" * width
    return f"[{bar}] {format_duration(elapsed)} / {format_duration(total)}"


async def ensure_voice(interaction: discord.Interaction) -> bool:
    """Ensure user is in a voice channel and bot can connect."""
    if not interaction.user.voice:
        await interaction.response.send_message(
            "You need to be in a voice channel!", ephemeral=True
        )
        return False
    return True


def _log_music_event(interaction: discord.Interaction, song, source_type: str, action: str):
    """Log a music audit event, extracting guild/user info from the interaction."""
    guild_name = interaction.guild.name if interaction.guild else "DM"
    AuditLogger.log_music(
        interaction.guild_id,
        guild_name,
        interaction.user.id,
        str(interaction.user),
        song.video_id,
        song.title,
        song.duration,
        source_type,
        action,
    )
