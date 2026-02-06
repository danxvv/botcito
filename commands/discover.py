"""AI-powered music discovery command."""

import asyncio

import discord
from discord import app_commands, ui

from audit.logger import log_command
from music_player import player_manager
from youtube import extract_song_info


class DiscoveryView(ui.View):
    """Interactive view for selecting discovered songs to play."""

    def __init__(self, songs, guild_id, requester, client, timeout=300.0):
        super().__init__(timeout=timeout)
        self.songs = songs
        self.guild_id = guild_id
        self.requester = requester
        self.client = client
        self.message = None

        options = []
        for song in songs[:25]:
            desc = song.artist
            if song.reason:
                desc = f"{song.artist} - {song.reason}"
            options.append(
                discord.SelectOption(
                    label=song.title[:100],
                    description=desc[:100],
                    value=song.video_id,
                )
            )

        self.song_select = ui.Select(
            placeholder="Pick songs to add to queue...",
            min_values=1,
            max_values=min(len(options), 25),
            options=options,
        )
        self.song_select.callback = self.select_callback
        self.add_item(self.song_select)

    async def _queue_songs(self, interaction: discord.Interaction, songs_to_queue):
        """Queue discovered songs and start playback."""
        if not interaction.user.voice:
            await interaction.response.send_message(
                "You need to be in a voice channel!", ephemeral=True
            )
            return

        await interaction.response.defer()
        channel = interaction.user.voice.channel
        await player_manager.connect(self.guild_id, channel)

        queued = 0
        for song in songs_to_queue:
            info = await extract_song_info(song.video_id)
            if info:
                await player_manager.add_to_queue(self.guild_id, info)
                queued += 1

        if not player_manager.is_playing(self.guild_id) and queued > 0:
            await player_manager.play_next(self.guild_id)

        count_text = "song" if queued == 1 else "songs"
        await interaction.followup.send(f"Added **{queued}** {count_text} to the queue!")

        self._disable_all()
        if self.message:
            await self.message.edit(view=self)

    @ui.button(label="Play All", style=discord.ButtonStyle.primary, emoji="\u25b6")
    async def play_all(self, interaction: discord.Interaction, button: ui.Button):
        await self._queue_songs(interaction, self.songs)

    async def select_callback(self, interaction: discord.Interaction):
        selected_ids = set(self.song_select.values)
        selected = [s for s in self.songs if s.video_id in selected_ids]
        await self._queue_songs(interaction, selected)

    def _disable_all(self):
        for child in self.children:
            if hasattr(child, "disabled"):
                child.disabled = True

    async def on_timeout(self):
        self._disable_all()
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.NotFound:
                pass


def setup(client):
    """Register the /discover command."""

    @client.tree.command(
        name="discover",
        description="AI-powered music discovery from natural language descriptions",
    )
    @app_commands.guild_only()
    @app_commands.describe(
        description="Describe the music you want (mood, genre, similar artists, vibe, etc.)"
    )
    @log_command
    async def discover(interaction: discord.Interaction, description: str):
        await interaction.response.defer()

        embed = discord.Embed(
            title=f"Discovering: {description[:200]}",
            description="Searching for the perfect songs...",
            color=discord.Color.purple(),
        )
        message = await interaction.followup.send(embed=embed)

        try:
            agent = client.get_music_discovery_agent()
        except Exception as e:
            embed.description = f"Configuration error: {e}"
            embed.color = discord.Color.red()
            await message.edit(embed=embed)
            return

        try:
            result = await asyncio.wait_for(agent.discover(description), timeout=60.0)
        except (TimeoutError, asyncio.TimeoutError):
            embed.description = "Discovery timed out. Please try again."
            embed.color = discord.Color.red()
            await message.edit(embed=embed)
            return
        except Exception as e:
            embed.description = f"Error during discovery: {str(e)[:500]}"
            embed.color = discord.Color.red()
            await message.edit(embed=embed)
            return

        if not result or not result.songs:
            embed.description = "Could not find songs matching your description. Try being more specific or using different keywords."
            embed.color = discord.Color.orange()
            await message.edit(embed=embed)
            return

        lines = []
        for i, song in enumerate(result.songs, 1):
            line = f"**{i}.** {song.title} - {song.artist}"
            if song.reason:
                line += f" -- {song.reason}"
            lines.append(line)

        embed.description = f"*{result.summary}*\n\n" + "\n".join(lines)
        embed.color = discord.Color.green()
        embed.set_footer(
            text=f"Found {len(result.songs)} songs | Select songs below to play"
        )

        view = DiscoveryView(
            songs=result.songs,
            guild_id=interaction.guild_id,
            requester=interaction.user,
            client=client,
        )
        view.message = message
        await message.edit(embed=embed, view=view)
