"""Stats and rating commands: stats, leaderboard, like, dislike."""

import discord
from discord import app_commands

from audit.database import get_user_music_stats, get_guild_music_leaderboard
from audit.logger import log_command
from music_player import player_manager
from ratings import rate_song, get_user_rating, get_rating_counts

from commands.helpers import format_duration, period_to_hours


def setup(client):
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
            medals = ["\U0001f947", "\U0001f948", "\U0001f949"]
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
            f"Rating: {likes} \U0001f44d / {dislikes} \U0001f44e"
        )

    @client.tree.command(name="like", description="Like the current song (affects autoplay)")
    @log_command
    async def like(interaction: discord.Interaction):
        """Like the currently playing song."""
        await _handle_song_rating(interaction, rating=1, emoji="\U0001f44d", action="liked")

    @client.tree.command(name="dislike", description="Dislike the current song (affects autoplay)")
    @log_command
    async def dislike(interaction: discord.Interaction):
        """Dislike the currently playing song."""
        await _handle_song_rating(interaction, rating=-1, emoji="\U0001f44e", action="disliked")
