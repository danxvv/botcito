"""Bounded audio downloads shared safely between listening sessions."""

import asyncio
import atexit
import logging
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event

import yt_dlp
from yt_dlp.utils import DownloadError

from youtube import SongInfo, _get_options

logger = logging.getLogger(__name__)
CACHE_DIR = Path(__file__).parent / "data" / "audio_cache"
MAX_CACHED_FILES = 10
MAX_CACHE_SIZE_MB = 500
DOWNLOAD_TIMEOUT = 60
STARTUP_WAIT = 3.0
_download_executor = ThreadPoolExecutor(max_workers=2)
atexit.register(_download_executor.shutdown, wait=False)


class AudioCache:
    """Download ahead, sharing files without cancelling another server's music."""

    def __init__(self, cache_dir: Path = CACHE_DIR) -> None:
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._files: dict[str, Path] = {}
        self._download_tasks: dict[str, asyncio.Task] = {}
        self._cancellations: dict[str, Event] = {}
        self._users: dict[str, set[str]] = {}
        self._playing: dict[str, str] = {}

    def clear_stale_files(self) -> None:
        """Clean the previous process's temporary audio once, at bot startup."""
        for path in self.cache_dir.iterdir():
            try:
                if path.is_file():
                    path.unlink(missing_ok=True)
                elif path.name.startswith("download-") and path.is_dir():
                    shutil.rmtree(path)
            except OSError:
                logger.warning("Could not remove stale audio cache file %s", path)

    def retain(self, song: SongInfo) -> None:
        self._users.setdefault(song.video_id, set()).add(song.entry_id)

    def protect(self, song: SongInfo) -> None:
        self.retain(song)
        self._playing[song.entry_id] = song.video_id

    def release(self, song: SongInfo) -> None:
        self._playing.pop(song.entry_id, None)
        users = self._users.get(song.video_id, set())
        users.discard(song.entry_id)
        if not users:
            self._users.pop(song.video_id, None)
            self.cancel(song.video_id)
        self._enforce_limits()

    def _download_sync(self, song: SongInfo, cancelled: Event) -> Path | None:
        def check_cancelled(progress: dict) -> None:
            if cancelled.is_set():
                raise DownloadError("Download cancelled")

        if cancelled.is_set():
            return None
        with TemporaryDirectory(prefix="download-", dir=self.cache_dir) as directory:
            options = _get_options()
            options.update(
                {
                    "outtmpl": str(Path(directory) / "audio.%(ext)s"),
                    "cachedir": False,
                    "progress_hooks": [check_cancelled],
                    "quiet": True,
                }
            )
            try:
                with yt_dlp.YoutubeDL(options) as ydl:
                    info = ydl.extract_info(song.webpage_url, download=True)
                    if not info or cancelled.is_set():
                        return None
                    path = Path(info.get("filepath") or ydl.prepare_filename(info))
                if not path.is_file() or path.suffix in {".part", ".ytdl"}:
                    return None
                destination = self.cache_dir / f"{Path(directory).name}{path.suffix}"
                path.replace(destination)
                return destination
            except (DownloadError, OSError):
                if not cancelled.is_set():
                    logger.exception("Audio download failed for %s", song.video_id)
                return None

    async def _download(self, song: SongInfo, cancelled: Event) -> None:
        future = asyncio.get_running_loop().run_in_executor(
            _download_executor, self._download_sync, song, cancelled
        )
        try:
            path = await asyncio.wait_for(asyncio.shield(future), DOWNLOAD_TIMEOUT)
            if path:
                self._files[song.video_id] = path
                self._enforce_limits()
        except (asyncio.CancelledError, asyncio.TimeoutError):
            cancelled.set()

            # Cancelling an executor future does not stop its thread. Reap a late file.
            def discard_result(result: asyncio.Future) -> None:
                try:
                    path = result.result()
                    if path:
                        path.unlink(missing_ok=True)
                except (Exception, asyncio.CancelledError):
                    logger.debug("Cancelled download cleanup failed", exc_info=True)

            future.add_done_callback(discard_result)
        except Exception:
            logger.exception("Audio cache failed for %s", song.video_id)

    def start_background_download(self, song: SongInfo) -> None:
        if (
            song.is_live
            or self.is_ready(song.video_id)
            or song.video_id in self._download_tasks
        ):
            return
        cancelled = Event()
        self._cancellations[song.video_id] = cancelled
        task = asyncio.create_task(self._download(song, cancelled))
        self._download_tasks[song.video_id] = task

        def finished(completed: asyncio.Task) -> None:
            if self._download_tasks.get(song.video_id) is completed:
                self._download_tasks.pop(song.video_id, None)
                self._cancellations.pop(song.video_id, None)

        task.add_done_callback(finished)

    async def ensure_downloaded(
        self, song: SongInfo, timeout: float = STARTUP_WAIT
    ) -> bool:
        """Wait briefly for a file, leaving slow downloads running in the background."""
        self.start_background_download(song)
        task = self._download_tasks.get(song.video_id)
        if task:
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout)
            except asyncio.TimeoutError:
                pass
        path = self._files.get(song.video_id)
        song.local_path = str(path) if path and path.is_file() else None
        return song.local_path is not None

    def remove(self, video_id: str) -> None:
        path = self._files.pop(video_id, None)
        if path:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                logger.warning("Could not remove cached audio", exc_info=True)

    def cancel(self, video_id: str) -> None:
        cancelled = self._cancellations.pop(video_id, None)
        if cancelled:
            cancelled.set()
        task = self._download_tasks.pop(video_id, None)
        if task:
            task.cancel()
        self.remove(video_id)

    def _enforce_limits(self) -> None:
        total = sum(
            path.stat().st_size for path in self._files.values() if path.exists()
        )
        for video_id, path in list(self._files.items()):
            if (
                len(self._files) <= MAX_CACHED_FILES
                and total <= MAX_CACHE_SIZE_MB * 1024 * 1024
            ):
                break
            if video_id in self._playing.values():
                continue
            total -= path.stat().st_size if path.exists() else 0
            self.remove(video_id)

    def is_ready(self, video_id: str) -> bool:
        path = self._files.get(video_id)
        return bool(path and path.is_file())

    def cleanup_all(self) -> None:
        for video_id in set(self._download_tasks) | set(self._files):
            self.cancel(video_id)
        self._users.clear()
        self._playing.clear()


audio_cache = AudioCache()
