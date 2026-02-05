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
from audit.database import get_user_music_stats, get_guild_music_leaderboard
from ratings import rate_song, get_song_rating_score, get_user_rating, get_rating_counts

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
        self._game_agent = None
        self._voice_conversation = None

    async def setup_hook(self):
        """Sync commands on startup."""
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
                VoiceConversation,
                get_tts_config,
            )

            agent = self.get_game_agent()
            mcp_url, language = get_tts_config()
            tts_provider = ChatterboxTTSProvider(mcp_url=mcp_url, default_language=language)

            self._voice_conversation = VoiceConversation(
                game_agent=agent,
                player_manager=player_manager,
                tts_provider=tts_provider,
            )
        return self._voice_conversation


client = MusicBot()


# ============== Helper Functions ==============


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


def get_tts_error_message(error: Exception) -> str:
    """Get a user-friendly error message for TTS exceptions."""
    from voice_agent import TTSConnectionError, TTSGenerationError

    if isinstance(error, TTSConnectionError):
        return "TTS server not available. Make sure Chatterbox TTS is running."
    if isinstance(error, TTSGenerationError):
        return f"Failed to generate speech: {error}"
    if isinstance(error, NotImplementedError):
        return "TTS provider not configured."
    if isinstance(error, ValueError):
        return f"Error: {error}"
    return f"Error generating speech: {error}"


def get_tts_footer_status(error: Exception) -> str:
    """Get a short TTS error status for embed footers."""
    from voice_agent import TTSConnectionError, TTSGenerationError

    if isinstance(error, TTSConnectionError):
        return "TTS server unavailable"
    if isinstance(error, TTSGenerationError):
        return f"TTS error: {str(error)[:50]}"
    if isinstance(error, NotImplementedError):
        return "TTS not configured"
    return f"Voice error: {str(error)[:50]}"


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

    # Video ID from autocomplete (11 chars) or direct URL → extract directly; otherwise search
    if query.startswith("http") or len(query) == 11:
        song = await extract_song_info(query)
    else:
        song = await search_youtube(query)

    if not song:
        await interaction.followup.send("Could not find or play that song.")
        return

    # Add to queue
    position = await player_manager.add_to_queue(guild_id, song)

    # Log music event
    source_type = "url" if query.startswith("http") else "search"
    _log_music_event(interaction, song, source_type, "play")

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
            _log_music_event(interaction, current, "queue", "skip")
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
        _log_music_event(interaction, current, "queue", "stop")

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
    user_id = interaction.user.id
    song = player_manager.get_current_song(guild_id)

    if not song:
        await interaction.response.send_message("Nothing is playing.", ephemeral=True)
        return

    embed = discord.Embed(
        title="Now Playing",
        description=f"**{song.title}**",
        color=discord.Color.blurple(),
    )

    # Progress bar
    elapsed = player_manager.get_elapsed_seconds(guild_id)
    if elapsed is not None:
        progress_bar = render_progress_bar(elapsed, song.duration)
        paused_indicator = " (Paused)" if player_manager.is_paused(guild_id) else ""
        embed.add_field(name="Progress", value=f"`{progress_bar}`{paused_indicator}", inline=False)
    else:
        embed.add_field(name="Duration", value=format_duration(song.duration))

    embed.add_field(name="URL", value=f"[Link]({song.webpage_url})")

    # Rating info
    likes, dislikes = get_rating_counts(guild_id, song.video_id)
    user_vote = get_user_rating(guild_id, song.video_id, user_id)
    vote_indicator = ""
    if user_vote == 1:
        vote_indicator = " (You: 👍)"
    elif user_vote == -1:
        vote_indicator = " (You: 👎)"
    embed.add_field(name="Rating", value=f"👍 {likes} / 👎 {dislikes}{vote_indicator}")

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


@client.tree.command(name="shuffle", description="Shuffle the current queue")
@log_command
async def shuffle(interaction: discord.Interaction):
    """Shuffle the songs in the queue."""
    guild_id = interaction.guild_id
    count = await player_manager.shuffle_queue(guild_id)

    if count == 0:
        await interaction.response.send_message("Queue is empty.", ephemeral=True)
    elif count == 1:
        await interaction.response.send_message("Only one song in queue.", ephemeral=True)
    else:
        await interaction.response.send_message(f"Shuffled **{count}** songs in the queue!")


