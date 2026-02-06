"""Music playback commands: play, skip, stop, pause, resume, queue, nowplaying, autoplay, clearhistory, shuffle."""

import discord
from discord import app_commands

from autoplay import YouTubeMusicHandler
from audit.logger import log_command
from music_player import player_manager
from ratings import get_rating_counts, get_user_rating
from youtube import extract_playlist, extract_song_info, is_playlist_url, search_youtube

from commands.helpers import (
    ensure_voice,
    format_duration,
    render_progress_bar,
    _log_music_event,
)

# YouTube Music handler for autocomplete
ytmusic = YouTubeMusicHandler()


def setup(client):
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
            vote_indicator = " (You: \U0001f44d)"
        elif user_vote == -1:
            vote_indicator = " (You: \U0001f44e)"
        embed.add_field(name="Rating", value=f"\U0001f44d {likes} / \U0001f44e {dislikes}{vote_indicator}")

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
