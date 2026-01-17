"""YouTube Music handler for search autocomplete and autoplay recommendations."""

import logging
from collections import OrderedDict

from ytmusicapi import YTMusic

logger = logging.getLogger(__name__)

# Cache and history limits
MAX_RECOMMENDATION_CACHE_SIZE = 50
MAX_PLAYED_VIDEOS_SIZE = 200


class YouTubeMusicHandler:
    """Handles YouTube Music search and autoplay recommendations."""

    def __init__(self):
        self.ytmusic = YTMusic()
        self._played_videos_list: list[str] = []  # Ordered list for LRU-style eviction
        self._played_videos_set: set[str] = set()  # Set for O(1) lookups
        self._recommendation_cache: OrderedDict[str, list[dict]] = OrderedDict()  # LRU cache

    def search_songs(self, query: str, limit: int = 10) -> list[dict]:
        """
        Search for songs on YouTube Music.

        Args:
            query: Search query string
            limit: Maximum number of results to return

        Returns:
            List of song dictionaries with videoId, title, and artists
        """
        if len(query) < 2:
            return []

        try:
            results = self.ytmusic.search(query, filter="songs", limit=limit)
            return [
                {
                    "videoId": r["videoId"],
                    "title": r["title"],
                    "artist": r["artists"][0]["name"] if r.get("artists") else "Unknown",
                    "duration": r.get("duration", ""),
                }
                for r in results
                if r.get("videoId")
            ]
        except Exception as e:
            logger.exception("Failed to search songs for query '%s': %s", query, e)
            return []

    def get_recommendations(self, video_id: str, limit: int = 10) -> list[dict]:
        """
        Get song recommendations based on a video ID for autoplay.

        Args:
            video_id: YouTube video ID of the current song
            limit: Maximum number of recommendations

        Returns:
            List of recommended songs (filtered to exclude already played)
        """
        # Check cache first (move to end for LRU behavior)
        if video_id in self._recommendation_cache:
            self._recommendation_cache.move_to_end(video_id)
            cached = self._recommendation_cache[video_id]
            # Filter out already played and return up to limit
            return [
                r for r in cached
                if r["videoId"] not in self._played_videos_set
            ][:limit]

        try:
            watch_playlist = self.ytmusic.get_watch_playlist(videoId=video_id)
            tracks = watch_playlist.get("tracks", [])

            # Store all recommendations in cache (unfiltered)
            all_recommendations = []
            for track in tracks:
                vid = track.get("videoId")
                if vid and vid != video_id:
                    all_recommendations.append(
                        {
                            "videoId": vid,
                            "title": track.get("title", "Unknown"),
                            "artist": (
                                track["artists"][0]["name"]
                                if track.get("artists")
                                else "Unknown"
                            ),
                            "duration": track.get("length", ""),
                        }
                    )

            # Evict oldest entries if cache is full
            while len(self._recommendation_cache) >= MAX_RECOMMENDATION_CACHE_SIZE:
                self._recommendation_cache.popitem(last=False)

            # Cache all recommendations for this video
            self._recommendation_cache[video_id] = all_recommendations

            # Return filtered results
            return [
                r for r in all_recommendations
                if r["videoId"] not in self._played_videos_set
            ][:limit]
        except Exception as e:
            logger.exception("Failed to get recommendations for video '%s': %s", video_id, e)
            return []

    def mark_played(self, video_id: str) -> None:
        """Mark a video as played to avoid repeating in autoplay."""
        if video_id in self._played_videos_set:
            return  # Already marked

        # Evict oldest if at capacity
        while len(self._played_videos_list) >= MAX_PLAYED_VIDEOS_SIZE:
            oldest = self._played_videos_list.pop(0)
            self._played_videos_set.discard(oldest)

        self._played_videos_list.append(video_id)
        self._played_videos_set.add(video_id)

    def clear_history(self) -> None:
        """Clear the played videos history and recommendation cache."""
        self._played_videos_list.clear()
        self._played_videos_set.clear()
        self._recommendation_cache.clear()
