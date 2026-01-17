"""Discord Music Bot with slash commands, autoplay, and Opus streaming."""

import asyncio
import os
import shutil
import time

import discord
from discord import app_commands
from dotenv import load_dotenv

from autoplay import YouTubeMusicHandler
from music_player import player_manager
from youtube import extract_playlist, extract_song_info, is_playlist_url, search_youtube
from audit.logger import log_command, AuditLogger

# Game agent (lazy loaded to avoid startup errors if keys missing)
_game_agent = None


def get_game_agent():
    """Get or create the game agent singleton."""
    global _game_agent
    if _game_agent is None:
        from game_agent import GameAgent
        _game_agent = GameAgent()
    return _game_agent

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")

# YouTube Music handler for autocomplete
ytmusic = YouTubeMusicHandler()


class MusicBot(discord.Client):
    """Discord bot client with command tree."""

    def __init__(self):
        intents = discord.Intents.default()
        intents.voice_states = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        """Sync commands on startup."""
        await self.tree.sync()
        print(f"Synced {len(self.tree.get_commands())} commands")


client = MusicBot()


# ============== Helper Functions ==============


def format_duration(seconds: int) -> str:
    """Format seconds as MM:SS or HH:MM:SS."""
    if seconds <= 0:
        return "Live"
    minutes, secs = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


async def ensure_voice(interaction: discord.Interaction) -> bool:
    """Ensure user is in a voice channel and bot can connect."""
    if not interaction.user.voice:
        await interaction.response.send_message(
            "You need to be in a voice channel!", ephemeral=True
        )
        return False
    return True


# ============== Slash Commands ==============


@client.tree.command(name="play", description="Play a song (search or URL)")
@app_commands.describe(query="Song name or YouTube URL")
@log_command
async def play(interaction: discord.Interaction, query: str):
    """Play a song from YouTube."""
    if not await ensure_voice(interaction):
        return

    await interaction.response.defer()

    guild_id = interaction.guild_id
    channel = interaction.user.voice.channel

    # Connect to voice channel
    await player_manager.connect(guild_id, channel)

    # Check if it's a playlist
    if is_playlist_url(query):
        entries = await extract_playlist(query)
        if not entries:
            await interaction.followup.send("Could not load playlist.")
            return

        added = 0
        for entry in entries:
            song = await extract_song_info(entry["video_id"])
            if song:
                await player_manager.add_to_queue(guild_id, song)
                added += 1

        await interaction.followup.send(f"Added **{added}** songs from playlist to queue!")

        # Start playing if not already
        if not player_manager.is_playing(guild_id):
            await player_manager.play_next(guild_id)
        return

    # Check if query is a video ID (11 chars, from autocomplete)
    if len(query) == 11 and not query.startswith("http"):
        song = await extract_song_info(query)
    elif query.startswith("http"):
        song = await extract_song_info(query)
    else:
        # Search YouTube
        song = await search_youtube(query)

    if not song:
        await interaction.followup.send("Could not find or play that song.")
        return

    # Add to queue
    position = await player_manager.add_to_queue(guild_id, song)

    # Log music event
    guild_name = interaction.guild.name if interaction.guild else "DM"
    AuditLogger.log_music(
        guild_id,
        guild_name,
        interaction.user.id,
        str(interaction.user),
        song.video_id,
        song.title,
        song.duration,
        "search" if not query.startswith("http") else "url",
        "play",
    )

    # Start playing if not already
    if not player_manager.is_playing(guild_id):
        await player_manager.play_next(guild_id)
        await interaction.followup.send(
            f"Now playing: **{song.title}** [{format_duration(song.duration)}]"
        )
    else:
        await interaction.followup.send(
            f"Added to queue (#{position}): **{song.title}** [{format_duration(song.duration)}]"
        )


@play.autocomplete("query")
async def play_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    """Provide song suggestions as user types."""
    if len(current) < 2:
        return []

    # Don't autocomplete URLs
    if current.startswith("http"):
        return []

    results = ytmusic.search_songs(current, limit=10)
    choices = []
    for r in results:
        name = f"{r['title']} - {r['artist']}"
        if len(name) > 100:
            name = name[:97] + "..."
        choices.append(app_commands.Choice(name=name, value=r["videoId"]))

    return choices[:25]  # Discord limit


