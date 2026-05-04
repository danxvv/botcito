"""Discord Music Bot with slash commands, autoplay, and Opus streaming."""

import os
import shutil

import discord
from discord import app_commands
from dotenv import load_dotenv

from music_player import player_manager

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")


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

        setup_commands(self)
        await self.tree.sync()
        print(f"Synced {len(self.tree.get_commands())} commands")


client = MusicBot()


# ============== Events ==============


@client.event
async def on_ready():
    """Called when bot is ready."""
    print(f"Logged in as {client.user} (ID: {client.user.id})")
    print("------")


@client.event
async def on_voice_state_update(
    member: discord.Member,
    before: discord.VoiceState,
    after: discord.VoiceState,
):
    """Handle voice state changes (e.g., bot alone in channel)."""
    # Check if the bot was disconnected
    if member.id == client.user.id and after.channel is None and before.channel:
        guild_id = before.channel.guild.id
        player = player_manager.get_player(guild_id)

        # Save recording if active before cleanup
        if player.recording_session and player.audio_sink:
            await player_manager.stop_recording(guild_id)

        # Acquire lock to avoid race conditions with play_next()
        async with player._lock:
            player.voice_client = None
            player.current_song = None
            player.queue.clear()
            player.autoplay_queue.clear()
            player.recent_songs.clear()
            player.ytmusic.clear_history()


# ============== Dependency Check ==============


def check_dependencies() -> list[str]:
    """Check for required external dependencies."""
    missing = []
    if not shutil.which("ffmpeg"):
        missing.append("FFmpeg - Required for audio playback")
    if not shutil.which("deno") and not shutil.which("node"):
        missing.append("Deno or Node.js - Required by yt-dlp for YouTube (install: https://deno.land)")
    return missing


# ============== Entry Point ==============


def main():
    """Run the bot."""
    if not TOKEN:
        print("Error: DISCORD_TOKEN not found in environment variables.")
        print("Create a .env file with: DISCORD_TOKEN=your_token_here")
        return

    # Check external dependencies
    missing_deps = check_dependencies()
    if missing_deps:
        print("Warning: Missing external dependencies:")
        for dep in missing_deps:
            print(f"  - {dep}")
        print()

    client.run(TOKEN)


if __name__ == "__main__":
    main()