@client.tree.command(name="stats", description="View your music listening statistics")
@app_commands.describe(period="Time period for statistics")
@app_commands.choices(period=[
    app_commands.Choice(name="Last 24 hours", value="24h"),
    app_commands.Choice(name="Last 7 days", value="7d"),
    app_commands.Choice(name="Last 30 days", value="30d"),
    app_commands.Choice(name="All time", value="all"),
])
@log_command
async def stats(interaction: discord.Interaction, period: app_commands.Choice[str] | None = None):
    """View your music listening statistics."""
    guild_id = interaction.guild_id
    user_id = interaction.user.id
    hours = period_to_hours(period)

    user_stats = get_user_music_stats(user_id, guild_id, hours)

    period_name = period.name if period else "All time"
    embed = discord.Embed(
        title=f"Music Stats for {interaction.user.display_name}",
        description=f"**{period_name}**",
        color=discord.Color.purple(),
    )

    embed.add_field(name="Songs Played", value=str(user_stats["songs_played"]), inline=True)
    embed.add_field(
        name="Time Listened",
        value=format_duration(user_stats["total_duration"]),
        inline=True,
    )

    if user_stats["top_songs"]:
        top_songs_text = "\n".join(
            f"{i}. {song['title'][:40]}{'...' if len(song['title']) > 40 else ''} ({song['play_count']}x)"
            for i, song in enumerate(user_stats["top_songs"], 1)
        )
        embed.add_field(name="Top Songs", value=top_songs_text, inline=False)
    else:
        embed.add_field(name="Top Songs", value="No songs played yet", inline=False)

    embed.set_thumbnail(url=interaction.user.display_avatar.url)
    await interaction.response.send_message(embed=embed)


@client.tree.command(name="leaderboard", description="View server music leaderboard")
@app_commands.describe(period="Time period for leaderboard")
@app_commands.choices(period=[
    app_commands.Choice(name="Last 24 hours", value="24h"),
    app_commands.Choice(name="Last 7 days", value="7d"),
    app_commands.Choice(name="Last 30 days", value="30d"),
    app_commands.Choice(name="All time", value="all"),
])
@log_command
async def leaderboard(interaction: discord.Interaction, period: app_commands.Choice[str] | None = None):
    """View server music leaderboard."""
    guild_id = interaction.guild_id
    hours = period_to_hours(period)

    leaderboard_data = get_guild_music_leaderboard(guild_id, hours, limit=10)

    period_name = period.name if period else "All time"
    embed = discord.Embed(
        title=f"Music Leaderboard - {interaction.guild.name}",
        description=f"**{period_name}**",
        color=discord.Color.gold(),
    )

    if not leaderboard_data:
        embed.add_field(name="No data", value="No one has played music yet!", inline=False)
    else:
        medals = ["🥇", "🥈", "🥉"]
        lines = []
        for i, entry in enumerate(leaderboard_data):
            prefix = medals[i] if i < 3 else f"{i + 1}."
            name = entry["user_name"] or f"User {entry['user_id']}"
            duration = format_duration(entry["total_duration"])
            lines.append(f"{prefix} **{name}** - {entry['songs_played']} songs ({duration})")

        embed.description = f"**{period_name}**\n\n" + "\n".join(lines)

    await interaction.response.send_message(embed=embed)


async def _handle_song_rating(
    interaction: discord.Interaction, rating: int, emoji: str, action: str
) -> None:
    """Handle like/dislike rating for the current song."""
    guild_id = interaction.guild_id
    user_id = interaction.user.id
    song = player_manager.get_current_song(guild_id)

    if not song:
        await interaction.response.send_message("Nothing is playing.", ephemeral=True)
        return

    current_rating = get_user_rating(guild_id, song.video_id, user_id)
    if current_rating == rating:
        await interaction.response.send_message(
            f"You already {action} **{song.title}**!", ephemeral=True
        )
        return

    rate_song(guild_id, song.video_id, user_id, rating, title=song.title)
    likes, dislikes = get_rating_counts(guild_id, song.video_id)

    await interaction.response.send_message(
        f"{emoji} {action.capitalize()} **{song.title}**!\n"
        f"Rating: {likes} 👍 / {dislikes} 👎"
    )


@client.tree.command(name="like", description="Like the current song (affects autoplay)")
@log_command
async def like(interaction: discord.Interaction):
    """Like the currently playing song."""
    await _handle_song_rating(interaction, rating=1, emoji="👍", action="liked")


@client.tree.command(name="dislike", description="Dislike the current song (affects autoplay)")
@log_command
async def dislike(interaction: discord.Interaction):
    """Dislike the currently playing song."""
    await _handle_song_rating(interaction, rating=-1, emoji="👎", action="disliked")


