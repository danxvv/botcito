"""Music player with queue management, autoplay, and auto-disconnect."""

import asyncio
import logging
import random
import subprocess
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field

import discord

from audit.logger import AuditLogger
from audio_cache import audio_cache
from autoplay import YouTubeMusicHandler
from ratings import get_guild_ratings
from youtube import SongInfo, extract_song_info


# Number of recent songs to track for blended recommendations
RECENT_SONGS_LIMIT = 3
logger = logging.getLogger(__name__)


@dataclass
class GuildPlayer:
    """Music player state for a single guild."""

    voice_client: discord.VoiceClient | None = None
    queue: deque[SongInfo] = field(default_factory=deque)
    current_song: SongInfo | None = None
    guild_name: str = "Unknown"
    autoplay_enabled: bool = False
    is_starting: bool = False
    start_token: int = 0
    stopping: bool = False
    song_start_time: float | None = None
    paused_at: float | None = None
    total_paused_time: float = 0.0
    ytmusic: YouTubeMusicHandler = field(default_factory=YouTubeMusicHandler)
    autoplay_queue: deque[SongInfo] = field(default_factory=deque)  # Pre-fetched autoplay songs
    recent_songs: deque[str] = field(default_factory=deque)  # Recent video IDs for blended recommendations
    volume: float = 1.0  # Volume level (0.0 to 1.0)
    _disconnect_task: asyncio.Task | None = field(default=None, repr=False)
    _prefetch_task: asyncio.Task | None = field(default=None, repr=False)
    session_id: int = 0
    notice: str = ""
    phase: str = "idle"
    _play_task: asyncio.Task | None = field(default=None, repr=False)
    _request_tasks: set[asyncio.Task] = field(default_factory=set, repr=False)
    _connect_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)


# FFmpeg options for reconnecting on network issues
# Include User-Agent header to avoid 403 errors from YouTube

def _get_ffmpeg_before_options() -> str:
    """Build FFmpeg before_options with cookies if available."""
    base_opts = (
        "-rw_timeout 15000000 -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 "
        "-reconnect_on_network_error 1 -reconnect_on_http_error 4xx,5xx "
        '-headers "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36\r\n"'
    )
    return base_opts

FFMPEG_BEFORE_OPTIONS = _get_ffmpeg_before_options()
# Output options for audio conversion
FFMPEG_OPTIONS = "-vn -bufsize 64k"

# Auto-disconnect timeout in seconds
DISCONNECT_TIMEOUT = 300  # 5 minutes

# Number of autoplay songs to keep pre-fetched
AUTOPLAY_PREFETCH_COUNT = 3

# Keep queues bounded so large playlists cannot exhaust memory.
MAX_QUEUE_LENGTH = 200


def _cancel_task(task: asyncio.Task | None) -> None:
    """Cancel a task if it exists and is not done."""
    if task and not task.done():
        task.cancel()


