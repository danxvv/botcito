"""Music playback commands: play, skip, stop, pause, resume, queue, nowplaying, autoplay, clearhistory, shuffle."""

import asyncio

import discord
from discord import app_commands

from autoplay import YouTubeMusicHandler
from audit.database import get_music_history
from audit.logger import log_command
from music_player import player_manager
from ratings import get_rating_counts, get_user_rating, rate_song
from youtube import extract_playlist, extract_song_info, is_playlist_url, search_youtube

from commands.helpers import (
    ensure_same_voice,
    ensure_voice,
    format_duration,
    render_progress_bar,
    _log_music_event,
)

# YouTube Music handler for autocomplete
ytmusic = YouTubeMusicHandler()


class SearchSelect(discord.ui.Select):
    """Select menu for choosing a search result."""

    def __init__(self, results: list[dict]):
        options = []
        for result in results[:5]:
            label = f"{result['title']} - {result['artist']}"[:100]
            options.append(
                discord.SelectOption(
                    label=label,
                    value=result["videoId"],
                    description=(result.get("duration") or "YouTube Music")[:100],
                )
            )
        super().__init__(placeholder="Choose a song", options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        self.view.selected_video_id = self.values[0]
        await interaction.response.defer()
        self.view.stop()


class SearchSelectView(discord.ui.View):
    """Search result picker restricted to the requesting user."""

    def __init__(self, user_id: int, results: list[dict]):
        super().__init__(timeout=45)
        self.user_id = user_id
        self.selected_video_id: str | None = None
        self.add_item(SearchSelect(results))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.user_id:
            return True
        await interaction.response.send_message("This search is not yours.", ephemeral=True)
        return False


class NowPlayingView(discord.ui.View):
    """Small control panel for the current guild player."""

    def __init__(self, guild_id: int):
        super().__init__(timeout=180)
        self.guild_id = guild_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        player = player_manager.get_player(self.guild_id)
        return await ensure_same_voice(interaction, player.voice_client)

    @discord.ui.button(label="Pause/Resume", style=discord.ButtonStyle.secondary)
    async def pause_resume(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if player_manager.is_paused(self.guild_id):
            changed = player_manager.resume(self.guild_id)
            message = "Resumed." if changed else "Nothing is paused."
        else:
            changed = player_manager.pause(self.guild_id)
            message = "Paused." if changed else "Nothing is playing."
        await interaction.response.send_message(message, ephemeral=True)

    @discord.ui.button(label="Skip", style=discord.ButtonStyle.primary)
    async def skip_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        current = player_manager.get_current_song(self.guild_id)
        if player_manager.skip(self.guild_id):
            if current:
                _log_music_event(interaction, current, "queue", "skip")
            await interaction.response.send_message("Skipped.", ephemeral=True)
        else:
            await interaction.response.send_message("Nothing is playing.", ephemeral=True)

    @discord.ui.button(label="Like", style=discord.ButtonStyle.success)
    async def like_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._rate(interaction, 1, "Liked")

    @discord.ui.button(label="Dislike", style=discord.ButtonStyle.danger)
    async def dislike_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._rate(interaction, -1, "Disliked")

    @discord.ui.button(label="Queue", style=discord.ButtonStyle.secondary)
    async def queue_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        songs = player_manager.get_queue(self.guild_id)
        if not songs:
            await interaction.response.send_message("Queue is empty.", ephemeral=True)
            return
        lines = [
            f"{i}. {song.title} [{format_duration(song.duration)}]"
            for i, song in enumerate(songs[:10], 1)
        ]
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    async def _rate(self, interaction: discord.Interaction, rating: int, action: str) -> None:
        song = player_manager.get_current_song(self.guild_id)
        if not song:
            await interaction.response.send_message("Nothing is playing.", ephemeral=True)
            return
        await asyncio.to_thread(
            rate_song, self.guild_id, song.video_id, interaction.user.id, rating, song.title
        )
        likes, dislikes = await asyncio.to_thread(get_rating_counts, self.guild_id, song.video_id)
        await interaction.response.send_message(
            f"{action} **{song.title}**. Rating: {likes} likes / {dislikes} dislikes",
            ephemeral=True,
        )


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
        guild_name = interaction.guild.name if interaction.guild else "DM"
        requester_name = str(interaction.user)

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
                    position = await player_manager.add_to_queue(
                        guild_id,
                        song,
                        requester_id=interaction.user.id,
                        requester_name=requester_name,
                        guild_name=guild_name,
                        source_type="playlist",
                    )
                    if position > 0:
                        added += 1
                    else:
                        break

            await interaction.followup.send(f"Added **{added}** songs from playlist to queue!")

            # Start playing if not already
            if not player_manager.is_playing(guild_id):
                await player_manager.play_next(guild_id)
            return

        # Video ID from autocomplete (11 chars) or direct URL → extract directly; otherwise search
        if query.startswith("http") or len(query) == 11:
            song = await extract_song_info(query)
        else:
            results = await ytmusic.search_songs_async(query, limit=5)
            if results:
                view = SearchSelectView(interaction.user.id, results)
                await interaction.followup.send(
                    "Choose a song from the search results:", view=view, ephemeral=True
                )
                await view.wait()
                if not view.selected_video_id:
                    await interaction.followup.send("Search timed out.", ephemeral=True)
                    return
                song = await extract_song_info(view.selected_video_id)
            else:
                song = await search_youtube(query)

        if not song:
            await interaction.followup.send("Could not find or play that song.")
            return

        # Add to queue
        source_type = "url" if query.startswith("http") else "search"
        position = await player_manager.add_to_queue(
            guild_id,
            song,
            requester_id=interaction.user.id,
            requester_name=requester_name,
            guild_name=guild_name,
            source_type=source_type,
        )
        if position < 0:
            await interaction.followup.send("Queue is full. Try again after a few songs play.")
            return

        # Start playing if not already
        if not player_manager.is_playing(guild_id):
            started = await player_manager.play_next(guild_id)
            if started:
                await interaction.followup.send(
                    f"Now playing: **{started.title}** [{format_duration(started.duration)}]"
                )
            else:
                await interaction.followup.send("Could not start playback.")
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

        results = await ytmusic.search_songs_async(current, limit=10)
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
        player = player_manager.get_player(guild_id)
        if not await ensure_same_voice(interaction, player.voice_client):
            return

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
        player = player_manager.get_player(guild_id)
        if not await ensure_same_voice(interaction, player.voice_client):
            return

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
        player = player_manager.get_player(guild_id)
        if not await ensure_same_voice(interaction, player.voice_client):
            return

        if player_manager.pause(guild_id):
            await interaction.response.send_message("Paused.")
        else:
            await interaction.response.send_message("Nothing is playing.", ephemeral=True)

    @client.tree.command(name="resume", description="Resume playback")
    @log_command
    async def resume(interaction: discord.Interaction):
        """Resume paused playback."""
        guild_id = interaction.guild_id
        player = player_manager.get_player(guild_id)
        if not await ensure_same_voice(interaction, player.voice_client):
            return

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

    @client.tree.command(name="volume", description="Set playback volume")
    @app_commands.describe(percent="Volume from 0 to 100")
    @log_command
    async def volume(interaction: discord.Interaction, percent: int):
        """Set playback volume for this server."""
        guild_id = interaction.guild_id
        player = player_manager.get_player(guild_id)
        if not await ensure_same_voice(interaction, player.voice_client):
            return

        if percent < 0 or percent > 100:
            await interaction.response.send_message("Use a volume from 0 to 100.", ephemeral=True)
            return

        player_manager.set_volume(guild_id, percent / 100)
        await interaction.response.send_message(f"Volume set to **{percent}%**.")

    @client.tree.command(name="remove", description="Remove a song from the queue")
    @app_commands.describe(position="Queue position to remove")
    @log_command
    async def remove(interaction: discord.Interaction, position: int):
        """Remove a queued song."""
        guild_id = interaction.guild_id
        player = player_manager.get_player(guild_id)
        if not await ensure_same_voice(interaction, player.voice_client):
            return

        song = await player_manager.remove_from_queue(guild_id, position)
        if not song:
            await interaction.response.send_message("That queue position does not exist.", ephemeral=True)
            return
        await interaction.response.send_message(f"Removed **{song.title}** from the queue.")

    @client.tree.command(name="move", description="Move a song in the queue")
    @app_commands.describe(
        from_position="Current queue position",
        to_position="New queue position",
    )
    @log_command
    async def move(interaction: discord.Interaction, from_position: int, to_position: int):
        """Move a queued song."""
        guild_id = interaction.guild_id
        player = player_manager.get_player(guild_id)
        if not await ensure_same_voice(interaction, player.voice_client):
            return

        moved = await player_manager.move_in_queue(guild_id, from_position, to_position)
        if not moved:
            await interaction.response.send_message("Those queue positions are invalid.", ephemeral=True)
            return
        song, final_position = moved
        await interaction.response.send_message(
            f"Moved **{song.title}** to queue position #{final_position}."
        )

    @client.tree.command(name="clearqueue", description="Clear queued songs")
    @log_command
    async def clearqueue(interaction: discord.Interaction):
        """Clear queued songs without stopping the current track."""
        guild_id = interaction.guild_id
        player = player_manager.get_player(guild_id)
        if not await ensure_same_voice(interaction, player.voice_client):
            return

        count = await player_manager.clear_queue(guild_id)
        if count:
            await interaction.response.send_message(f"Cleared **{count}** queued songs.")
        else:
            await interaction.response.send_message("Queue is already empty.", ephemeral=True)

    @client.tree.command(name="history", description="Show recently played songs")
    @log_command
    async def history(interaction: discord.Interaction):
        """Show recent play history for this server."""
        rows = await asyncio.to_thread(get_music_history, interaction.guild_id, None, 15)
        plays = [row for row in rows if row["action"] == "play"][:10]
        if not plays:
            await interaction.response.send_message("No play history yet.", ephemeral=True)
            return

        lines = []
        for i, row in enumerate(plays, 1):
            lines.append(
                f"{i}. [{row['title']}](https://www.youtube.com/watch?v={row['video_id']})"
            )
        embed = discord.Embed(
            title=f"Recent songs - {interaction.guild.name}",
            description="\n".join(lines),
            color=discord.Color.blurple(),
        )
        await interaction.response.send_message(embed=embed)

    @client.tree.command(name="replay", description="Replay a recent song")
    @app_commands.describe(position="History position from /history")
    @log_command
    async def replay(interaction: discord.Interaction, position: int = 1):
        """Replay a song from recent history."""
        if not await ensure_voice(interaction):
            return

        await interaction.response.defer()
        guild_id = interaction.guild_id
        channel = interaction.user.voice.channel
        await player_manager.connect(guild_id, channel)

        rows = await asyncio.to_thread(get_music_history, guild_id, None, 20)
        plays = [row for row in rows if row["action"] == "play"]
        if position < 1 or position > len(plays):
            await interaction.followup.send("That history position does not exist.", ephemeral=True)
            return

        row = plays[position - 1]
        song = await extract_song_info(row["video_id"])
        if not song:
            await interaction.followup.send("Could not replay that song.", ephemeral=True)
            return

        guild_name = interaction.guild.name if interaction.guild else "DM"
        queue_position = await player_manager.add_to_queue(
            guild_id,
            song,
            requester_id=interaction.user.id,
            requester_name=str(interaction.user),
            guild_name=guild_name,
            source_type="replay",
        )
        if queue_position < 0:
            await interaction.followup.send("Queue is full.", ephemeral=True)
            return

        if not player_manager.is_playing(guild_id):
            started = await player_manager.play_next(guild_id)
            if started:
                await interaction.followup.send(f"Replaying **{started.title}**.")
            else:
                await interaction.followup.send("Could not start playback.")
        else:
            await interaction.followup.send(
                f"Added replay to queue (#{queue_position}): **{song.title}**"
            )

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

        await interaction.response.send_message(embed=embed, view=NowPlayingView(guild_id))

    @client.tree.command(name="autoplay", description="Manage autoplay mode")
    @app_commands.describe(action="Autoplay action")
    @app_commands.choices(action=[
        app_commands.Choice(name="Toggle", value="toggle"),
        app_commands.Choice(name="Status", value="status"),
        app_commands.Choice(name="Refresh", value="refresh"),
    ])
    @log_command
    async def autoplay(
        interaction: discord.Interaction,
        action: app_commands.Choice[str] | None = None,
    ):
        """Toggle, inspect, or refresh autoplay."""
        guild_id = interaction.guild_id
        player = player_manager.get_player(guild_id)
        action_value = action.value if action else "toggle"

        if action_value == "status":
            status = "enabled" if player.autoplay_enabled else "disabled"
            await interaction.response.send_message(
                f"Autoplay is **{status}**. Prefetched songs: **{len(player.autoplay_queue)}**."
            )
            return

        if not await ensure_same_voice(interaction, player.voice_client):
            return

        if action_value == "refresh":
            refreshed = player_manager.refresh_autoplay(guild_id)
            if refreshed:
                await interaction.response.send_message("Autoplay recommendations refreshed.")
            else:
                await interaction.response.send_message(
                    "Autoplay needs to be enabled with a current song first.", ephemeral=True
                )
            return

        enabled = player_manager.toggle_autoplay(guild_id)
        status = "enabled" if enabled else "disabled"
        await interaction.response.send_message(f"Autoplay **{status}**.")

    @client.tree.command(name="clearhistory", description="Clear autoplay history to allow songs to repeat")
    @log_command
    async def clearhistory(interaction: discord.Interaction):
        """Clear played history so songs can be recommended again."""
        guild_id = interaction.guild_id
        player = player_manager.get_player(guild_id)
        if not await ensure_same_voice(interaction, player.voice_client):
            return

        player_manager.clear_history(guild_id)
        await interaction.response.send_message("Autoplay history cleared. Songs can now be recommended again.")

    @client.tree.command(name="shuffle", description="Shuffle the current queue")
    @log_command
    async def shuffle(interaction: discord.Interaction):
        """Shuffle the songs in the queue."""
        guild_id = interaction.guild_id
        player = player_manager.get_player(guild_id)
        if not await ensure_same_voice(interaction, player.voice_client):
            return

        count = await player_manager.shuffle_queue(guild_id)

        if count == 0:
            await interaction.response.send_message("Queue is empty.", ephemeral=True)
        elif count == 1:
            await interaction.response.send_message("Only one song in queue.", ephemeral=True)
        else:
            await interaction.response.send_message(f"Shuffled **{count}** songs in the queue!")
