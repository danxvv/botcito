"""Music playback commands: play, skip, stop, pause, resume, queue, nowplaying, autoplay, clearhistory, shuffle."""

import asyncio

import discord
from discord import app_commands

from audit.database import get_music_history
from audit.logger import log_command
from music_player import player_manager

from .helpers import ensure_same_voice, respond, _log_music_event
from .music_requests import request_play, ytmusic
from .player_view import panels
from .queue_view import show_queue


def setup(client: discord.Client) -> None:
    player_manager.on_change = panels.changed

    @client.tree.command(name="play", description="Play a song or add it to the queue")
    @app_commands.guild_only()
    @app_commands.describe(query="Song name, YouTube URL, or playlist")
    @log_command
    async def play(interaction: discord.Interaction, query: str) -> None:
        await request_play(interaction, query, source="url" if query.startswith("http") else "search")

    @play.autocomplete("query")
    async def play_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        if len(current) < 2 or current.startswith("http"):
            return []
        try:
            results = await asyncio.wait_for(ytmusic.search_songs_async(current, limit=10), timeout=2)
        except asyncio.TimeoutError:
            return []
        return [app_commands.Choice(name=f"{song['title']} - {song['artist']}"[:100], value=f"yt:{song['videoId']}") for song in results]

    @client.tree.command(name="skip", description="Skip the current song")
    @app_commands.guild_only()
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
    @app_commands.guild_only()
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

        await interaction.response.defer(ephemeral=True)
        await player_manager.disconnect(guild_id)
        await respond(interaction, "Stopped, cleared the queue, and cancelled pending requests.")

    @client.tree.command(name="pause", description="Pause the current song")
    @app_commands.guild_only()
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
    @app_commands.guild_only()
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
    @app_commands.guild_only()
    @log_command
    async def queue(interaction: discord.Interaction):
        """Show the current queue."""
        await show_queue(interaction)

    @client.tree.command(name="volume", description="Set playback volume")
    @app_commands.guild_only()
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
    @app_commands.guild_only()
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
    @app_commands.guild_only()
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
    @app_commands.guild_only()
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
            await interaction.response.send_message("Queue is empty. Any pending imports were cancelled.", ephemeral=True)

    @client.tree.command(name="history", description="Show recently played songs")
    @app_commands.guild_only()
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
    @app_commands.guild_only()
    @app_commands.describe(position="History position from /history")
    @log_command
    async def replay(interaction: discord.Interaction, position: int = 1):
        """Replay a song from recent history."""
        player = player_manager.get_player(interaction.guild_id)
        if not await ensure_same_voice(interaction, player.voice_client):
            return
        await interaction.response.defer(ephemeral=True)
        rows = await asyncio.to_thread(get_music_history, interaction.guild_id, None, 15)
        plays = [row for row in rows if row["action"] == "play"][:10]
        if position < 1 or position > len(plays):
            await interaction.edit_original_response(content="That history position does not exist. Use /history to choose a song.")
            return
        await request_play(interaction, f"yt:{plays[position - 1]['video_id']}", source="replay")

    @client.tree.command(name="nowplaying", description="Show the currently playing song")
    @app_commands.guild_only()
    @log_command
    async def nowplaying(interaction: discord.Interaction):
        """Show the currently playing song."""
        player = player_manager.get_player(interaction.guild_id)
        if not player.voice_client:
            await respond(interaction, "Nothing is playing. Join a voice channel and use /play.")
            return
        await interaction.response.defer(ephemeral=True)
        message = await panels.ensure(interaction)
        await interaction.edit_original_response(content=f"[Open the music player]({message.jump_url})")

    @client.tree.command(name="autoplay", description="Manage autoplay mode")
    @app_commands.guild_only()
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
                f"Autoplay is **{status}**. {len(player.autoplay_queue)} recommendations ready after your queue."
            )
            return

        if not await ensure_same_voice(interaction, player.voice_client):
            return

        if action_value == "refresh":
            refreshed = player_manager.refresh_autoplay(guild_id)
            if refreshed:
                await interaction.response.send_message("Finding new autoplay recommendations…")
            else:
                await interaction.response.send_message(
                    "Autoplay needs to be enabled with a current song first.", ephemeral=True
                )
            return

        enabled = player_manager.toggle_autoplay(guild_id)
        status = "enabled" if enabled else "disabled"
        await interaction.response.send_message(f"Autoplay **{status}**.")

    @client.tree.command(name="clearhistory", description="Clear autoplay history to allow songs to repeat")
    @app_commands.guild_only()
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
    @app_commands.guild_only()
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
