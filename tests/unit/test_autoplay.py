"""Unit tests for autoplay.py - YouTube Music recommendations."""

from unittest.mock import MagicMock, patch

import pytest

from autoplay import MAX_PLAYED_VIDEOS_SIZE, MAX_RECOMMENDATION_CACHE_SIZE, YouTubeMusicHandler


class TestYouTubeMusicHandlerInit:
    """Tests for YouTubeMusicHandler initialization."""

    def test_init_creates_empty_history(self):
        """Test handler initializes with empty history."""
        with patch("autoplay.YTMusic"):
            handler = YouTubeMusicHandler()
            assert len(handler._played_videos_list) == 0
            assert len(handler._played_videos_set) == 0
            assert len(handler._recommendation_cache) == 0


class TestSearchSongs:
    """Tests for search_songs method."""

    def test_search_returns_formatted_results(self, mock_ytmusic_search_results):
        """Test search returns properly formatted song list."""
        with patch("autoplay.YTMusic") as mock_ytmusic_class:
            mock_instance = MagicMock()
            mock_instance.search.return_value = mock_ytmusic_search_results
            mock_ytmusic_class.return_value = mock_instance

            handler = YouTubeMusicHandler()
            results = handler.search_songs("never gonna give you up", limit=10)

            assert len(results) == 2
            assert results[0]["videoId"] == "dQw4w9WgXcQ"
            assert results[0]["title"] == "Never Gonna Give You Up"
            assert results[0]["artist"] == "Rick Astley"

    def test_search_short_query_returns_empty(self):
        """Test search with query shorter than 2 chars returns empty."""
        with patch("autoplay.YTMusic"):
            handler = YouTubeMusicHandler()
            results = handler.search_songs("a")

            assert results == []

    def test_search_empty_query_returns_empty(self):
        """Test search with empty query returns empty."""
        with patch("autoplay.YTMusic"):
            handler = YouTubeMusicHandler()
            results = handler.search_songs("")

            assert results == []

    def test_search_handles_api_error(self):
        """Test search returns empty list on API error."""
        with patch("autoplay.YTMusic") as mock_ytmusic_class:
            mock_instance = MagicMock()
            mock_instance.search.side_effect = Exception("API Error")
            mock_ytmusic_class.return_value = mock_instance

            handler = YouTubeMusicHandler()
            results = handler.search_songs("test query")

            assert results == []

    def test_search_handles_missing_artists(self):
        """Test search handles songs without artists field."""
        results_no_artists = [
            {
                "videoId": "abc123",
                "title": "Unknown Artist Song",
                "duration": "3:00",
            }
        ]

        with patch("autoplay.YTMusic") as mock_ytmusic_class:
            mock_instance = MagicMock()
            mock_instance.search.return_value = results_no_artists
            mock_ytmusic_class.return_value = mock_instance

            handler = YouTubeMusicHandler()
            results = handler.search_songs("test")

            assert len(results) == 1
            assert results[0]["artist"] == "Unknown"


