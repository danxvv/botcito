"""Music player with queue management, autoplay, and auto-disconnect."""

import asyncio
from collections import deque
from dataclasses import dataclass, field

import discord

from autoplay import YouTubeMusicHandler
from youtube import SongInfo, extract_song_info


@dataclass
class GuildPlayer:
    """Music player state for a single guild."""

    voice_client: discord.VoiceClient | None = None
    queue: deque[SongInfo] = field(default_factory=deque)
    current_song: SongInfo | None = None
    autoplay_enabled: bool = False
    ytmusic: YouTubeMusicHandler = field(default_factory=YouTubeMusicHandler)
    _disconnect_task: asyncio.Task | None = field(default=None, repr=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    def __post_init__(self):
        # Ensure lock is created
        if self._lock is None:
            self._lock = asyncio.Lock()


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

        if player.voice_client:
            if player.voice_client.is_playing():
                player.voice_client.stop()
            await player.voice_client.disconnect()
            player.voice_client = None

        player.queue.clear()
        player.current_song = None
        player.ytmusic.clear_history()

    async def add_to_queue(self, guild_id: int, song: SongInfo) -> int:
        """Add a song to the queue. Returns queue position."""
        player = self.get_player(guild_id)
        player.queue.append(song)
        return len(player.queue)

    async def play_next(self, guild_id: int) -> SongInfo | None:
        """Play the next song in queue or fetch autoplay recommendation."""
        player = self.get_player(guild_id)

        async with player._lock:
            # Cancel any pending disconnect
            self._cancel_disconnect_timer(player)

            if not player.voice_client or not player.voice_client.is_connected():
                return None

            # Get next song from queue
            if player.queue:
                song = player.queue.popleft()
            elif player.autoplay_enabled and player.current_song:
                # Fetch autoplay recommendation
                song = await self._get_autoplay_song(player)
                if not song:
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

            return song

    async def _get_autoplay_song(self, player: GuildPlayer) -> SongInfo | None:
        """Fetch a song from autoplay recommendations."""
        if not player.current_song:
            return None

        recommendations = player.ytmusic.get_recommendations(
            player.current_song.video_id, limit=5
        )

        for rec in recommendations:
            song = await extract_song_info(rec["videoId"])
            if song:
                return song

        return None

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

    def get_queue(self, guild_id: int) -> list[SongInfo]:
        """Get the current queue."""
        player = self.get_player(guild_id)
        return list(player.queue)

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
