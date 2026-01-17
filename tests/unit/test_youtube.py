"""Unit tests for youtube.py - YouTube extraction via yt-dlp."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest
import yt_dlp

from youtube import (
    SongInfo,
    extract_playlist,
    extract_song_info,
    is_playlist_url,
    search_youtube,
)


class TestSongInfo:
    """Tests for the SongInfo dataclass."""

    def test_song_info_creation(self):
        """Test creating a SongInfo object."""
        song = SongInfo(
            url="https://example.com/stream",
            title="Test Song",
            duration=180,
            thumbnail="https://example.com/thumb.jpg",
            video_id="abc123",
            webpage_url="https://youtube.com/watch?v=abc123",
        )
        assert song.title == "Test Song"
        assert song.duration == 180
        assert song.video_id == "abc123"

    def test_song_info_equality(self):
        """Test SongInfo equality comparison."""
        song1 = SongInfo(
            url="url", title="title", duration=100, thumbnail="", video_id="id1", webpage_url=""
        )
        song2 = SongInfo(
            url="url", title="title", duration=100, thumbnail="", video_id="id1", webpage_url=""
        )
        assert song1 == song2


class TestIsPlaylistUrl:
    """Tests for is_playlist_url function."""

    def test_playlist_url_with_list_param(self):
        """Test URL with list= parameter."""
        url = "https://www.youtube.com/watch?v=abc123&list=PLxyz789"
        assert is_playlist_url(url) is True

    def test_playlist_url_with_playlist_path(self):
        """Test URL with /playlist path."""
        url = "https://www.youtube.com/playlist?list=PLxyz789"
        assert is_playlist_url(url) is True

    def test_single_video_url(self):
        """Test single video URL (not a playlist)."""
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        assert is_playlist_url(url) is False

    def test_short_url(self):
        """Test youtu.be short URL (not a playlist)."""
        url = "https://youtu.be/dQw4w9WgXcQ"
        assert is_playlist_url(url) is False


class TestExtractSongInfo:
    """Tests for extract_song_info function."""

    @pytest.mark.asyncio
    async def test_extract_from_url(self, mock_ytdl_extract_info):
        """Test extracting song info from a YouTube URL."""
        with patch("youtube.yt_dlp.YoutubeDL") as mock_ytdl_class:
            mock_instance = MagicMock()
            mock_instance.extract_info.return_value = mock_ytdl_extract_info
            mock_instance.__enter__ = MagicMock(return_value=mock_instance)
            mock_instance.__exit__ = MagicMock(return_value=False)
            mock_ytdl_class.return_value = mock_instance

            song = await extract_song_info("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

            assert song is not None
            assert song.video_id == "dQw4w9WgXcQ"
            assert song.title == "Rick Astley - Never Gonna Give You Up"
            assert song.duration == 212

    @pytest.mark.asyncio
    async def test_extract_from_video_id(self, mock_ytdl_extract_info):
        """Test extracting song info from a video ID (11 chars)."""
        with patch("youtube.yt_dlp.YoutubeDL") as mock_ytdl_class:
            mock_instance = MagicMock()
            mock_instance.extract_info.return_value = mock_ytdl_extract_info
            mock_instance.__enter__ = MagicMock(return_value=mock_instance)
            mock_instance.__exit__ = MagicMock(return_value=False)
            mock_ytdl_class.return_value = mock_instance

            song = await extract_song_info("dQw4w9WgXcQ")

            assert song is not None
            assert song.video_id == "dQw4w9WgXcQ"

    @pytest.mark.asyncio
    async def test_extract_returns_none_on_error(self):
        """Test that extraction returns None on download error."""
        with patch("youtube.yt_dlp.YoutubeDL") as mock_ytdl_class:
            mock_instance = MagicMock()
            mock_instance.extract_info.side_effect = yt_dlp.utils.DownloadError("Video unavailable")
            mock_instance.__enter__ = MagicMock(return_value=mock_instance)
            mock_instance.__exit__ = MagicMock(return_value=False)
            mock_ytdl_class.return_value = mock_instance

            song = await extract_song_info("https://www.youtube.com/watch?v=invalid")

            assert song is None

    @pytest.mark.asyncio
    async def test_extract_with_javascript_error(self, capsys):
        """Test JavaScript error message is printed."""
        with patch("youtube.yt_dlp.YoutubeDL") as mock_ytdl_class:
            mock_instance = MagicMock()
            mock_instance.extract_info.side_effect = yt_dlp.utils.DownloadError(
                "JavaScript extraction failed"
            )
            mock_instance.__enter__ = MagicMock(return_value=mock_instance)
            mock_instance.__exit__ = MagicMock(return_value=False)
            mock_ytdl_class.return_value = mock_instance

            song = await extract_song_info("https://www.youtube.com/watch?v=test")

            assert song is None
            captured = capsys.readouterr()
            assert "Deno" in captured.out or "Node.js" in captured.out

    @pytest.mark.asyncio
    async def test_extract_with_formats_fallback(self):
        """Test fallback to formats array when url is missing."""
        info_without_url = {
            "id": "abc123",
            "title": "Test Song",
            "duration": 180,
            "thumbnail": "",
            "webpage_url": "https://youtube.com/watch?v=abc123",
            "formats": [
                {"format_id": "140", "acodec": "mp4a.40.2", "url": "https://audio-url.com"},
            ],
        }

        with patch("youtube.yt_dlp.YoutubeDL") as mock_ytdl_class:
            mock_instance = MagicMock()
            mock_instance.extract_info.return_value = info_without_url
            mock_instance.__enter__ = MagicMock(return_value=mock_instance)
            mock_instance.__exit__ = MagicMock(return_value=False)
            mock_ytdl_class.return_value = mock_instance

            song = await extract_song_info("https://www.youtube.com/watch?v=abc123")

            assert song is not None
            assert song.url == "https://audio-url.com"

    @pytest.mark.asyncio
    async def test_extract_returns_none_when_no_url(self):
        """Test None returned when no URL can be found."""
        info_no_url = {
            "id": "abc123",
            "title": "Test",
            "duration": 100,
            "thumbnail": "",
            "webpage_url": "",
            "formats": [],
        }

        with patch("youtube.yt_dlp.YoutubeDL") as mock_ytdl_class:
            mock_instance = MagicMock()
            mock_instance.extract_info.return_value = info_no_url
            mock_instance.__enter__ = MagicMock(return_value=mock_instance)
            mock_instance.__exit__ = MagicMock(return_value=False)
            mock_ytdl_class.return_value = mock_instance

            song = await extract_song_info("https://www.youtube.com/watch?v=abc123")

            assert song is None


class TestExtractPlaylist:
    """Tests for extract_playlist function."""

    @pytest.mark.asyncio
    async def test_extract_playlist_entries(self, mock_ytdl_playlist_info):
        """Test extracting entries from a playlist."""
        with patch("youtube.yt_dlp.YoutubeDL") as mock_ytdl_class:
            mock_instance = MagicMock()
            mock_instance.extract_info.return_value = mock_ytdl_playlist_info
            mock_instance.__enter__ = MagicMock(return_value=mock_instance)
            mock_instance.__exit__ = MagicMock(return_value=False)
            mock_ytdl_class.return_value = mock_instance

            entries = await extract_playlist("https://www.youtube.com/playlist?list=PLtest")

            assert len(entries) == 2
            assert entries[0]["video_id"] == "dQw4w9WgXcQ"
            assert entries[1]["video_id"] == "fJ9rUzIMcZQ"

    @pytest.mark.asyncio
    async def test_extract_playlist_empty_on_error(self):
        """Test empty list returned on extraction error."""
        with patch("youtube.yt_dlp.YoutubeDL") as mock_ytdl_class:
            mock_instance = MagicMock()
            mock_instance.extract_info.return_value = None
            mock_instance.__enter__ = MagicMock(return_value=mock_instance)
            mock_instance.__exit__ = MagicMock(return_value=False)
            mock_ytdl_class.return_value = mock_instance

            entries = await extract_playlist("https://www.youtube.com/playlist?list=PLtest")

            assert entries == []

    @pytest.mark.asyncio
    async def test_extract_single_video_as_playlist(self):
        """Test single video URL treated as single-item playlist."""
        single_video_info = {
            "id": "dQw4w9WgXcQ",
            "title": "Never Gonna Give You Up",
            "webpage_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        }

        with patch("youtube.yt_dlp.YoutubeDL") as mock_ytdl_class:
            mock_instance = MagicMock()
            mock_instance.extract_info.return_value = single_video_info
            mock_instance.__enter__ = MagicMock(return_value=mock_instance)
            mock_instance.__exit__ = MagicMock(return_value=False)
            mock_ytdl_class.return_value = mock_instance

            entries = await extract_playlist("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

            assert len(entries) == 1
            assert entries[0]["video_id"] == "dQw4w9WgXcQ"


class TestSearchYoutube:
    """Tests for search_youtube function."""

    @pytest.mark.asyncio
    async def test_search_returns_song(self, mock_ytdl_search_result):
        """Test search returns first result as SongInfo."""
        with patch("youtube.yt_dlp.YoutubeDL") as mock_ytdl_class:
            mock_instance = MagicMock()
            mock_instance.extract_info.return_value = mock_ytdl_search_result
            mock_instance.__enter__ = MagicMock(return_value=mock_instance)
            mock_instance.__exit__ = MagicMock(return_value=False)
            mock_ytdl_class.return_value = mock_instance

            song = await search_youtube("never gonna give you up")

            assert song is not None
            assert song.video_id == "dQw4w9WgXcQ"

    @pytest.mark.asyncio
    async def test_search_returns_none_on_no_results(self):
        """Test search returns None when no results found."""
        with patch("youtube.yt_dlp.YoutubeDL") as mock_ytdl_class:
            mock_instance = MagicMock()
            mock_instance.extract_info.return_value = None
            mock_instance.__enter__ = MagicMock(return_value=mock_instance)
            mock_instance.__exit__ = MagicMock(return_value=False)
            mock_ytdl_class.return_value = mock_instance

            song = await search_youtube("completely invalid search query xyz123")

            assert song is None
