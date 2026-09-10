"""A shared player card that follows the listening session."""

import asyncio
import logging
from dataclasses import dataclass, field

import discord

from music_player import player_manager
from ratings import get_rating_counts, rate_song
from .helpers import (
    MusicView,
    ensure_same_voice,
    format_duration,
    render_progress_bar,
    respond,
    _log_music_event,
)
from .queue_view import show_queue

logger = logging.getLogger(__name__)


class PlayerView(MusicView):
    def __init__(self, guild_id: int, entry_id: str | None) -> None:
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.entry_id = entry_id
        player = player_manager.get_player(guild_id)
        self.pause_resume.label = "Resume" if player.phase == "paused" else "Pause"
        self.pause_resume.disabled = player.phase not in {"playing", "paused"}
        self.skip_song.label = "Cancel song" if player.is_starting else "Skip"
        self.skip_song.disabled = not entry_id and not player.is_starting
        self.like.disabled = self.dislike.disabled = entry_id is None
        self.autoplay.label = f"Autoplay: {'On' if player.autoplay_enabled else 'Off'}"
        self.volume_down.disabled = player.volume <= 0
        self.volume_up.disabled = player.volume >= 1

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await ensure_same_voice(
            interaction, player_manager.get_player(self.guild_id).voice_client
        )

    async def current_matches(self, interaction: discord.Interaction) -> bool:
        song = player_manager.get_current_song(self.guild_id)
        if (
            song is None
            and self.entry_id is None
            and player_manager.get_player(self.guild_id).is_starting
        ):
            return True
        if not song or song.entry_id != self.entry_id:
            await respond(
                interaction, "The song changed. Use the updated player controls."
            )
            panels.changed(self.guild_id)
            return False
        return True

    @discord.ui.button(label="Pause", style=discord.ButtonStyle.primary, row=0)
    async def pause_resume(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if not await self.current_matches(interaction):
            return
        if player_manager.is_paused(self.guild_id):
            changed = player_manager.resume(self.guild_id)
            message = "Resumed."
        else:
            changed = player_manager.pause(self.guild_id)
            message = "Paused."
        await respond(
            interaction, message if changed else "The song is still preparing."
        )

    @discord.ui.button(label="Skip", row=0)
    async def skip_song(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if not await self.current_matches(interaction):
            return
        song = player_manager.get_current_song(self.guild_id)
        changed = player_manager.skip(self.guild_id)
        if changed and song:
            _log_music_event(interaction, song, "queue", "skip")
        await respond(interaction, "Skipped." if changed else "Nothing is playing.")

    @discord.ui.button(label="Queue", row=0)
    async def queue(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await show_queue(interaction)

    @discord.ui.button(label="Autoplay", row=0)
    async def autoplay(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        enabled = player_manager.toggle_autoplay(self.guild_id)
        await respond(interaction, f"Autoplay {'enabled' if enabled else 'disabled'}.")

    @discord.ui.button(label="Stop", style=discord.ButtonStyle.danger, row=0)
    async def stop_playback(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        song = player_manager.get_current_song(self.guild_id)
        if song:
            _log_music_event(interaction, song, "queue", "stop")
        await player_manager.disconnect(self.guild_id)
        await respond(
            interaction, "Stopped, cleared the queue, and cancelled pending requests."
        )

    @discord.ui.button(label="Volume −10%", row=1)
    async def volume_down(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        player_manager.set_volume(
            self.guild_id, player_manager.get_volume(self.guild_id) - 0.1
        )
        await respond(
            interaction, f"Volume: {player_manager.get_volume(self.guild_id):.0%}."
        )

    @discord.ui.button(label="Volume +10%", row=1)
    async def volume_up(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        player_manager.set_volume(
            self.guild_id, player_manager.get_volume(self.guild_id) + 0.1
        )
        await respond(
            interaction, f"Volume: {player_manager.get_volume(self.guild_id):.0%}."
        )

    async def rate(self, interaction: discord.Interaction, rating: int) -> None:
        if not await self.current_matches(interaction):
            return
        song = player_manager.get_current_song(self.guild_id)
        await interaction.response.defer(ephemeral=True)
        await asyncio.to_thread(
            rate_song,
            self.guild_id,
            song.video_id,
            interaction.user.id,
            rating,
            song.title,
        )
        panels.changed(self.guild_id)
        await respond(
            interaction, f"{'Liked' if rating == 1 else 'Disliked'} {song.title[:150]}."
        )

    @discord.ui.button(label="Like", style=discord.ButtonStyle.success, row=1)
    async def like(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.rate(interaction, 1)

    @discord.ui.button(label="Dislike", row=1)
    async def dislike(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.rate(interaction, -1)


async def render_player(guild_id: int) -> tuple[discord.Embed, PlayerView | None]:
    player = player_manager.get_player(guild_id)
    song = player.current_song
    labels = {
        "playing": "Now playing",
        "paused": "Paused",
        "preparing": "Preparing your music…",
        "retrying": "Retrying playback…",
        "idle": "Ready for your next song",
        "disconnected": "Session ended",
    }
    embed = discord.Embed(
        title=labels.get(player.phase, "Music player"), color=discord.Color.blurple()
    )
    view = (
        PlayerView(guild_id, song.entry_id if song else None)
        if player.voice_client
        else None
    )
    if song:
        embed.description = f"**{discord.utils.escape_markdown(song.title[:250])}**\n[Open on YouTube]({song.webpage_url})"
        elapsed = player_manager.get_elapsed_seconds(guild_id)
        if elapsed is not None:
            embed.add_field(
                name="Progress",
                value=f"`{render_progress_bar(elapsed, song.duration)}`",
                inline=False,
            )
        else:
            embed.add_field(name="Duration", value=format_duration(song.duration))
        embed.add_field(
            name="Requested by",
            value=discord.utils.escape_markdown(song.requested_by_name[:80]),
        )
        if song.thumbnail:
            embed.set_thumbnail(url=song.thumbnail)
    else:
        embed.description = "Choose a song with /play."
    next_song = next(iter(player.queue), None)
    if next_song is None and player.autoplay_enabled:
        next_song = next(iter(player.autoplay_queue), None)
    if next_song:
        embed.add_field(name="Up next", value=next_song.title[:250], inline=False)
    if player.notice:
        embed.add_field(name="Update", value=player.notice[:1024], inline=False)
    embed.set_footer(
        text=f"Volume {player.volume:.0%} · Autoplay {'On' if player.autoplay_enabled else 'Off'} · {len(player.queue)} queued"
    )
    if song:
        likes, dislikes = await asyncio.to_thread(
            get_rating_counts, guild_id, song.video_id
        )
        embed.add_field(name="Rating", value=f"{likes} likes · {dislikes} dislikes")
    return embed, view


@dataclass
class Panel:
    message: discord.Message
    view: PlayerView | None
    changed: asyncio.Event = field(default_factory=asyncio.Event)
    task: asyncio.Task | None = None


class PlayerPanels:
    def __init__(self) -> None:
        self.items: dict[int, Panel] = {}
        self._locks: dict[int, asyncio.Lock] = {}

    def changed(self, guild_id: int) -> None:
        panel = self.items.get(guild_id)
        if panel:
            panel.changed.set()

    async def ensure(self, interaction: discord.Interaction) -> discord.Message:
        guild_id = interaction.guild_id
        async with self._locks.setdefault(guild_id, asyncio.Lock()):
            panel = self.items.get(guild_id)
            if panel:
                try:
                    await panel.message.channel.fetch_message(panel.message.id)
                    panel.changed.set()
                    return panel.message
                except discord.NotFound:
                    if panel.task:
                        panel.task.cancel()
                    if panel.view:
                        panel.view.stop()
                    self.items.pop(guild_id, None)
            embed, view = await render_player(guild_id)
            message = await interaction.channel.send(
                embed=embed, view=view, allowed_mentions=discord.AllowedMentions.none()
            )
            panel = Panel(message, view)
            self.items[guild_id] = panel
            panel.task = asyncio.create_task(self._update(guild_id, panel))
            return message

    async def _update(self, guild_id: int, panel: Panel) -> None:
        try:
            while True:
                panel.changed.clear()
                # Coalesce queue imports and rapid button presses.
                await asyncio.sleep(0.5)
                embed, view = await render_player(guild_id)
                try:
                    await panel.message.edit(embed=embed, view=view)
                except (discord.NotFound, discord.Forbidden):
                    if view:
                        view.stop()
                    return
                except discord.HTTPException:
                    if view:
                        view.stop()
                    logger.warning("Could not refresh music player", exc_info=True)
                else:
                    if panel.view:
                        panel.view.stop()
                    panel.view = view
                if not player_manager.get_player(guild_id).voice_client:
                    return
                try:
                    await asyncio.wait_for(panel.changed.wait(), timeout=15)
                except asyncio.TimeoutError:
                    pass
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Player panel update failed")
        finally:
            if panel.view:
                panel.view.stop()
            if self.items.get(guild_id) is panel:
                self.items.pop(guild_id, None)

    async def close(self) -> None:
        for panel in list(self.items.values()):
            try:
                await panel.message.edit(view=None)
            except discord.HTTPException:
                pass
        tasks = [panel.task for panel in self.items.values() if panel.task]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


panels = PlayerPanels()
