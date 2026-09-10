"""Cancellable song requests and incremental playlist imports."""

import asyncio
import logging
import re
from time import monotonic

import discord

from autoplay import YouTubeMusicHandler
from music_player import MAX_QUEUE_LENGTH, player_manager
from youtube import (
    SongInfo,
    extract_playlist,
    extract_song_info,
    is_playlist_url,
    search_youtube,
    single_video_url,
)
from .helpers import MusicView, ensure_same_voice, respond
from .player_view import panels
from .queue_view import wait_label

logger = logging.getLogger(__name__)
ytmusic = YouTubeMusicHandler()


class RequestChoice(discord.ui.Select):
    async def callback(self, interaction: discord.Interaction) -> None:
        self.view.choice = self.values[0]
        await interaction.response.defer()
        self.view.stop()


class ChoiceView(MusicView):
    def __init__(self, user_id: int, options: list[discord.SelectOption]) -> None:
        super().__init__(timeout=45)
        self.user_id = user_id
        self.choice: str | None = None
        self.cancelled = False
        self.add_item(
            RequestChoice(placeholder="Choose an option", options=options, row=0)
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await respond(
                interaction,
                "This is someone else's request. Use /play to make your own.",
            )
            return False
        return True

    async def on_timeout(self) -> None:
        # The waiting request replaces this menu with an explanation.
        pass

    @discord.ui.button(label="Cancel", row=1)
    async def cancel(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.cancelled = True
        await interaction.response.defer()
        self.stop()


class CancelRequestView(MusicView):
    def __init__(self, request: "MusicRequest") -> None:
        super().__init__(timeout=None)
        self.request = request

    @discord.ui.button(label="Cancel request", style=discord.ButtonStyle.secondary)
    async def cancel(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if interaction.user.id != self.request.interaction.user.id:
            await respond(
                interaction,
                "Only the requester can cancel this import. Use Stop to end the listening session.",
            )
            return
        await interaction.response.defer()
        if self.request.task:
            self.request.task.cancel()


class MusicRequest:
    def __init__(
        self,
        interaction: discord.Interaction,
        message: discord.Message,
        query: str,
        source: str,
    ) -> None:
        self.interaction = interaction
        self.message = message
        self.query = query.strip()
        self.source = source
        self.player = player_manager.get_player(interaction.guild_id)
        self.session_id = self.player.session_id
        self.task: asyncio.Task | None = None
        self.view: MusicView | None = None
        self.added = 0
        self.unavailable = 0
        self.remaining = 0
        self.player_url: str | None = None

    async def update(self, content: str, view: MusicView | None = None) -> None:
        if self.view and self.view is not view:
            self.view.stop()
        self.view = view
        await self.message.edit(
            content=content, view=view, allowed_mentions=discord.AllowedMentions.none()
        )
        if view:
            view.message = self.message

    async def choose(self, prompt: str, options: list[discord.SelectOption]) -> str:
        view = ChoiceView(self.interaction.user.id, options)
        await self.update(prompt, view)
        await view.wait()
        if view.cancelled:
            raise asyncio.CancelledError
        if view.choice is None:
            raise ValueError("Selection expired. Use /play to search again.")
        return view.choice

    def check_session(self) -> None:
        if self.player.session_id != self.session_id:
            raise asyncio.CancelledError

    async def connect(self) -> None:
        self.check_session()
        if not await ensure_same_voice(self.interaction, self.player.voice_client):
            raise ValueError(
                "Request cancelled because you left the listening channel."
            )
        channel = self.interaction.user.voice.channel
        permissions = channel.permissions_for(self.interaction.guild.me)
        if not permissions.connect or not permissions.speak:
            raise ValueError(
                f"I need Connect and Speak permissions in <#{channel.id}> to play music."
            )
        await player_manager.connect(self.interaction.guild_id, channel)
        self.check_session()
        message = await panels.ensure(self.interaction)
        self.player_url = message.jump_url

    async def resolve_song(self, query: str) -> SongInfo | None:
        if query.startswith("yt:") and re.fullmatch(r"[A-Za-z0-9_-]{11}", query[3:]):
            return await extract_song_info(query[3:])
        if query.startswith(("https://", "http://")):
            return await extract_song_info(single_video_url(query) or query)
        try:
            results = await asyncio.wait_for(
                ytmusic.search_songs_async(query, limit=5), timeout=8
            )
        except asyncio.TimeoutError:
            results = []
        if not results:
            return await search_youtube(query)
        selected = await self.choose(
            "Choose the song you want to hear:",
            [
                discord.SelectOption(
                    label=f"{song['title']} — {song['artist']}"[:100],
                    value=song["videoId"],
                    description=(song.get("duration") or "YouTube Music")[:100],
                )
                for song in results
            ],
        )
        await self.update("Preparing your selected song…", CancelRequestView(self))
        return await extract_song_info(selected)

    async def enqueue(self, song: SongInfo, source: str) -> int:
        self.check_session()
        return await player_manager.add_to_queue(
            self.interaction.guild_id,
            song,
            requester_id=self.interaction.user.id,
            requester_name=self.interaction.user.display_name,
            guild_name=self.interaction.guild.name,
            source_type=source,
        )

    async def import_playlist(self) -> None:
        # Use a normal message so long imports can update after interaction tokens expire.
        progress = await self.interaction.channel.send(
            "Loading playlist…", allowed_mentions=discord.AllowedMentions.none()
        )
        await self.update(f"[Playlist progress]({progress.jump_url})")
        self.message = progress
        await self.update("Loading playlist…", CancelRequestView(self))
        entries = await extract_playlist(self.query)
        if not entries:
            raise ValueError(
                "Could not load this playlist. Check that it is public, or try a song URL."
            )
        await self.connect()
        last_update = 0.0
        for index, entry in enumerate(entries):
            self.check_session()
            if len(self.player.queue) >= MAX_QUEUE_LENGTH:
                self.remaining = len(entries) - index
                break
            song = await extract_song_info(entry["video_id"])
            self.check_session()
            if not song:
                self.unavailable += 1
            elif await self.enqueue(song, "playlist") < 0:
                self.remaining = len(entries) - index
                break
            else:
                self.added += 1
                player_manager.start_playback(self.interaction.guild_id)
            if monotonic() - last_update >= 2:
                await self.update(
                    f"Playlist: {self.added} songs added · {self.unavailable} unavailable · loading more…",
                    self.view,
                )
                last_update = monotonic()
        await self.update(
            f"Playlist ready: **{self.added}** songs added · **{self.unavailable}** unavailable · **{self.remaining}** not added (queue full)."
        )

    async def request_song(self) -> None:
        song = await self.resolve_song(self.query)
        self.check_session()
        if song is None:
            raise ValueError(
                "Could not play that song. Try a different search result or a public YouTube URL."
            )
        await self.connect()
        position = await self.enqueue(song, self.source)
        if position < 0:
            raise ValueError(
                "Queue is full. Remove a song with /queue, then try again."
            )
        self.added = 1
        if player_manager.is_playing(self.interaction.guild_id):
            confirmation = f"Added **{discord.utils.escape_markdown(song.title[:200])}** · #{position} · {wait_label(self.interaction.guild_id, song.entry_id)}"
        else:
            confirmation = f"Preparing **{discord.utils.escape_markdown(song.title[:200])}**. Use the player to cancel or skip."
        player_manager.start_playback(self.interaction.guild_id)
        if self.player_url:
            confirmation += f"\n[Open the player]({self.player_url})"
        await self.update(confirmation)

    async def run(self) -> None:
        try:
            await self.update("Finding your music…", CancelRequestView(self))
            if is_playlist_url(self.query):
                video_url = single_video_url(self.query)
                choice = "playlist"
                if video_url:
                    choice = await self.choose(
                        "This link includes a song and a playlist. What would you like to play?",
                        [
                            discord.SelectOption(label="This song", value="song"),
                            discord.SelectOption(
                                label="Entire playlist", value="playlist"
                            ),
                        ],
                    )
                if choice == "playlist":
                    await self.import_playlist()
                    return
                self.query = video_url
                await self.update("Preparing this song…", CancelRequestView(self))
            await self.request_song()
        except asyncio.CancelledError:
            await self.finish(f"Request cancelled after adding {self.added} song(s).")
        except ValueError as error:
            await self.finish(str(error))
        except (discord.Forbidden, asyncio.TimeoutError):
            await self.finish(
                "Could not connect or show the player. Check my voice and text channel permissions, then try /play again."
            )
        except Exception:
            logger.exception("Music request failed")
            await self.finish(
                "This request could not complete. Try /play again or choose another song."
            )
        finally:
            if self.view:
                self.view.stop()
            self.player._request_tasks.discard(asyncio.current_task())
            if self.player.voice_client and not self.player._request_tasks:
                player_manager.start_playback(self.interaction.guild_id)

    async def finish(self, message: str) -> None:
        try:
            await self.update(message)
        except discord.HTTPException:
            logger.warning("Could not update music request", exc_info=True)


async def request_play(
    interaction: discord.Interaction, query: str, *, source: str = "search"
) -> None:
    player = player_manager.get_player(interaction.guild_id)
    if not await ensure_same_voice(interaction, player.voice_client):
        return
    if not query.strip():
        await respond(interaction, "Enter a song name or a YouTube URL.")
        return
    if not interaction.response.is_done():
        await interaction.response.defer(ephemeral=True)
    message = await interaction.edit_original_response(content="Finding your music…")
    request = MusicRequest(interaction, message, query, source)
    request.task = asyncio.create_task(request.run())
    player._request_tasks.add(request.task)
    try:
        await request.task
    except asyncio.CancelledError:
        await request.finish("Request cancelled.")
    finally:
        player._request_tasks.discard(request.task)
