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
        self._game_agent = None
        self._voice_conversation = None
        self._music_discovery_agent = None

    async def setup_hook(self):
        """Register commands and sync on startup."""
        from commands import setup_commands

        setup_commands(self)
        await self.tree.sync()
        print(f"Synced {len(self.tree.get_commands())} commands")

    def get_game_agent(self):
        """Get or create the game agent singleton."""
        if self._game_agent is None:
            from game_agent import GameAgent

            self._game_agent = GameAgent()
        return self._game_agent

    def get_voice_conversation(self):
        """Get or create the voice conversation manager singleton."""
        if self._voice_conversation is None:
            from voice_agent import (
                ChatterboxTTSProvider,
                Qwen3TTSProvider,
                VoiceConversation,
                get_qwen_tts_settings_path,
                get_tts_config,
            )

            agent = self.get_game_agent()
            provider_name = os.getenv("TTS_PROVIDER", "qwen").strip().lower()

            if provider_name == "qwen":
                tts_provider = Qwen3TTSProvider(
                    settings_path=get_qwen_tts_settings_path()
                )
            elif provider_name == "chatterbox":
                mcp_url, language = get_tts_config()
                tts_provider = ChatterboxTTSProvider(
                    mcp_url=mcp_url,
                    default_language=language,
                )
            else:
                raise ValueError(
                    "Invalid TTS_PROVIDER value. Use `qwen` or `chatterbox`."
                )

            self._voice_conversation = VoiceConversation(
                game_agent=agent,
                player_manager=player_manager,
                tts_provider=tts_provider,
            )
        return self._voice_conversation

    def get_music_discovery_agent(self):
        """Get or create the music discovery agent singleton."""
        if self._music_discovery_agent is None:
            from music_agent import MusicDiscoveryAgent

            self._music_discovery_agent = MusicDiscoveryAgent()
        return self._music_discovery_agent


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

        # Stop voice conversation if active
        if client._voice_conversation and client._voice_conversation.is_active(guild_id):
            client._voice_conversation.stop(guild_id)

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
