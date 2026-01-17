"""Discord Music Bot with slash commands, autoplay, and Opus streaming."""

import os
import shutil

import discord
from discord import app_commands
from dotenv import load_dotenv

from autoplay import YouTubeMusicHandler
from music_player import player_manager
from youtube import extract_playlist, extract_song_info, is_playlist_url, search_youtube

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
async def skip(interaction: discord.Interaction):
    """Skip the current song."""
    guild_id = interaction.guild_id

    if player_manager.skip(guild_id):
        await interaction.response.send_message("Skipped!")
    else:
        await interaction.response.send_message("Nothing is playing.", ephemeral=True)


@client.tree.command(name="stop", description="Stop playback and clear queue")
async def stop(interaction: discord.Interaction):
    """Stop playback and disconnect."""
    guild_id = interaction.guild_id
    await player_manager.disconnect(guild_id)
    await interaction.response.send_message("Stopped and disconnected.")


@client.tree.command(name="pause", description="Pause the current song")
async def pause(interaction: discord.Interaction):
    """Pause the current song."""
    guild_id = interaction.guild_id

    if player_manager.pause(guild_id):
        await interaction.response.send_message("Paused.")
    else:
        await interaction.response.send_message("Nothing is playing.", ephemeral=True)


@client.tree.command(name="resume", description="Resume playback")
async def resume(interaction: discord.Interaction):
    """Resume paused playback."""
    guild_id = interaction.guild_id

    if player_manager.resume(guild_id):
        await interaction.response.send_message("Resumed.")
    else:
        await interaction.response.send_message("Nothing is paused.", ephemeral=True)


@client.tree.command(name="queue", description="Show the current queue")
async def queue(interaction: discord.Interaction):
    """Show the current queue."""
    guild_id = interaction.guild_id

    current = player_manager.get_current_song(guild_id)
    songs = player_manager.get_queue(guild_id)
    player = player_manager.get_player(guild_id)

    if not current and not songs:
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

    await interaction.response.send_message("\n".join(lines))


@client.tree.command(name="nowplaying", description="Show the currently playing song")
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
async def autoplay(interaction: discord.Interaction):
    """Toggle autoplay mode on/off."""
    guild_id = interaction.guild_id
    enabled = player_manager.toggle_autoplay(guild_id)

    status = "enabled" if enabled else "disabled"
    await interaction.response.send_message(f"Autoplay **{status}**.")


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
        player.voice_client = None
        player.current_song = None
        player.queue.clear()


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
