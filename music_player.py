"""Music player with queue management, autoplay, and auto-disconnect."""

import asyncio
from collections import deque
from dataclasses import dataclass, field

import discord

from autoplay import YouTubeMusicHandler
from youtube import SongInfo, extract_song_info


# Number of recent songs to track for blended recommendations
RECENT_SONGS_LIMIT = 3


@dataclass
class GuildPlayer:
    """Music player state for a single guild."""

    voice_client: discord.VoiceClient | None = None
    queue: deque[SongInfo] = field(default_factory=deque)
    current_song: SongInfo | None = None
    autoplay_enabled: bool = False
    ytmusic: YouTubeMusicHandler = field(default_factory=YouTubeMusicHandler)
    autoplay_queue: deque[SongInfo] = field(default_factory=deque)  # Pre-fetched autoplay songs
    recent_songs: deque[str] = field(default_factory=deque)  # Recent video IDs for blended recommendations
    _disconnect_task: asyncio.Task | None = field(default=None, repr=False)
    _prefetch_task: asyncio.Task | None = field(default=None, repr=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)


# FFmpeg options for reconnecting on network issues
FFMPEG_BEFORE_OPTIONS = (
    "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
)
FFMPEG_OPTIONS = "-vn"

# Auto-disconnect timeout in seconds
DISCONNECT_TIMEOUT = 300  # 5 minutes