@client.tree.command(name="skip", description="Skip the current song")
@log_command
async def skip(interaction: discord.Interaction):
    """Skip the current song."""
    guild_id = interaction.guild_id
    current = player_manager.get_current_song(guild_id)

    if player_manager.skip(guild_id):
        if current:
            guild_name = interaction.guild.name if interaction.guild else "DM"
            AuditLogger.log_music(
                guild_id, guild_name, interaction.user.id, str(interaction.user),
                current.video_id, current.title, current.duration, "queue", "skip"
            )
        await interaction.response.send_message("Skipped!")
    else:
        await interaction.response.send_message("Nothing is playing.", ephemeral=True)


@client.tree.command(name="stop", description="Stop playback and clear queue")
@log_command
async def stop(interaction: discord.Interaction):
    """Stop playback and disconnect."""
    guild_id = interaction.guild_id
    current = player_manager.get_current_song(guild_id)

    if current:
        guild_name = interaction.guild.name if interaction.guild else "DM"
        AuditLogger.log_music(
            guild_id, guild_name, interaction.user.id, str(interaction.user),
            current.video_id, current.title, current.duration, "queue", "stop"
        )

    await player_manager.disconnect(guild_id)
    await interaction.response.send_message("Stopped and disconnected.")


@client.tree.command(name="pause", description="Pause the current song")
@log_command
async def pause(interaction: discord.Interaction):
    """Pause the current song."""
    guild_id = interaction.guild_id

    if player_manager.pause(guild_id):
        await interaction.response.send_message("Paused.")
    else:
        await interaction.response.send_message("Nothing is playing.", ephemeral=True)


@client.tree.command(name="resume", description="Resume playback")
@log_command
async def resume(interaction: discord.Interaction):
    """Resume paused playback."""
    guild_id = interaction.guild_id

    if player_manager.resume(guild_id):
        await interaction.response.send_message("Resumed.")
    else:
        await interaction.response.send_message("Nothing is paused.", ephemeral=True)


@client.tree.command(name="queue", description="Show the current queue")
@log_command
async def queue(interaction: discord.Interaction):
    """Show the current queue."""
    guild_id = interaction.guild_id

    current = player_manager.get_current_song(guild_id)
    songs = player_manager.get_queue(guild_id)
    autoplay_songs = player_manager.get_autoplay_queue(guild_id)
    player = player_manager.get_player(guild_id)

    if not current and not songs and not autoplay_songs:
        await interaction.response.send_message("Queue is empty.", ephemeral=True)
        return

    lines = []

    if current:
        lines.append(f"**Now Playing:** {current.title} [{format_duration(current.duration)}]")

    if songs:
        lines.append("\n**Up Next:**")
        for i, song in enumerate(songs[:10], 1):
            lines.append(f"{i}. {song.title} [{format_duration(song.duration)}]")

        if len(songs) > 10:
            lines.append(f"... and {len(songs) - 10} more")

    autoplay_status = "ON" if player.autoplay_enabled else "OFF"
    lines.append(f"\n*Autoplay: {autoplay_status}*")

    # Show autoplay queue if autoplay is enabled and has songs
    if player.autoplay_enabled and autoplay_songs:
        lines.append("\n**Autoplay Up Next:**")
        for i, song in enumerate(autoplay_songs[:5], 1):
            lines.append(f"  {i}. {song.title} [{format_duration(song.duration)}]")

    await interaction.response.send_message("\n".join(lines))


@client.tree.command(name="nowplaying", description="Show the currently playing song")
@log_command
async def nowplaying(interaction: discord.Interaction):
    """Show the currently playing song."""
    guild_id = interaction.guild_id
    song = player_manager.get_current_song(guild_id)

    if not song:
        await interaction.response.send_message("Nothing is playing.", ephemeral=True)
        return

    embed = discord.Embed(
        title="Now Playing",
        description=f"**{song.title}**",
        color=discord.Color.blurple(),
    )
    embed.add_field(name="Duration", value=format_duration(song.duration))
    embed.add_field(name="URL", value=f"[Link]({song.webpage_url})")

    if song.thumbnail:
        embed.set_thumbnail(url=song.thumbnail)

    await interaction.response.send_message(embed=embed)