class MusicPlayerManager:
    """Manages music players for all guilds."""

    def __init__(self) -> None:
        self.players: dict[int, GuildPlayer] = {}
        self.on_change: Callable[[int], None] | None = None

    def changed(self, guild_id: int) -> None:
        if self.on_change:
            self.on_change(guild_id)

    def cancel_requests(self, guild_id: int) -> None:
        for task in tuple(self.get_player(guild_id)._request_tasks):
            _cancel_task(task)

    def start_playback(self, guild_id: int) -> None:
        player = self.get_player(guild_id)
        if self.is_playing(guild_id) or (player._play_task and not player._play_task.done()):
            return
        player._play_task = asyncio.create_task(self.play_next(guild_id))

    def get_player(self, guild_id: int) -> GuildPlayer:
        """Get or create a player for a guild."""
        if guild_id not in self.players:
            self.players[guild_id] = GuildPlayer()
        return self.players[guild_id]

    async def connect(
        self, guild_id: int, channel: discord.VoiceChannel
    ) -> discord.VoiceClient:
        """Connect to a voice channel for music playback."""
        player = self.get_player(guild_id)
        async with player._connect_lock:
            if player.voice_client and player.voice_client.is_connected():
                if player.voice_client.channel.id != channel.id:
                    raise ValueError(f"Music is already in <#{player.voice_client.channel.id}>. Join that channel first.")
                return player.voice_client
            player.guild_name = channel.guild.name
            player.stopping = False
            player.phase = "idle"
            player.notice = ""
            try:
                player.voice_client = await channel.connect(timeout=15, reconnect=True)
            except (asyncio.CancelledError, asyncio.TimeoutError, discord.DiscordException, OSError):
                partial = getattr(channel.guild, "voice_client", None)
                if partial:
                    await partial.disconnect(force=True)
                raise
            self.changed(guild_id)
            return player.voice_client

    async def disconnect(self, guild_id: int) -> None:
        player = self.get_player(guild_id)
        player.stopping = True
        self.cancel_requests(guild_id)
        async with player._connect_lock:
            voice_client = player.voice_client
            await self.cleanup_external_disconnect(guild_id)
            if voice_client:
                source = voice_client.source
                voice_client.stop()
                if source:
                    await asyncio.to_thread(source.cleanup)
                if voice_client.is_connected():
                    await voice_client.disconnect()

    async def cleanup_external_disconnect(self, guild_id: int) -> None:
        player = self.get_player(guild_id)
        player.stopping = True
        player.session_id += 1
        player.start_token += 1
        self.cancel_requests(guild_id)
        _cancel_task(player._play_task)
        self._cancel_disconnect_timer(player)
        await self._cancel_prefetch(player)
        songs = [s for s in [player.current_song, *player.queue, *player.autoplay_queue] if s]
        player.voice_client = None
        player.queue.clear()
        player.autoplay_queue.clear()
        player.current_song = None
        player.recent_songs.clear()
        player.song_start_time = None
        player.paused_at = None
        player.total_paused_time = 0.0
        player.is_starting = False
        player.phase = "disconnected"
        player.notice = "Session ended. Use /play to start listening again."
        player.ytmusic.clear_history()
        for song in songs:
            audio_cache.release(song)
        self.changed(guild_id)

    async def add_to_queue(
        self,
        guild_id: int,
        song: SongInfo,
        *,
        requester_id: int = 0,
        requester_name: str = "Autoplay",
        guild_name: str = "Unknown",
        source_type: str = "search",
    ) -> int:
        """Add a song to the queue. Returns queue position."""
        player = self.get_player(guild_id)
        async with player._lock:
            if len(player.queue) >= MAX_QUEUE_LENGTH:
                return -1
            song.requested_by_id = requester_id
            song.requested_by_name = requester_name
            song.guild_name = guild_name
            song.source_type = source_type
            player.queue.append(song)
            audio_cache.retain(song)
            self._prefetch_next_audio(player)
            self.changed(guild_id)
            return len(player.queue)

    def _get_next_song(self, guild_id: int, player: GuildPlayer) -> SongInfo | None:
        """Get next song from queue or pre-fetched autoplay."""
        if player.queue:
            return player.queue.popleft()

        if player.autoplay_enabled and player.autoplay_queue:
            return player.autoplay_queue.popleft()

        return None

    def _set_current_song(self, player: GuildPlayer, song: SongInfo) -> None:
        """Update current song bookkeeping."""
        player.current_song = song
        player.song_start_time = None
        player.paused_at = None
        player.total_paused_time = 0.0
        player.ytmusic.mark_played(song.video_id)

        if song.video_id not in player.recent_songs:
            player.recent_songs.append(song.video_id)
            while len(player.recent_songs) > RECENT_SONGS_LIMIT:
                player.recent_songs.popleft()

    def _log_play(self, guild_id: int, song: SongInfo) -> None:
        """Write a play event after playback successfully starts."""
        asyncio.create_task(
            asyncio.to_thread(
                AuditLogger.log_music,
                guild_id,
                song.guild_name,
                song.requested_by_id,
                song.requested_by_name,
                song.video_id,
                song.title,
                song.duration,
                song.source_type,
                "play",
            )
        )

    async def _create_audio_source(
        self, song: SongInfo, player: GuildPlayer, *, retry: bool = False
    ) -> discord.PCMVolumeTransformer:
        audio_cache.protect(song)
        downloaded = await audio_cache.ensure_downloaded(song)
        if downloaded:
            audio_source = song.local_path
        else:
            if retry or time.monotonic() - song.extracted_at > 300:
                fresh = await extract_song_info(song.webpage_url)
                if not fresh:
                    raise ValueError("Could not refresh this song.")
                song.url = fresh.url
                song.extracted_at = fresh.extracted_at
            if not song.url.startswith("http"):
                raise ValueError("No playable audio URL.")
            audio_source = song.url
        source = discord.FFmpegPCMAudio(
            audio_source,
            before_options=FFMPEG_BEFORE_OPTIONS if audio_source.startswith("http") else None,
            options=FFMPEG_OPTIONS,
            stderr=subprocess.DEVNULL,
        )
        return discord.PCMVolumeTransformer(source, volume=player.volume)

    async def _play_song(self, guild_id: int, song: SongInfo, token: int, retry: bool) -> bool:
        player = self.get_player(guild_id)
        source = None
        try:
            source = await self._create_audio_source(song, player, retry=retry)
            if player.start_token != token or not player.voice_client:
                return False
            loop = asyncio.get_running_loop()

            def after(error: Exception | None) -> None:
                asyncio.run_coroutine_threadsafe(
                    self._after_playback(guild_id, song, token, retry, error), loop
                )

            player.voice_client.play(source, after=after)
            source = None  # The voice client now owns cleanup.
            player.song_start_time = time.time()
            player.is_starting = False
            player.phase = "playing"
            if retry:
                player.notice = f"Playback recovered for {song.title[:150]}."
            if player.autoplay_enabled:
                self._start_prefetch(guild_id, player)
            self._prefetch_next_audio(player)
            self.changed(guild_id)
            return True
        finally:
            if source:
                source.cleanup()

    async def _after_playback(
        self, guild_id: int, song: SongInfo, token: int, retried: bool,
        error: Exception | None,
    ) -> None:
        player = self.get_player(guild_id)
        if player.start_token != token or player.stopping:
            return
        elapsed = self.get_elapsed_seconds(guild_id) or 0
        ended_early = song.duration > 0 and elapsed + 5 < song.duration
        failed = error is not None or ended_early or song.is_live
        if failed and not retried:
            player.notice = f"Playback interrupted for {song.title[:150]}. Retrying once from the beginning…"
            self.changed(guild_id)
            player._play_task = asyncio.create_task(self.play_next(guild_id, retry_song=song))
            return
        if failed:
            player.notice = f"Could not play {song.title[:150]}. Skipped to the next song. Try /play again or choose another result."
            logger.warning("Playback failed for %s: %s", song.video_id, error or "audio ended early")
        audio_cache.release(song)
        player.current_song = None
        self.changed(guild_id)
        self.start_playback(guild_id)

    async def play_next(self, guild_id: int, *, retry_song: SongInfo | None = None) -> SongInfo | None:
        player = self.get_player(guild_id)
        if self.is_playing(guild_id):
            return player.current_song
        player._play_task = asyncio.current_task()
        player.is_starting = True
        player.start_token += 1
        token = player.start_token
        try:
            while player.voice_client and player.voice_client.is_connected() and not player.stopping:
                self._cancel_disconnect_timer(player)
                song = retry_song or self._get_next_song(guild_id, player)
                retry = retry_song is not None
                retry_song = None
                if not song and player.autoplay_enabled:
                    player.phase = "preparing"
                    self.changed(guild_id)
                    song = await self._get_autoplay_song(guild_id, player)
                if not song:
                    player.current_song = None
                    player.phase = "idle"
                    self._start_disconnect_timer(guild_id, player)
                    return None
                self._set_current_song(player, song)
                player.phase = "retrying" if retry else "preparing"
                self.changed(guild_id)
                for attempt in range(1 if retry else 2):
                    try:
                        if await self._play_song(guild_id, song, token, retry or attempt > 0):
                            if not retry:
                                self._log_play(guild_id, song)
                            return song
                        return None
                    except Exception:
                        logger.exception("Could not start %s", song.video_id)
                        player.phase = "retrying"
                        player.notice = f"Having trouble starting {song.title[:150]}. Retrying…"
                        self.changed(guild_id)
                player.notice = f"Could not play {song.title[:150]}. Skipping it; try another result with /play."
                audio_cache.release(song)
                player.current_song = None
        except asyncio.CancelledError:
            return None
        except Exception:
            logger.exception("Playback failed in server %s", guild_id)
            player.notice = "Playback could not continue. Use /play to try again."
            if player.current_song:
                audio_cache.release(player.current_song)
            player.current_song = None
            player.phase = "idle"
            self._start_disconnect_timer(guild_id, player)
        finally:
            if player.start_token == token:
                player.is_starting = False
                self.changed(guild_id)

    def _prefetch_next_audio(self, player: GuildPlayer) -> None:
        """Start background download for next songs in queue."""
        # Prefetch from regular queue first
        for i, next_song in enumerate(player.queue):
            if i >= 2:  # Only prefetch first 2
                break
            if not audio_cache.is_ready(next_song.video_id):
                audio_cache.start_background_download(next_song)

        # Then from autoplay queue
        for i, next_song in enumerate(player.autoplay_queue):
            if i >= 1:  # Only prefetch 1 from autoplay
                break
            if not audio_cache.is_ready(next_song.video_id):
                audio_cache.start_background_download(next_song)

    async def _get_autoplay_song(self, guild_id: int, player: GuildPlayer) -> SongInfo | None:
        """Fetch a single song from autoplay recommendations (fallback)."""
        if not player.recent_songs:
            return None
        if player._prefetch_task and not player._prefetch_task.done():
            await asyncio.wait({player._prefetch_task})
        if not player.autoplay_enabled:
            return None
        if player.autoplay_queue:
            return player.autoplay_queue.popleft()

        # Use blended recommendations from recent songs
        recommendations = await self._get_blended_recommendations(guild_id, player, limit=5)

        for rec in recommendations:
            song = await extract_song_info(rec["videoId"])
            if song:
                song.guild_name = player.guild_name
                song.source_type = "autoplay"
                return song

        return None

    def _start_prefetch(self, guild_id: int, player: GuildPlayer) -> None:
        """Start background task to pre-fetch autoplay songs."""
        # Don't start if already prefetching or have enough songs
        if player._prefetch_task and not player._prefetch_task.done():
            return
        if len(player.autoplay_queue) >= AUTOPLAY_PREFETCH_COUNT:
            return

        if player.voice_client and player.voice_client.loop:
            async def prefetch() -> None:
                try:
                    await self._prefetch_autoplay(guild_id, player, count=AUTOPLAY_PREFETCH_COUNT)
                except Exception:
                    logger.exception("Could not prepare autoplay recommendations")
                    player.notice = "Could not prepare recommendations. Your queued music will continue; add more with /play."
                    self.changed(guild_id)
            player._prefetch_task = asyncio.create_task(prefetch())

    async def _cancel_prefetch(self, player: GuildPlayer) -> None:
        """Cancel any running prefetch task."""
        _cancel_task(player._prefetch_task)
        if player._prefetch_task:
            try:
                await player._prefetch_task
            except asyncio.CancelledError:
                pass
            player._prefetch_task = None

    async def _get_blended_recommendations(
        self, guild_id: int, player: GuildPlayer, limit: int
    ) -> list[dict]:
        """Get blended recommendations from recent songs, sorted by guild ratings."""
        if not player.recent_songs:
            return []

        all_recs: list[dict] = []
        seen_ids: set[str] = set()

        # Get recommendations from each recent song (most recent first)
        per_song_limit = max(limit // len(player.recent_songs), 2)
        for video_id in reversed(list(player.recent_songs)):
            recs = await player.ytmusic.get_recommendations_async(
                video_id, limit=per_song_limit + 2
            )
            for rec in recs:
                if rec["videoId"] not in seen_ids:
                    seen_ids.add(rec["videoId"])
                    all_recs.append(rec)

        # Sort by guild ratings: positive first, neutral middle, heavily disliked last
        ratings = await asyncio.to_thread(get_guild_ratings, guild_id)

        # Thresholds: positive (>0) = group 0, neutral (0) = 1, disliked (-1) = 2, heavily disliked (<=-2) = 3
        _GROUP_THRESHOLDS = [(1, 0), (0, 1), (-1, 2)]

        def rating_sort_key(rec: dict) -> tuple[int, int]:
            score = ratings.get(rec["videoId"], 0)
            group = next((g for threshold, g in _GROUP_THRESHOLDS if score >= threshold), 3)
            return (group, -score)

        all_recs.sort(key=rating_sort_key)
        return all_recs[:limit]

    async def _prefetch_autoplay(
        self, guild_id: int, player: GuildPlayer, count: int = AUTOPLAY_PREFETCH_COUNT
    ) -> None:
        """Pre-fetch autoplay songs into the autoplay queue."""
        if not player.recent_songs:
            return

        # Get blended recommendations from recent songs (sorted by ratings)
        recommendations = await self._get_blended_recommendations(
            guild_id, player, limit=count + 2  # Get extra in case some fail
        )

        for rec in recommendations:
            if len(player.autoplay_queue) >= count:
                break
            # Skip if already in autoplay queue (check under lock)
            async with player._lock:
                queued = [*player.queue, *player.autoplay_queue]
                if player.current_song:
                    queued.append(player.current_song)
                if any(s.video_id == rec["videoId"] for s in queued):
                    continue

            song = await extract_song_info(rec["videoId"])
            if song:
                song.guild_name = player.guild_name
                song.source_type = "autoplay"
                async with player._lock:
                    queued_ids = {s.video_id for s in [*player.queue, *player.autoplay_queue]}
                    if player.current_song:
                        queued_ids.add(player.current_song.video_id)
                    if not player.stopping and player.voice_client and player.autoplay_enabled and song.video_id not in queued_ids:
                        player.autoplay_queue.append(song)
                        audio_cache.retain(song)
                        self._prefetch_next_audio(player)
                        self.changed(guild_id)

    def _start_disconnect_timer(self, guild_id: int, player: GuildPlayer) -> None:
        """Start the auto-disconnect timer."""
        _cancel_task(player._disconnect_task)
        player._disconnect_task = None

        if player.voice_client:
            async def disconnect_after_timeout():
                await asyncio.sleep(DISCONNECT_TIMEOUT)
                player._disconnect_task = None
                await self.disconnect(guild_id)

            player._disconnect_task = asyncio.create_task(disconnect_after_timeout())

    def _cancel_disconnect_timer(self, player: GuildPlayer) -> None:
        """Cancel the auto-disconnect timer."""
        if player._disconnect_task is not asyncio.current_task():
            _cancel_task(player._disconnect_task)
        player._disconnect_task = None

    def skip(self, guild_id: int) -> bool:
        player = self.get_player(guild_id)
        song = player.current_song
        if not song and not player.is_starting:
            return False
        player.start_token += 1  # Ignore completion from the discarded source.
        _cancel_task(player._play_task)
        player._play_task = None
        if player.voice_client:
            source = player.voice_client.source
            player.voice_client.stop()
            if source:
                asyncio.create_task(asyncio.to_thread(source.cleanup))
        if song:
            audio_cache.release(song)
        player.current_song = None
        player.is_starting = False
        player.notice = f"Skipped {song.title[:150]}." if song else "Cancelled preparation."
        self.changed(guild_id)
        self.start_playback(guild_id)
        return True

    def pause(self, guild_id: int) -> bool:
        """Pause playback. Returns True if paused."""
        player = self.get_player(guild_id)
        if player.voice_client and player.voice_client.is_playing():
            player.voice_client.pause()
            player.paused_at = time.time()
            player.phase = "paused"
            self.changed(guild_id)
            return True
        return False

    def resume(self, guild_id: int) -> bool:
        """Resume playback. Returns True if resumed."""
        player = self.get_player(guild_id)
        if player.voice_client and player.voice_client.is_paused():
            player.voice_client.resume()
            if player.paused_at:
                player.total_paused_time += time.time() - player.paused_at
                player.paused_at = None
            player.phase = "playing"
            self.changed(guild_id)
            return True
        return False

    def toggle_autoplay(self, guild_id: int) -> bool:
        """Toggle autoplay mode. Returns new state."""
        player = self.get_player(guild_id)
        player.autoplay_enabled = not player.autoplay_enabled
        if player.autoplay_enabled:
            self._start_prefetch(guild_id, player)
        else:
            _cancel_task(player._prefetch_task)
            player._prefetch_task = None
            for song in player.autoplay_queue:
                audio_cache.release(song)
            player.autoplay_queue.clear()
        self.changed(guild_id)
        return player.autoplay_enabled

    def clear_history(self, guild_id: int) -> None:
        """Clear played history and recent songs, allowing songs to be recommended again."""
        player = self.get_player(guild_id)
        player.ytmusic.clear_history()
        player.recent_songs.clear()
        _cancel_task(player._prefetch_task)
        player._prefetch_task = None
        for song in player.autoplay_queue:
            audio_cache.release(song)
        player.autoplay_queue.clear()
        self.changed(guild_id)

    def refresh_autoplay(self, guild_id: int) -> bool:
        """Clear prefetched autoplay songs and fetch new ones if possible."""
        player = self.get_player(guild_id)
        _cancel_task(player._prefetch_task)
        player._prefetch_task = None
        for song in player.autoplay_queue:
            audio_cache.release(song)
        player.autoplay_queue.clear()
        self.changed(guild_id)
        if not player.autoplay_enabled or not player.current_song:
            return False
        self._start_prefetch(guild_id, player)
        return True

    def get_queue(self, guild_id: int) -> list[SongInfo]:
        """Get the current queue."""
        player = self.get_player(guild_id)
        return list(player.queue)

    async def shuffle_queue(self, guild_id: int) -> int:
        """Shuffle the queue. Returns count of shuffled songs."""
        player = self.get_player(guild_id)
        async with player._lock:
            if len(player.queue) < 2:
                return len(player.queue)
            queue_list = list(player.queue)
            random.shuffle(queue_list)
            player.queue = deque(queue_list)
            self._prefetch_next_audio(player)
            self.changed(guild_id)
            return len(player.queue)

    async def clear_queue(self, guild_id: int) -> int:
        """Clear queued songs without stopping the current track."""
        player = self.get_player(guild_id)
        self.cancel_requests(guild_id)
        async with player._lock:
            count = len(player.queue)
            songs = list(player.queue)
            player.queue.clear()

        for song in songs:
            audio_cache.release(song)
        self.changed(guild_id)
        return count

    async def remove_from_queue(self, guild_id: int, position: int) -> SongInfo | None:
        """Remove a queued song by 1-based position."""
        player = self.get_player(guild_id)
        async with player._lock:
            if position < 1 or position > len(player.queue):
                return None
            songs = list(player.queue)
            song = songs.pop(position - 1)
            player.queue = deque(songs)

        audio_cache.release(song)
        self._prefetch_next_audio(player)
        self.changed(guild_id)
        return song

    async def move_in_queue(
        self, guild_id: int, from_position: int, to_position: int
    ) -> tuple[SongInfo, int] | None:
        """Move a queued song and return it with its final 1-based position."""
        player = self.get_player(guild_id)
        async with player._lock:
            if from_position < 1 or from_position > len(player.queue) or to_position < 1:
                return None
            songs = list(player.queue)
            song = songs.pop(from_position - 1)
            to_position = min(to_position, len(songs) + 1)
            songs.insert(to_position - 1, song)
            player.queue = deque(songs)
            self._prefetch_next_audio(player)
            self.changed(guild_id)
            return song, to_position

    async def edit_queue_entry(self, guild_id: int, entry_id: str, *, move_to: int | None = None) -> SongInfo | None:
        """Edit the selected queue entry, even if its position changed."""
        player = self.get_player(guild_id)
        async with player._lock:
            song = next((song for song in player.queue if song.entry_id == entry_id), None)
            if song is None:
                return None
            player.queue.remove(song)
            if move_to is not None:
                player.queue.insert(max(0, min(move_to - 1, len(player.queue))), song)
            else:
                audio_cache.release(song)
            self._prefetch_next_audio(player)
            self.changed(guild_id)
            return song

    def queue_wait(self, guild_id: int, entry_id: str) -> int | None:
        player = self.get_player(guild_id)
        if self.is_paused(guild_id):
            return None
        current = player.current_song
        if current and (current.duration <= 0 or player.is_starting):
            return None
        wait = max(0, current.duration - (self.get_elapsed_seconds(guild_id) or 0)) if current else 0
        for song in player.queue:
            if song.entry_id == entry_id:
                return wait
            if song.duration <= 0:
                return None
            wait += song.duration
        return None

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
            player.is_starting
            or (
                player.voice_client
                and (player.voice_client.is_playing() or player.voice_client.is_paused())
            )
        )

    def get_elapsed_seconds(self, guild_id: int) -> int | None:
        """Get elapsed playback time in seconds, accounting for pauses."""
        player = self.get_player(guild_id)
        if not player.song_start_time or not player.current_song:
            return None

        if player.paused_at:
            # Currently paused - calculate time up to pause
            elapsed = player.paused_at - player.song_start_time - player.total_paused_time
        else:
            # Currently playing
            elapsed = time.time() - player.song_start_time - player.total_paused_time

        return max(0, int(elapsed))

    def is_paused(self, guild_id: int) -> bool:
        """Check if playback is paused."""
        player = self.get_player(guild_id)
        return bool(player.voice_client and player.voice_client.is_paused())

    # ============== Volume Methods ==============

    def set_volume(self, guild_id: int, volume: float) -> None:
        """
        Set playback volume for a guild.

        Args:
            guild_id: Discord guild ID
            volume: Volume level (0.0 to 1.0)
        """
        player = self.get_player(guild_id)
        player.volume = max(0.0, min(1.0, volume))

        # Apply to current source if playing
        if player.voice_client and player.voice_client.source:
            # PCMVolumeTransformer wraps the source
            if hasattr(player.voice_client.source, "volume"):
                player.voice_client.source.volume = player.volume
        self.changed(guild_id)

    def get_volume(self, guild_id: int) -> float:
        """Get current volume for a guild."""
        player = self.get_player(guild_id)
        return player.volume


# Global player manager instance
player_manager = MusicPlayerManager()
