"""Discord Music Bot with slash commands, autoplay, and Opus streaming."""

import asyncio
import logging
import math
import os
import shutil

import discord
import yt_dlp.version
from discord import app_commands
from discord.ext import tasks
from dotenv import load_dotenv

from health import (
    HEARTBEAT_INTERVAL,
    YTDLP_MAX_AGE_DAYS,
    clear_heartbeat,
    write_heartbeat,
    ytdlp_age_days,
)
from music_player import player_manager

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
SYNC_COMMANDS = os.getenv("SYNC_COMMANDS", "1") != "0"
logger = logging.getLogger(__name__)


class MusicBot(discord.Client):
    """Discord bot client with command tree."""

    def __init__(self):
        intents = discord.Intents.default()
        intents.voice_states = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        """Register commands and sync on startup."""
        from commands import setup_commands
        from audio_cache import audio_cache

        await asyncio.to_thread(audio_cache.clear_stale_files)
        setup_commands(self)
        self.tree.on_error = self.on_command_error
        clear_heartbeat()
        self.heartbeat.start()
        if SYNC_COMMANDS:
            try:
                await self.tree.sync()
                logger.info("Synced %d commands", len(self.tree.get_commands()))
            except discord.HTTPException as e:
                logger.warning("Could not sync slash commands: %s", e)
        else:
            logger.info("Skipped slash command sync (SYNC_COMMANDS=0)")

    @tasks.loop(seconds=HEARTBEAT_INTERVAL)
    async def heartbeat(self) -> None:
        """Refresh the file the container health check reads while Discord is reachable."""
        if self.is_ready() and not self.is_closed() and math.isfinite(self.latency):
            await asyncio.to_thread(write_heartbeat)

    async def on_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        from commands.helpers import respond

        logger.error("Music command failed", exc_info=error)
        message = "That command could not complete. Try again, or use /nowplaying to check the player."
        if isinstance(getattr(error, "original", error), discord.Forbidden):
            message = "I need permission to send messages and embeds here, and to connect and speak in your voice channel."
        try:
            await respond(interaction, message)
        except discord.HTTPException:
            pass

    async def close(self) -> None:
        from audio_cache import audio_cache
        from commands.player_view import panels

        self.heartbeat.cancel()
        for guild_id in list(player_manager.players):
            await player_manager.disconnect(guild_id)
        await panels.close()
        audio_cache.cleanup_all()
        await super().close()


client = MusicBot()


# ============== Events ==============


@client.event
async def on_ready():
    """Called when bot is ready."""
    logger.info("Logged in as %s (ID: %s)", client.user, client.user.id)


@client.event
async def on_voice_state_update(
    member: discord.Member,
    before: discord.VoiceState,
    after: discord.VoiceState,
):
    """Handle the bot being disconnected, and everyone leaving the bot's channel."""
    guild_id = member.guild.id
    player = player_manager.players.get(guild_id)
    if not player or not player.voice_client:
        return
    # Check if the bot was disconnected
    if member.id == client.user.id and after.channel is None and before.channel:
        if player.voice_client.channel.id == before.channel.id:
            await player_manager.cleanup_external_disconnect(guild_id)
        return
    # Someone joined, left, or moved: start or stop the empty-channel countdown.
    player_manager.check_listeners(guild_id)


# ============== Dependency Check ==============


def check_dependencies() -> list[str]:
    """Check for required external dependencies."""
    missing = []
    if not shutil.which("ffmpeg"):
        missing.append("FFmpeg - Required for audio playback")
    if not any(shutil.which(runtime) for runtime in ("deno", "node", "bun")):
        missing.append(
            "Deno, Node.js, or Bun - Required by yt-dlp for YouTube JavaScript extraction"
        )
    return missing


# ============== Entry Point ==============


def configure_logging() -> None:
    """Send every module's logs, including yt-dlp's, to stderr at LOG_LEVEL (default INFO)."""
    level = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)
    logging.basicConfig(
        level=level if isinstance(level, int) else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def main():
    """Run the bot."""
    configure_logging()
    if not TOKEN:
        logger.error(
            "DISCORD_TOKEN not found in environment variables. "
            "Create a .env file with: DISCORD_TOKEN=your_token_here"
        )
        return

    # Check external dependencies
    for dep in check_dependencies():
        logger.warning("Missing external dependency: %s", dep)

    age = ytdlp_age_days(yt_dlp.version.__version__)
    if age is not None and age > YTDLP_MAX_AGE_DAYS:
        logger.warning(
            "yt-dlp %s is %d days old and YouTube changes often; "
            "update it (uv lock --upgrade-package yt-dlp) and rebuild if playback fails.",
            yt_dlp.version.__version__,
            age,
        )

    # Logging is configured above, so discord.py must not install a second handler.
    client.run(TOKEN, log_handler=None)


if __name__ == "__main__":
    main()
