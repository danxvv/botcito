"""Browse and edit a music queue using stable song selections."""

import discord

from music_player import player_manager
from .helpers import MusicView, ensure_same_voice, format_duration, respond

PAGE_SIZE = 10


def wait_label(guild_id: int, entry_id: str) -> str:
    seconds = player_manager.queue_wait(guild_id, entry_id)
    if seconds is None:
        return "start time unknown"
    return "up next" if seconds == 0 else f"about {format_duration(seconds)}"


class QueueView(MusicView):
    def __init__(self, guild_id: int, user_id: int) -> None:
        super().__init__(timeout=300)
        self.guild_id = guild_id
        self.user_id = user_id
        self.page = 0
        self.selected: str | None = None
        self.note = ""

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await respond(interaction, "Use /queue to open your own queue controls.")
            return False
        return True

    def render(self) -> discord.Embed:
        player = player_manager.get_player(self.guild_id)
        songs = list(player.queue)
        pages = max(1, (len(songs) + PAGE_SIZE - 1) // PAGE_SIZE)
        self.page = min(self.page, pages - 1)
        visible = songs[self.page * PAGE_SIZE : (self.page + 1) * PAGE_SIZE]
        embed = discord.Embed(
            title=f"Queue · {len(songs)} songs", color=discord.Color.blurple()
        )
        lines = []
        for position, song in enumerate(visible, self.page * PAGE_SIZE + 1):
            title = discord.utils.escape_markdown(song.title[:100])
            requester = discord.utils.escape_markdown(song.requested_by_name[:40])
            lines.append(
                f"**{position}. {title}** · {format_duration(song.duration)}\n{requester} · {wait_label(self.guild_id, song.entry_id)}"
            )
        embed.description = (
            "\n\n".join(lines) or "Queue is empty. Add a song with /play."
        )
        if player.current_song:
            embed.add_field(
                name=player.phase.capitalize(),
                value=player.current_song.title[:200],
                inline=False,
            )
        if player.autoplay_enabled:
            upcoming = (
                "\n".join(song.title[:100] for song in player.autoplay_queue)
                or "Finding recommendations…"
            )
            embed.add_field(
                name="Autoplay follows your queue", value=upcoming[:1024], inline=False
            )
        if self.note:
            embed.add_field(name="Queue update", value=self.note[:1024], inline=False)
        embed.set_footer(
            text=f"Page {self.page + 1}/{pages} · Waiting times are estimates"
        )
        self.select_song.options = [
            discord.SelectOption(
                label=song.title[:100],
                value=song.entry_id,
                description=f"#{i} · {song.requested_by_name}"[:100],
                default=song.entry_id == self.selected,
            )
            for i, song in enumerate(visible, self.page * PAGE_SIZE + 1)
        ] or [discord.SelectOption(label="Queue is empty", value="empty")]
        self.select_song.disabled = not visible
        self.previous.disabled = self.page == 0
        self.next_page.disabled = self.page == pages - 1
        selected_exists = any(song.entry_id == self.selected for song in songs)
        self.remove_song.disabled = not selected_exists
        self.play_next.disabled = not selected_exists
        self.move_song.disabled = not selected_exists
        return embed

    async def refresh(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(embed=self.render(), view=self)

    @discord.ui.select(placeholder="Select a song to move or remove", row=0)
    async def select_song(
        self, interaction: discord.Interaction, select: discord.ui.Select
    ) -> None:
        self.selected = select.values[0]
        await self.refresh(interaction)

    @discord.ui.button(label="Previous", row=1)
    async def previous(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.page = max(0, self.page - 1)
        await self.refresh(interaction)

    @discord.ui.button(label="Next", row=1)
    async def next_page(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.page += 1
        await self.refresh(interaction)

    @discord.ui.button(label="Refresh", row=1)
    async def refresh_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.refresh(interaction)

    async def edit_selected(
        self, interaction: discord.Interaction, move_to: int | None = None
    ) -> None:
        player = player_manager.get_player(self.guild_id)
        if not await ensure_same_voice(interaction, player.voice_client):
            return
        song = await player_manager.edit_queue_entry(
            self.guild_id, self.selected or "", move_to=move_to
        )
        self.note = (
            (f"Moved {song.title}." if move_to else f"Removed {song.title}.")
            if song
            else "That song already left the queue. Select another song."
        )
        self.selected = None
        await self.refresh(interaction)

    @discord.ui.button(label="Play next", style=discord.ButtonStyle.primary, row=2)
    async def play_next(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.edit_selected(interaction, move_to=1)

    @discord.ui.button(label="Move…", row=2)
    async def move_song(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.send_modal(MoveSongModal(self))

    @discord.ui.button(label="Remove", style=discord.ButtonStyle.danger, row=2)
    async def remove_song(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.edit_selected(interaction)


class MoveSongModal(discord.ui.Modal, title="Move selected song"):
    position = discord.ui.TextInput(
        label="New queue position", max_length=3, placeholder="1"
    )

    def __init__(self, queue: QueueView) -> None:
        super().__init__()
        self.queue = queue
        self.entry_id = queue.selected

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not self.position.value.isdecimal() or int(self.position.value) < 1:
            await respond(interaction, "Enter a queue position starting at 1.")
            return
        # Preserve the selection made when this modal was opened.
        self.queue.selected = self.entry_id
        await self.queue.edit_selected(interaction, move_to=int(self.position.value))

    async def on_error(
        self, interaction: discord.Interaction, error: Exception
    ) -> None:
        await respond(
            interaction, "Could not move that song. Open /queue and try again."
        )


async def show_queue(interaction: discord.Interaction) -> None:
    if not interaction.guild_id:
        await respond(interaction, "Use /queue in a server.")
        return
    view = QueueView(interaction.guild_id, interaction.user.id)
    await interaction.response.send_message(
        embed=view.render(), view=view, ephemeral=True
    )
    view.message = await interaction.original_response()