@client.tree.command(name="autoplay", description="Toggle autoplay mode")
@log_command
async def autoplay(interaction: discord.Interaction):
    """Toggle autoplay mode on/off."""
    guild_id = interaction.guild_id
    enabled = player_manager.toggle_autoplay(guild_id)

    status = "enabled" if enabled else "disabled"
    await interaction.response.send_message(f"Autoplay **{status}**.")


@client.tree.command(name="clearhistory", description="Clear autoplay history to allow songs to repeat")
@log_command
async def clearhistory(interaction: discord.Interaction):
    """Clear played history so songs can be recommended again."""
    guild_id = interaction.guild_id
    player_manager.clear_history(guild_id)
    await interaction.response.send_message("Autoplay history cleared. Songs can now be recommended again.")


@client.tree.command(name="model", description="Change the AI model for /guide command")
@app_commands.describe(model="The LLM model to use")
@app_commands.choices(model=[
    app_commands.Choice(name="OpenAI GPT-5.2", value="openai/gpt-5.2"),
    app_commands.Choice(name="xAI Grok 4.1 Fast", value="x-ai/grok-4.1-fast"),
    app_commands.Choice(name="Google Gemini 3 Pro", value="google/gemini-3-pro-preview"),
    app_commands.Choice(name="Anthropic Claude Sonnet 4.5", value="anthropic/claude-sonnet-4.5"),
    app_commands.Choice(name="Anthropic Claude Haiku 4.5", value="anthropic/claude-haiku-4.5"),
    app_commands.Choice(name="Google Gemini 3 Flash", value="google/gemini-3-flash-preview"),
])
@log_command
async def model(interaction: discord.Interaction, model: app_commands.Choice[str]):
    """Change the LLM model used by the /guide command."""
    from settings import set_llm_model, get_llm_model

    if set_llm_model(model.value):
        await interaction.response.send_message(f"Model changed to **{model.name}**")
    else:
        current = get_llm_model()
        await interaction.response.send_message(
            f"Invalid model. Current model: **{current}**",
            ephemeral=True
        )


@client.tree.command(name="guide", description="Get help with video games using AI")
@app_commands.guild_only()
@app_commands.describe(question="Your gaming question (tips, strategies, builds, etc.)")
@log_command
async def guide(interaction: discord.Interaction, question: str):
    """Answer gaming questions using AI with web search."""
    await interaction.response.defer()

    guild_id = interaction.guild_id
    user_id = interaction.user.id

    # Create initial embed
    embed = discord.Embed(
        title=question[:256],  # Discord title limit
        description="Searching for answers...",
        color=discord.Color.blue(),
    )
    embed.set_footer(text="Powered by Agno + Exa")

    message = await interaction.followup.send(embed=embed)

    try:
        agent = get_game_agent()
    except ValueError as e:
        embed.description = f"Configuration error: {e}"
        embed.color = discord.Color.red()
        await message.edit(embed=embed)
        return

    try:
        response_chunks: list[str] = []
        last_update = time.monotonic()

        async for chunk in agent.ask(guild_id, user_id, question):
            response_chunks.append(chunk)

            # Update embed at most once per second to avoid rate limits
            if time.monotonic() - last_update >= 1.0:
                embed.description = "".join(response_chunks)[:4000]  # Discord embed limit
                embed.color = discord.Color.gold()
                await message.edit(embed=embed)
                last_update = time.monotonic()

        # Final update with complete response
        full_response = "".join(response_chunks)
        embed.description = full_response[:4000] if full_response else "No response generated."
        embed.color = discord.Color.green()
        await message.edit(embed=embed)

    except (TimeoutError, asyncio.TimeoutError):
        embed.description = "Request timed out. Please try again."
        embed.color = discord.Color.red()
        await message.edit(embed=embed)
    except Exception as e:
        embed.description = f"Error: {str(e)[:500]}"
        embed.color = discord.Color.red()
        await message.edit(embed=embed)


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
