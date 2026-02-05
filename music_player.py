"""Music player with queue management, autoplay, auto-disconnect, and recording."""

import asyncio
import random
import subprocess
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime

import discord
from discord.ext import voice_recv

from audio_cache import audio_cache
from autoplay import YouTubeMusicHandler
from ratings import get_guild_ratings
from voice_recorder import RecordingSession, WavAudioSink, save_recordings, get_recording_stats
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
    song_start_time: float | None = None
    paused_at: float | None = None
    total_paused_time: float = 0.0
    ytmusic: YouTubeMusicHandler = field(default_factory=YouTubeMusicHandler)
    autoplay_queue: deque[SongInfo] = field(default_factory=deque)  # Pre-fetched autoplay songs
    recent_songs: deque[str] = field(default_factory=deque)  # Recent video IDs for blended recommendations
    recording_session: RecordingSession | None = None
    audio_sink: WavAudioSink | None = None
    volume: float = 1.0  # Volume level (0.0 to 1.0)
    _disconnect_task: asyncio.Task | None = field(default=None, repr=False)
    _prefetch_task: asyncio.Task | None = field(default=None, repr=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)


# FFmpeg options for reconnecting on network issues
# Include User-Agent header to avoid 403 errors from YouTube

def _get_ffmpeg_before_options() -> str:
    """Build FFmpeg before_options with cookies if available."""
    base_opts = (
        "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 "
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


def _cancel_task(task: asyncio.Task | None) -> None:
    """Cancel a task if it exists and is not done."""
    if task and not task.done():
        task.cancel()


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
    ) -> voice_recv.VoiceRecvClient:
        """Connect to a voice channel using VoiceRecvClient for recording support."""
        player = self.get_player(guild_id)

        if player.voice_client and player.voice_client.is_connected():
            if player.voice_client.channel.id != channel.id:
                await player.voice_client.move_to(channel)
            return player.voice_client

        player.voice_client = await channel.connect(cls=voice_recv.VoiceRecvClient)
        return player.voice_client

    async def disconnect(self, guild_id: int) -> dict | None:
        """Disconnect from voice channel and clean up. Returns recording stats if was recording."""
        player = self.get_player(guild_id)
        self._cancel_disconnect_timer(player)
        await self._cancel_prefetch(player)

        # Save recording if active
        recording_result = None
        if player.recording_session and player.audio_sink:
            recording_result = await self.stop_recording(guild_id)

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

        # Clean up audio cache
        audio_cache.cleanup_all()

        return recording_result

    async def add_to_queue(self, guild_id: int, song: SongInfo) -> int:
        """Add a song to the queue. Returns queue position."""
        player = self.get_player(guild_id)
        player.queue.append(song)
        return len(player.queue)

    async def _get_next_song(self, guild_id: int, player: GuildPlayer) -> SongInfo | None:
        """Get next song from queue or autoplay. Starts disconnect timer if nothing available."""
        if player.queue:
            return player.queue.popleft()

        if player.autoplay_enabled:
            if player.autoplay_queue:
                return player.autoplay_queue.popleft()
            if player.current_song:
                song = await self._get_autoplay_song(guild_id, player)
                if song:
                    return song

        player.current_song = None
        self._start_disconnect_timer(guild_id, player)
        return None

    async def _create_audio_source(
        self, song: SongInfo, player: GuildPlayer, guild_id: int
    ) -> discord.PCMVolumeTransformer | None:
        """Create FFmpeg audio source from cached file or stream URL."""
        audio_source = None

        # Download audio file for reliable playback
        print(f"[DEBUG] Downloading: {song.title}")
        downloaded = await audio_cache.ensure_downloaded(song)
        if downloaded and song.local_path:
            print(f"[DEBUG] Playing from cache: {song.local_path}")
            audio_source = song.local_path
        else:
            print(f"[DEBUG] Cache failed, falling back to stream")

        # Fallback to streaming URL
        if not audio_source:
            print(f"[DEBUG] Playing stream: {song.title}")
            print(f"[DEBUG] URL starts with: {song.url[:80]}...")
            if not song.url or not song.url.startswith("http"):
                print(f"[ERROR] Invalid URL for song: {song.title}")
                self._start_disconnect_timer(guild_id, player)
                return None
            audio_source = song.url

        try:
            # Only use network options for streaming URLs, not local files
            before_opts = FFMPEG_BEFORE_OPTIONS if audio_source.startswith("http") else None

            source = discord.FFmpegPCMAudio(
                audio_source,
                before_options=before_opts,
                options=FFMPEG_OPTIONS,
                stderr=subprocess.PIPE,  # Capture FFmpeg errors
            )
        except Exception as e:
            print(f"[ERROR] Failed to create FFmpeg source: {e}")
            self._start_disconnect_timer(guild_id, player)
            return None

        return discord.PCMVolumeTransformer(source, volume=player.volume)

    def _make_after_callback(self, song: SongInfo, player: GuildPlayer, guild_id: int, source):
        """Create the after-playback callback for voice client."""
        def after_callback(error):
            # Check FFmpeg process status
            ffmpeg_error = False
            return_code = None
            if hasattr(source, 'original') and hasattr(source.original, '_process'):
                proc = source.original._process
                if proc:
                    return_code = proc.returncode
                    # Non-zero return code indicates FFmpeg error
                    if return_code and return_code != 0:
                        ffmpeg_error = True
                        # Read stderr if available
                        stderr_output = ""
                        if proc.stderr:
                            try:
                                stderr_output = proc.stderr.read().decode('utf-8', errors='replace')
                            except Exception:
                                pass
                        print(f"[ERROR] FFmpeg crashed with code {return_code} for: {song.title}")
                        if stderr_output:
                            print(f"[ERROR] FFmpeg stderr: {stderr_output[:500]}")

            if error:
                print(f"[ERROR] Playback error: {error}")
            elif ffmpeg_error:
                print(f"[ERROR] FFmpeg abnormal exit (code {return_code}) for: {song.title}")
            else:
                print(f"[DEBUG] Playback finished for: {song.title}")

            # Clean up cached file after playback
            if song.local_path:
                audio_cache.remove(song.video_id)

            # Schedule next song
            if player.voice_client and player.voice_client.loop:
                asyncio.run_coroutine_threadsafe(
                    self.play_next(guild_id),
                    player.voice_client.loop,
                )

        return after_callback

    async def play_next(self, guild_id: int) -> SongInfo | None:
        """Play the next song in queue or use pre-fetched autoplay."""
        player = self.get_player(guild_id)

        async with player._lock:
            # Cancel any pending disconnect
            self._cancel_disconnect_timer(player)

            if not player.voice_client or not player.voice_client.is_connected():
                return None

            song = await self._get_next_song(guild_id, player)
            if not song:
                return None

            # Play the song
            player.current_song = song
            player.ytmusic.mark_played(song.video_id)

            # Track recent songs for blended recommendations
            if song.video_id not in player.recent_songs:
                player.recent_songs.append(song.video_id)
                while len(player.recent_songs) > RECENT_SONGS_LIMIT:
                    player.recent_songs.popleft()

            source = await self._create_audio_source(song, player, guild_id)
            if not source:
                return None

            callback = self._make_after_callback(song, player, guild_id, source)
            player.voice_client.play(source, after=callback)

            # Track playback timing
            player.song_start_time = time.time()
            player.paused_at = None
            player.total_paused_time = 0.0

            # Pre-fetch autoplay songs in background if autoplay is enabled
            if player.autoplay_enabled:
                self._start_prefetch(guild_id, player)

            # Pre-download next song(s) in queue for seamless playback
            self._prefetch_next_audio(player)

            return song

    def _prefetch_next_audio(self, player: GuildPlayer) -> None:
        """Start background download for next songs in queue."""
        # Prefetch from regular queue first
        for i, next_song in enumerate(player.queue):
            if i >= 2:  # Only prefetch first 2
                break
            if not next_song.local_path and not audio_cache.is_ready(next_song.video_id):
                audio_cache.start_background_download(next_song)

        # Then from autoplay queue
        for i, next_song in enumerate(player.autoplay_queue):
            if i >= 1:  # Only prefetch 1 from autoplay
                break
            if not next_song.local_path and not audio_cache.is_ready(next_song.video_id):
                audio_cache.start_background_download(next_song)

    async def _get_autoplay_song(self, guild_id: int, player: GuildPlayer) -> SongInfo | None:
        """Fetch a single song from autoplay recommendations (fallback)."""
        if not player.recent_songs:
            return None

        # Use blended recommendations from recent songs
        recommendations = self._get_blended_recommendations(guild_id, player, limit=5)

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
        if len(player.autoplay_queue) >= AUTOPLAY_PREFETCH_COUNT:
            return

        if player.voice_client and player.voice_client.loop:
            coro = self._prefetch_autoplay(guild_id, player, count=AUTOPLAY_PREFETCH_COUNT)
            player._prefetch_task = player.voice_client.loop.create_task(coro)

    async def _cancel_prefetch(self, player: GuildPlayer) -> None:
        """Cancel any running prefetch task."""
        _cancel_task(player._prefetch_task)
        if player._prefetch_task:
            try:
                await player._prefetch_task
            except asyncio.CancelledError:
                pass
            player._prefetch_task = None

    def _get_blended_recommendations(
        self, guild_id: int, player: GuildPlayer, limit: int
    ) -> list[dict]:
        """Get blended recommendations from recent songs, sorted by guild ratings."""
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

        # Sort by guild ratings: positive first, neutral middle, heavily disliked last
        ratings = get_guild_ratings(guild_id)

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
        recommendations = self._get_blended_recommendations(
            guild_id, player, limit=count + 2  # Get extra in case some fail
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
        _cancel_task(player._disconnect_task)
        player._disconnect_task = None

        if player.voice_client:
            async def disconnect_after_timeout():
                await asyncio.sleep(DISCONNECT_TIMEOUT)
                await self.disconnect(guild_id)

            player._disconnect_task = asyncio.create_task(disconnect_after_timeout())

    def _cancel_disconnect_timer(self, player: GuildPlayer) -> None:
        """Cancel the auto-disconnect timer."""
        _cancel_task(player._disconnect_task)
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
            player.paused_at = time.time()
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

    async def shuffle_queue(self, guild_id: int) -> int:
        """Shuffle the queue. Returns count of shuffled songs."""
        player = self.get_player(guild_id)
        async with player._lock:
            if len(player.queue) < 2:
                return len(player.queue)
            queue_list = list(player.queue)
            random.shuffle(queue_list)
            player.queue = deque(queue_list)
            return len(player.queue)

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

    # ============== Recording Methods ==============

    def is_recording(self, guild_id: int) -> bool:
        """Check if recording is active for this guild."""
        player = self.get_player(guild_id)
        return player.recording_session is not None

    async def start_recording(self, guild_id: int, started_by: int) -> RecordingSession | None:
        """Start recording voice channel audio. Returns session or None if failed."""
        player = self.get_player(guild_id)

        if not player.voice_client or not player.voice_client.is_connected():
            return None

        if player.recording_session:
            return None  # Already recording

        # Create recording session
        session_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:8]
        session = RecordingSession(
            session_id=session_id,
            guild_id=guild_id,
            started_by=started_by,
        )

        # Create audio sink and start listening
        sink = WavAudioSink(session)
        player.voice_client.listen(sink)

        player.recording_session = session
        player.audio_sink = sink

        return session

    async def stop_recording(self, guild_id: int) -> dict | None:
        """Stop recording and save files. Returns stats dict or None if not recording."""
        player = self.get_player(guild_id)

        if not player.recording_session or not player.audio_sink:
            return None

        # Stop listening
        if player.voice_client and player.voice_client.is_connected():
            player.voice_client.stop_listening()

        # Get stats before saving
        stats = get_recording_stats(player.audio_sink)

        # Save recordings
        saved_files = save_recordings(player.audio_sink)
        stats["saved_files"] = {uid: str(path) for uid, path in saved_files.items()}
        stats["output_dir"] = str(player.recording_session.output_dir)
        stats["session_id"] = player.recording_session.session_id

        # Cleanup
        player.audio_sink.cleanup()
        player.recording_session = None
        player.audio_sink = None

        return stats

    # ============== Volume and TTS Playback Methods ==============

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

    def get_volume(self, guild_id: int) -> float:
        """Get current volume for a guild."""
        player = self.get_player(guild_id)
        return player.volume

    async def play_audio_file(self, guild_id: int, file_path: str) -> bool:
        """
        Play a local audio file (used for TTS). Waits for playback to complete.

        Args:
            guild_id: Discord guild ID
            file_path: Path to audio file (MP3 or WAV)

        Returns:
            True if playback completed successfully
        """
        player = self.get_player(guild_id)

        if not player.voice_client or not player.voice_client.is_connected():
            return False

        # Wait for current audio to finish if playing (outside lock to avoid blocking)
        while player.voice_client and player.voice_client.is_playing():
            await asyncio.sleep(0.1)

        # Create event to signal when playback is done
        playback_done = asyncio.Event()

        def after_callback(error):
            if error:
                print(f"TTS playback error: {error}")
            # Signal that playback is complete
            if player.voice_client and player.voice_client.loop:
                player.voice_client.loop.call_soon_threadsafe(playback_done.set)

        # Use lock briefly only for starting playback to prevent race with play_next
        async with player._lock:
            if not player.voice_client or not player.voice_client.is_connected():
                return False

            # Create audio source from file
            source = discord.FFmpegPCMAudio(file_path)
            # Wrap with volume transformer
            source = discord.PCMVolumeTransformer(source, volume=player.volume)

            # Play the audio
            player.voice_client.play(source, after=after_callback)

        # Wait for playback to complete (outside lock to allow other operations)
        await playback_done.wait()
        return True


# Global player manager instance
player_manager = MusicPlayerManager()
