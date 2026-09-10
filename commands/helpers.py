"""Shared helper functions used across command modules."""

import asyncio
import logging

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
    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        await respond(interaction, "Use music commands in a server's voice channel.")
        return False
    if not interaction.user.voice or not interaction.user.voice.channel:
        await respond(interaction, "Join a voice channel, then use /play to choose a song.")
        return False
    return True


async def ensure_same_voice(
    interaction: discord.Interaction, voice_client: discord.VoiceClient | None
) -> bool:
    """Ensure a user controls playback from the bot's voice channel."""
    if not await ensure_voice(interaction):
        return False

    if voice_client and voice_client.channel.id != interaction.user.voice.channel.id:
        await respond(interaction, f"Music is in <#{voice_client.channel.id}>. Join that channel first.")
        return False
    return True


async def respond(interaction: discord.Interaction, message: str) -> None:
    """Send a private response before or after an interaction was acknowledged."""
    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())
    else:
        await interaction.response.send_message(message, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())


class MusicView(discord.ui.View):
    """Make failed controls and expired temporary menus understandable."""

    def __init__(self, *, timeout: float | None = 180) -> None:
        super().__init__(timeout=timeout)
        self.message: discord.Message | None = None

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item) -> None:
        logging.getLogger(__name__).error("Music control failed", exc_info=error)
        await respond(interaction, "That control could not complete. Try again, or use /nowplaying to open the player.")

    async def on_timeout(self) -> None:
        if self.message:
            try:
                await self.message.edit(view=None)
            except discord.HTTPException:
                pass


def _log_music_event(interaction: discord.Interaction, song, source_type: str, action: str):
    """Log a music audit event, extracting guild/user info from the interaction."""
    guild_name = interaction.guild.name if interaction.guild else "DM"
    asyncio.create_task(
        asyncio.to_thread(
            AuditLogger.log_music,
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
    )