@client.tree.command(name="record", description="Start recording voice channel audio")
@log_command
async def record(interaction: discord.Interaction):
    """Start recording audio from the voice channel."""
    if not await ensure_voice(interaction):
        return

    guild_id = interaction.guild_id

    # Check if already recording
    if player_manager.is_recording(guild_id):
        await interaction.response.send_message(
            "Already recording! Use `/stoprecord` to stop.", ephemeral=True
        )
        return

    # Connect to voice channel if not already connected
    channel = interaction.user.voice.channel
    await player_manager.connect(guild_id, channel)

    # Start recording
    session = await player_manager.start_recording(guild_id, interaction.user.id)

    if session:
        await interaction.response.send_message(
            f"Recording started. Use `/stoprecord` to save the recording.\n"
            f"Session ID: `{session.session_id}`"
        )
    else:
        await interaction.response.send_message(
            "Failed to start recording. Make sure the bot is in a voice channel.",
            ephemeral=True,
        )


@client.tree.command(name="stoprecord", description="Stop recording and save audio files")
@log_command
async def stoprecord(interaction: discord.Interaction):
    """Stop recording and save audio files."""
    guild_id = interaction.guild_id

    if not player_manager.is_recording(guild_id):
        await interaction.response.send_message(
            "Not currently recording. Use `/record` to start.", ephemeral=True
        )
        return

    await interaction.response.defer()

    # Stop recording and save files
    stats = await player_manager.stop_recording(guild_id)

    if not stats:
        await interaction.followup.send("Failed to stop recording.")
        return

    if stats["user_count"] == 0:
        await interaction.followup.send(
            "Recording stopped. No audio was captured.\n"
            f"Session ID: `{stats['session_id']}`"
        )
        return

    # Build response message
    lines = [
        f"Recording saved!",
        f"Session ID: `{stats['session_id']}`",
        f"Duration: {stats['total_seconds']:.1f}s",
        f"Users recorded: {stats['user_count']}",
        f"Output: `{stats['output_dir']}`",
        "",
        "**Files:**",
    ]

    for user_id, user_info in stats["users"].items():
        filepath = stats["saved_files"].get(user_id, "N/A")
        lines.append(f"- {user_info['name']}: {user_info['seconds']:.1f}s")

    await interaction.followup.send("\n".join(lines))


@client.tree.command(name="talk", description="Start voice conversation mode - bot listens and responds")
@log_command
async def talk(interaction: discord.Interaction):
    """Start voice conversation mode."""
    if not await ensure_voice(interaction):
        return

    guild_id = interaction.guild_id

    try:
        voice_conv = client.get_voice_conversation()
    except ValueError as e:
        await interaction.response.send_message(
            f"Configuration error: {e}", ephemeral=True
        )
        return

    # Check if already in talk mode
    if voice_conv.is_active(guild_id):
        await interaction.response.send_message(
            "Already in voice conversation mode! Use `/stoptalk` to stop.",
            ephemeral=True,
        )
        return

    # Connect to voice channel if not already connected
    channel = interaction.user.voice.channel
    voice_client = await player_manager.connect(guild_id, channel)

    # Start voice conversation
    try:
        await voice_conv.start(guild_id, voice_client)
        tts_status = "" if voice_conv.tts_available else "\n*Note: TTS not configured - responses will be logged to console only.*"
        await interaction.response.send_message(
            "Voice conversation started! I'm now listening. "
            "Speak naturally and I'll respond after you pause.\n"
            f"Use `/stoptalk` to end the conversation.{tts_status}"
        )
    except ValueError as e:
        await interaction.response.send_message(
            f"Failed to start voice conversation: {e}", ephemeral=True
        )


@client.tree.command(name="stoptalk", description="Stop voice conversation mode")
@log_command
async def stoptalk(interaction: discord.Interaction):
    """Stop voice conversation mode."""
    guild_id = interaction.guild_id

    try:
        voice_conv = client.get_voice_conversation()
    except ValueError as e:
        await interaction.response.send_message(
            f"Configuration error: {e}", ephemeral=True
        )
        return

    if not voice_conv.is_active(guild_id):
        await interaction.response.send_message(
            "Not in voice conversation mode. Use `/talk` to start.",
            ephemeral=True,
        )
        return

    voice_conv.stop(guild_id)
    await interaction.response.send_message("Voice conversation ended.")