class MusicPlayerManager:
    """Manages music players for all guilds."""

    def __init__(self):
        self.players: dict[int, GuildPlayer] = {}

    def get_player(self, guild_id: int) -> GuildPlayer:
        """Get or create a player for a guild."""
        if guild_id not in self.players:
            self.players[guild_id] = GuildPlayer()
        return self.players[guild_id]

    async def connect(
        self, guild_id: int, channel: discord.VoiceChannel
    ) -> discord.VoiceClient:
        """Connect to a voice channel."""
        player = self.get_player(guild_id)

        if player.voice_client and player.voice_client.is_connected():
            if player.voice_client.channel.id != channel.id:
                await player.voice_client.move_to(channel)
            return player.voice_client

        player.voice_client = await channel.connect()
        return player.voice_client

    async def disconnect(self, guild_id: int) -> None:
        """Disconnect from voice channel and clean up."""
        player = self.get_player(guild_id)
        self._cancel_disconnect_timer(player)
        await self._cancel_prefetch(player)

        if player.voice_client:
            if player.voice_client.is_playing():
                player.voice_client.stop()
            await player.voice_client.disconnect()
            player.voice_client = None

        player.queue.clear()
        player.autoplay_queue.clear()
        player.recent_songs.clear()
        player.current_song = None
        player.ytmusic.clear_history()

    async def add_to_queue(self, guild_id: int, song: SongInfo) -> int:
        """Add a song to the queue. Returns queue position."""
        player = self.get_player(guild_id)
        player.queue.append(song)
        return len(player.queue)

    async def play_next(self, guild_id: int) -> SongInfo | None:
        """Play the next song in queue or use pre-fetched autoplay."""
        player = self.get_player(guild_id)

        async with player._lock:
            # Cancel any pending disconnect
            self._cancel_disconnect_timer(player)

            if not player.voice_client or not player.voice_client.is_connected():
                return None

            # Get next song from queue
            if player.queue:
                song = player.queue.popleft()
            elif player.autoplay_enabled:
                # Use pre-fetched autoplay queue first
                if player.autoplay_queue:
                    song = player.autoplay_queue.popleft()
                elif player.current_song:
                    # Fallback: fetch one song on-demand if queue is empty
                    song = await self._get_autoplay_song(player)
                    if not song:
                        self._start_disconnect_timer(guild_id, player)
                        return None
                else:
                    player.current_song = None
                    self._start_disconnect_timer(guild_id, player)
                    return None
            else:
                # Nothing to play, start disconnect timer
                player.current_song = None
                self._start_disconnect_timer(guild_id, player)
                return None

            # Play the song
            player.current_song = song
            player.ytmusic.mark_played(song.video_id)

            # Track recent songs for blended recommendations
            if song.video_id not in player.recent_songs:
                player.recent_songs.append(song.video_id)
                while len(player.recent_songs) > RECENT_SONGS_LIMIT:
                    player.recent_songs.popleft()

            source = discord.FFmpegOpusAudio(
                song.url,
                before_options=FFMPEG_BEFORE_OPTIONS,
                options=FFMPEG_OPTIONS,
            )

            def after_callback(error):
                if error:
                    print(f"Playback error: {error}")
                # Schedule next song
                if player.voice_client and player.voice_client.loop:
                    asyncio.run_coroutine_threadsafe(
                        self.play_next(guild_id),
                        player.voice_client.loop,
                    )

            player.voice_client.play(
                source,
                after=after_callback,
                application="audio",
                bitrate=128,
                signal_type="music",
            )

            # Pre-fetch autoplay songs in background if autoplay is enabled
            if player.autoplay_enabled:
                self._start_prefetch(guild_id, player)

            return song

    async def _get_autoplay_song(self, player: GuildPlayer) -> SongInfo | None:
        """Fetch a single song from autoplay recommendations (fallback)."""
        if not player.recent_songs:
            return None

        # Use blended recommendations from recent songs
        recommendations = self._get_blended_recommendations(player, limit=5)

        for rec in recommendations:
            song = await extract_song_info(rec["videoId"])
            if song:
                return song

        return None

    def _start_prefetch(self, guild_id: int, player: GuildPlayer) -> None:
        """Start background task to pre-fetch autoplay songs."""
        # Don't start if already prefetching or have enough songs
        if player._prefetch_task and not player._prefetch_task.done():
            return
        if len(player.autoplay_queue) >= 3:
            return

        async def prefetch():
            await self._prefetch_autoplay(guild_id, player, count=3)

        if player.voice_client and player.voice_client.loop:
            loop = player.voice_client.loop
            player._prefetch_task = loop.create_task(prefetch())

    async def _cancel_prefetch(self, player: GuildPlayer) -> None:
        """Cancel any running prefetch task."""
        if player._prefetch_task:
            player._prefetch_task.cancel()
            try:
                await player._prefetch_task
            except asyncio.CancelledError:
                pass
            player._prefetch_task = None

    def _get_blended_recommendations(
        self, player: GuildPlayer, limit: int
    ) -> list[dict]:
        """Get blended recommendations from recent songs."""
        if not player.recent_songs:
            return []

        all_recs: list[dict] = []
        seen_ids: set[str] = set()

        # Get recommendations from each recent song (most recent first)
        per_song_limit = max(limit // len(player.recent_songs), 2)
        for video_id in reversed(player.recent_songs):
            recs = player.ytmusic.get_recommendations(video_id, limit=per_song_limit + 2)
            for rec in recs:
                if rec["videoId"] not in seen_ids:
                    seen_ids.add(rec["videoId"])
                    all_recs.append(rec)

        return all_recs[:limit]

    async def _prefetch_autoplay(
        self, guild_id: int, player: GuildPlayer, count: int = 3
    ) -> None:
        """Pre-fetch autoplay songs into the autoplay queue."""
        if not player.recent_songs:
            return

        # Get blended recommendations from recent songs
        recommendations = self._get_blended_recommendations(
            player, limit=count + 2  # Get extra in case some fail
        )

        fetched = 0
        for rec in recommendations:
            if fetched >= count:
                break
            # Skip if already in autoplay queue (check under lock)
            async with player._lock:
                if any(s.video_id == rec["videoId"] for s in player.autoplay_queue):
                    continue

            song = await extract_song_info(rec["videoId"])
            if song:
                async with player._lock:
                    player.autoplay_queue.append(song)
                fetched += 1

    def _start_disconnect_timer(self, guild_id: int, player: GuildPlayer) -> None:
        """Start the auto-disconnect timer."""
        self._cancel_disconnect_timer(player)

        async def disconnect_after_timeout():
            await asyncio.sleep(DISCONNECT_TIMEOUT)
            await self.disconnect(guild_id)

        if player.voice_client:
            player._disconnect_task = asyncio.create_task(disconnect_after_timeout())

    def _cancel_disconnect_timer(self, player: GuildPlayer) -> None:
        """Cancel the auto-disconnect timer."""
        if player._disconnect_task:
            player._disconnect_task.cancel()
            player._disconnect_task = None

    def skip(self, guild_id: int) -> bool:
        """Skip the current song. Returns True if something was playing."""
        player = self.get_player(guild_id)
        if player.voice_client and player.voice_client.is_playing():
            player.voice_client.stop()  # This triggers the after callback
            return True
        return False

    def pause(self, guild_id: int) -> bool:
        """Pause playback. Returns True if paused."""
        player = self.get_player(guild_id)
        if player.voice_client and player.voice_client.is_playing():
            player.voice_client.pause()
            return True
        return False

    def resume(self, guild_id: int) -> bool:
        """Resume playback. Returns True if resumed."""
        player = self.get_player(guild_id)
        if player.voice_client and player.voice_client.is_paused():
            player.voice_client.resume()
            return True
        return False

    def toggle_autoplay(self, guild_id: int) -> bool:
        """Toggle autoplay mode. Returns new state."""
        player = self.get_player(guild_id)
        player.autoplay_enabled = not player.autoplay_enabled
        return player.autoplay_enabled

    def clear_history(self, guild_id: int) -> None:
        """Clear played history and recent songs, allowing songs to be recommended again."""
        player = self.get_player(guild_id)
        player.ytmusic.clear_history()
        player.recent_songs.clear()
        player.autoplay_queue.clear()

    def get_queue(self, guild_id: int) -> list[SongInfo]:
        """Get the current queue."""
        player = self.get_player(guild_id)
        return list(player.queue)

    def get_autoplay_queue(self, guild_id: int) -> list[SongInfo]:
        """Get the pre-fetched autoplay queue."""
        player = self.get_player(guild_id)
        return list(player.autoplay_queue)

    def get_current_song(self, guild_id: int) -> SongInfo | None:
        """Get the currently playing song."""
        player = self.get_player(guild_id)
        return player.current_song

    def is_playing(self, guild_id: int) -> bool:
        """Check if music is currently playing."""
        player = self.get_player(guild_id)
        return bool(
            player.voice_client
            and (player.voice_client.is_playing() or player.voice_client.is_paused())
        )


# Global player manager instance
player_manager = MusicPlayerManager()
