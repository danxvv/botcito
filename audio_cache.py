"""Pre-download audio cache to eliminate mid-song network stuttering."""

import asyncio
import atexit
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yt_dlp

logger = logging.getLogger(__name__)

CACHE_DIR = Path("data/audio_cache")
COOKIES_FILE = Path(__file__).parent / "cookies.txt"
MAX_CACHED_FILES = 10
MAX_CACHE_SIZE_MB = 500
DOWNLOAD_TIMEOUT = 60

_download_executor = ThreadPoolExecutor(max_workers=2)
atexit.register(_download_executor.shutdown, wait=False)


class AudioCache:
    """Manages pre-downloading and caching audio files for smooth playback."""

    def __init__(self, cache_dir: Path = CACHE_DIR):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._files: dict[str, Path] = {}
        self._cache_size: int = 0  # Track total size in memory
        self._ready_events: dict[str, asyncio.Event] = {}
        self._download_tasks: dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()
        self._clean_stale_files()

    def _clean_stale_files(self) -> None:
        """Remove leftover files from previous runs."""
        for f in self.cache_dir.iterdir():
            if f.is_file():
                try:
                    f.unlink()
                except OSError:
                    pass

    def _download_sync(self, video_id: str, webpage_url: str) -> Path | None:
        """Download audio file via yt-dlp (blocking, runs in executor)."""
        # Clean any pre-existing files for this video_id before downloading
        for f in self.cache_dir.glob(f"{video_id}.*"):
            try:
                f.unlink()
            except OSError:
                pass

        output_template = str(self.cache_dir / video_id)
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ydl_opts = {
            "format": "251/250/249/140/139/bestaudio/best",
            "outtmpl": output_template,
            "noplaylist": True,
            "quiet": False,
            "no_warnings": False,
            "http_headers": {"User-Agent": user_agent},
            "cachedir": False,
            "js_runtimes": {"deno": {}, "node": {}, "bun": {}},
            "remote_components": {"ejs:github": {}},
            "extractor_args": {"youtube": {"player_client": ["tv", "web"]}},
        }
        if COOKIES_FILE.exists():
            ydl_opts["cookiefile"] = str(COOKIES_FILE)
            print(f"[DEBUG] Cache using cookies from: {COOKIES_FILE}")
        else:
            print(f"[DEBUG] No cookies file at: {COOKIES_FILE}")
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([webpage_url])
            # yt-dlp appends the extension; find the actual file
            for f in self.cache_dir.glob(f"{video_id}.*"):
                return f
            output_path = Path(output_template)
            if output_path.exists():
                return output_path
            return None
        except Exception as e:
            logger.error("Download failed for %s: %s", video_id, e)
            return None

    async def ensure_downloaded(self, song) -> bool:
        """Ensure a song is downloaded. Waits if already in progress."""
        async with self._lock:
            if song.video_id in self._files:
                path = self._files[song.video_id]
                if path.exists():
                    song.local_path = str(path)
                    return True
                else:
                    del self._files[song.video_id]

            event = self._ready_events.get(song.video_id)

        if event:
            try:
                await asyncio.wait_for(event.wait(), timeout=DOWNLOAD_TIMEOUT)
            except asyncio.TimeoutError:
                return False
            async with self._lock:
                if song.video_id in self._files:
                    song.local_path = str(self._files[song.video_id])
                    return True
            return False

        return await self._start_download(song)

    async def _start_download(self, song) -> bool:
        """Start a download and wait for completion."""
        event = asyncio.Event()
        async with self._lock:
            # Double-check another task didn't start while we waited for lock
            if song.video_id in self._ready_events:
                existing_event = self._ready_events[song.video_id]
            else:
                existing_event = None
                self._ready_events[song.video_id] = event

        # If another download is in progress, wait for it outside the lock
        if existing_event:
            try:
                await asyncio.wait_for(existing_event.wait(), timeout=DOWNLOAD_TIMEOUT)
            except asyncio.TimeoutError:
                return False
            async with self._lock:
                if song.video_id in self._files:
                    song.local_path = str(self._files[song.video_id])
                    return True
            return False

        loop = asyncio.get_running_loop()
        try:
            path = await asyncio.wait_for(
                loop.run_in_executor(
                    _download_executor,
                    self._download_sync,
                    song.video_id,
                    song.webpage_url,
                ),
                timeout=DOWNLOAD_TIMEOUT,
            )
            if path and path.exists():
                file_size = path.stat().st_size
                async with self._lock:
                    self._files[song.video_id] = path
                    self._cache_size += file_size
                    self._enforce_limits()
                song.local_path = str(path)
                return True
            return False
        except (asyncio.TimeoutError, Exception) as e:
            logger.error("Download failed for %s: %s", song.video_id, e)
            return False
        finally:
            event.set()
            async with self._lock:
                self._ready_events.pop(song.video_id, None)

    def start_background_download(self, song) -> None:
        """Fire-and-forget download. Does not block."""
        vid = song.video_id
        if vid in self._files or vid in self._ready_events:
            return

        task = asyncio.create_task(self._start_download(song))
        self._download_tasks[vid] = task
        task.add_done_callback(lambda _: self._download_tasks.pop(vid, None))

    def remove(self, video_id: str) -> None:
        """Delete cached file for a song."""
        path = self._files.pop(video_id, None)
        if path and path.exists():
            try:
                size = path.stat().st_size
                path.unlink()
                self._cache_size = max(0, self._cache_size - size)
            except OSError as e:
                logger.warning("Failed to delete %s: %s", path, e)

    def _enforce_limits(self) -> None:
        """Remove oldest files if over count or size limits."""
        while len(self._files) > MAX_CACHED_FILES:
            oldest_id = next(iter(self._files))
            self.remove(oldest_id)

        max_bytes = MAX_CACHE_SIZE_MB * 1024 * 1024
        while self._cache_size > max_bytes and self._files:
            oldest_id = next(iter(self._files))
            self.remove(oldest_id)

    def is_ready(self, video_id: str) -> bool:
        """Check if a song is already downloaded."""
        return video_id in self._files

    def cleanup_all(self) -> None:
        """Remove all cached files and cancel in-flight downloads."""
        for task in self._download_tasks.values():
            task.cancel()
        self._download_tasks.clear()
        self._ready_events.clear()
        for vid in list(self._files):
            self.remove(vid)


audio_cache = AudioCache()