@client.tree.command(name="speak", description="Make the bot speak text aloud")
@app_commands.describe(text="The text for the bot to speak", language="Language for TTS")
@app_commands.choices(language=[
    app_commands.Choice(name="Spanish", value="es"),
    app_commands.Choice(name="English", value="en"),
    app_commands.Choice(name="French", value="fr"),
    app_commands.Choice(name="German", value="de"),
    app_commands.Choice(name="Italian", value="it"),
    app_commands.Choice(name="Portuguese", value="pt"),
    app_commands.Choice(name="Polish", value="pl"),
    app_commands.Choice(name="Turkish", value="tr"),
    app_commands.Choice(name="Russian", value="ru"),
    app_commands.Choice(name="Dutch", value="nl"),
    app_commands.Choice(name="Czech", value="cs"),
    app_commands.Choice(name="Arabic", value="ar"),
    app_commands.Choice(name="Chinese", value="zh"),
    app_commands.Choice(name="Japanese", value="ja"),
    app_commands.Choice(name="Hungarian", value="hu"),
    app_commands.Choice(name="Korean", value="ko"),
])
@log_command
async def speak(
    interaction: discord.Interaction,
    text: str,
    language: app_commands.Choice[str] | None = None,
):
    """Make the bot speak text using TTS."""
    if not await ensure_voice(interaction):
        return

    guild_id = interaction.guild_id
    await interaction.response.defer()

    try:
        voice_conv = client.get_voice_conversation()
    except ValueError as e:
        await interaction.followup.send(f"Configuration error: {e}")
        return

    # Connect to voice channel if not already connected
    channel = interaction.user.voice.channel
    await player_manager.connect(guild_id, channel)

    # Get language value if provided
    lang = language.value if language else None

    # Speak the text
    try:
        success = await voice_conv.speak_text(guild_id, text, language=lang)
        if success:
            lang_display = f" ({language.name})" if language else ""
            truncated = f"{text[:100]}..." if len(text) > 100 else text
            await interaction.followup.send(f"Speaking{lang_display}: *{truncated}*")
        else:
            await interaction.followup.send("Failed to speak. Bot may not be in a voice channel.")
    except Exception as e:
        await interaction.followup.send(get_tts_error_message(e))


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
@app_commands.describe(
    question="Your gaming question (tips, strategies, builds, etc.)",
    voice="Enable voice output (default: off)"
)
@log_command
async def guide(interaction: discord.Interaction, question: str, voice: bool | None = None):
    """Answer gaming questions using AI with web search."""
    # Check if user is in voice channel
    user_in_voice = interaction.user.voice is not None
    voice_channel = interaction.user.voice.channel if user_in_voice else None

    # Handle explicit voice=True when not in voice channel
    if voice is True and not user_in_voice:
        await interaction.response.send_message(
            "You need to be in a voice channel to use voice output!",
            ephemeral=True,
        )
        return

    await interaction.response.defer()

    guild_id = interaction.guild_id
    user_id = interaction.user.id

    # Create initial embed
    embed = discord.Embed(
        title=question[:256],  # Discord title limit
        description="Searching for answers...",
        color=discord.Color.blue(),
    )
    embed.set_footer(text="Powered by GameGuide Team")

    message = await interaction.followup.send(embed=embed)

    try:
        agent = client.get_game_agent()
    except ValueError as e:
        embed.description = f"Configuration error: {e}"
        embed.color = discord.Color.red()
        await message.edit(embed=embed)
        return

    # Voice output only if explicitly enabled
    should_speak = voice is True

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

        # Speak response if voice output is enabled
        if should_speak and full_response.strip():
            await _speak_guide_response(interaction, voice_channel, full_response, embed, message)

    except (TimeoutError, asyncio.TimeoutError):
        embed.description = "Request timed out. Please try again."
        embed.color = discord.Color.red()
        await message.edit(embed=embed)
    except Exception as e:
        embed.description = f"Error: {str(e)[:500]}"
        embed.color = discord.Color.red()
        await message.edit(embed=embed)


async def _speak_guide_response(
    interaction: discord.Interaction,
    voice_channel,
    full_response: str,
    embed: discord.Embed,
    message,
):
    """Speak the guide response via TTS."""
    guild_id = interaction.guild_id
    tts_text = _truncate_for_tts(full_response)

    try:
        await player_manager.connect(guild_id, voice_channel)
        voice_conv = client.get_voice_conversation()

        embed.set_footer(text="Powered by Agno + Exa | Speaking...")
        await message.edit(embed=embed)

        await voice_conv.speak_text(guild_id, tts_text)

        embed.set_footer(text="Powered by Agno + Exa | Spoken")
        await message.edit(embed=embed)
    except Exception as e:
        status = get_tts_footer_status(e)
        embed.set_footer(text=f"Powered by Agno + Exa | {status}")
        await message.edit(embed=embed)


def _truncate_for_tts(text: str, max_chars: int = 2000) -> str:
    """Truncate text for TTS at a sentence boundary."""
    if len(text) <= max_chars:
        return text

    truncate_at = max_chars
    for punct in [". ", "! ", "? ", "\n"]:
        last_pos = text[:max_chars].rfind(punct)
        if last_pos > max_chars // 2:
            truncate_at = last_pos + 1
            break
    return text[:truncate_at].strip()


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