class TestGetRecommendations:
    """Tests for get_recommendations method."""

    def test_get_recommendations_filters_played(self, mock_ytmusic_recommendations):
        """Test recommendations exclude already played videos."""
        with patch("autoplay.YTMusic") as mock_ytmusic_class:
            mock_instance = MagicMock()
            mock_instance.get_watch_playlist.return_value = mock_ytmusic_recommendations
            mock_ytmusic_class.return_value = mock_instance

            handler = YouTubeMusicHandler()
            handler.mark_played("abc123")  # Mark first recommendation as played

            recs = handler.get_recommendations("dQw4w9WgXcQ", limit=10)

            # Should not include abc123
            video_ids = [r["videoId"] for r in recs]
            assert "abc123" not in video_ids
            assert "def456" in video_ids

    def test_get_recommendations_uses_cache(self, mock_ytmusic_recommendations):
        """Test recommendations are cached and reused."""
        with patch("autoplay.YTMusic") as mock_ytmusic_class:
            mock_instance = MagicMock()
            mock_instance.get_watch_playlist.return_value = mock_ytmusic_recommendations
            mock_ytmusic_class.return_value = mock_instance

            handler = YouTubeMusicHandler()

            # First call - should hit API
            handler.get_recommendations("dQw4w9WgXcQ")
            assert mock_instance.get_watch_playlist.call_count == 1

            # Second call - should use cache
            handler.get_recommendations("dQw4w9WgXcQ")
            assert mock_instance.get_watch_playlist.call_count == 1  # No additional call

    def test_get_recommendations_respects_limit(self, mock_ytmusic_recommendations):
        """Test recommendations respect the limit parameter."""
        with patch("autoplay.YTMusic") as mock_ytmusic_class:
            mock_instance = MagicMock()
            mock_instance.get_watch_playlist.return_value = mock_ytmusic_recommendations
            mock_ytmusic_class.return_value = mock_instance

            handler = YouTubeMusicHandler()
            recs = handler.get_recommendations("dQw4w9WgXcQ", limit=2)

            assert len(recs) <= 2

    def test_get_recommendations_excludes_source_video(self, mock_ytmusic_recommendations):
        """Test recommendations exclude the source video itself."""
        # Add the source video to the tracks
        tracks_with_source = mock_ytmusic_recommendations.copy()
        tracks_with_source["tracks"] = [
            {"videoId": "dQw4w9WgXcQ", "title": "Source", "artists": [{"name": "Artist"}]},
        ] + mock_ytmusic_recommendations["tracks"]

        with patch("autoplay.YTMusic") as mock_ytmusic_class:
            mock_instance = MagicMock()
            mock_instance.get_watch_playlist.return_value = tracks_with_source
            mock_ytmusic_class.return_value = mock_instance

            handler = YouTubeMusicHandler()
            recs = handler.get_recommendations("dQw4w9WgXcQ", limit=10)

            video_ids = [r["videoId"] for r in recs]
            assert "dQw4w9WgXcQ" not in video_ids

    def test_get_recommendations_handles_api_error(self):
        """Test empty list returned on API error."""
        with patch("autoplay.YTMusic") as mock_ytmusic_class:
            mock_instance = MagicMock()
            mock_instance.get_watch_playlist.side_effect = Exception("API Error")
            mock_ytmusic_class.return_value = mock_instance

            handler = YouTubeMusicHandler()
            recs = handler.get_recommendations("dQw4w9WgXcQ")

            assert recs == []

    def test_cache_eviction_when_full(self, mock_ytmusic_recommendations):
        """Test LRU cache evicts oldest entries when full."""
        with patch("autoplay.YTMusic") as mock_ytmusic_class:
            mock_instance = MagicMock()
            mock_instance.get_watch_playlist.return_value = mock_ytmusic_recommendations
            mock_ytmusic_class.return_value = mock_instance

            handler = YouTubeMusicHandler()

            # Fill cache beyond limit
            for i in range(MAX_RECOMMENDATION_CACHE_SIZE + 5):
                handler.get_recommendations(f"video_{i}")

            assert len(handler._recommendation_cache) <= MAX_RECOMMENDATION_CACHE_SIZE


class TestMarkPlayed:
    """Tests for mark_played method."""

    def test_mark_played_adds_to_history(self):
        """Test marking a video as played adds it to history."""
        with patch("autoplay.YTMusic"):
            handler = YouTubeMusicHandler()
            handler.mark_played("abc123")

            assert "abc123" in handler._played_videos_set
            assert "abc123" in handler._played_videos_list

    def test_mark_played_idempotent(self):
        """Test marking same video twice doesn't duplicate."""
        with patch("autoplay.YTMusic"):
            handler = YouTubeMusicHandler()
            handler.mark_played("abc123")
            handler.mark_played("abc123")

            assert handler._played_videos_list.count("abc123") == 1
            assert len(handler._played_videos_set) == 1

    def test_mark_played_evicts_oldest(self):
        """Test oldest entries are evicted when at capacity."""
        with patch("autoplay.YTMusic"):
            handler = YouTubeMusicHandler()

            # Fill beyond limit
            for i in range(MAX_PLAYED_VIDEOS_SIZE + 5):
                handler.mark_played(f"video_{i}")

            assert len(handler._played_videos_list) <= MAX_PLAYED_VIDEOS_SIZE
            assert len(handler._played_videos_set) <= MAX_PLAYED_VIDEOS_SIZE

            # Oldest should be evicted
            assert "video_0" not in handler._played_videos_set
            # Newest should still be present
            assert f"video_{MAX_PLAYED_VIDEOS_SIZE + 4}" in handler._played_videos_set


class TestClearHistory:
    """Tests for clear_history method."""

    def test_clear_history_empties_all(self, mock_ytmusic_recommendations):
        """Test clear_history empties played videos and cache."""
        with patch("autoplay.YTMusic") as mock_ytmusic_class:
            mock_instance = MagicMock()
            mock_instance.get_watch_playlist.return_value = mock_ytmusic_recommendations
            mock_ytmusic_class.return_value = mock_instance

            handler = YouTubeMusicHandler()

            # Add some state
            handler.mark_played("abc123")
            handler.mark_played("def456")
            handler.get_recommendations("dQw4w9WgXcQ")

            assert len(handler._played_videos_list) > 0
            assert len(handler._recommendation_cache) > 0

            # Clear everything
            handler.clear_history()

            assert len(handler._played_videos_list) == 0
            assert len(handler._played_videos_set) == 0
            assert len(handler._recommendation_cache) == 0
