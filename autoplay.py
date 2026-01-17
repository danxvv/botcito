"""YouTube Music handler for search autocomplete and autoplay recommendations."""

from ytmusicapi import YTMusic


class YouTubeMusicHandler:
    """Handles YouTube Music search and autoplay recommendations."""

    def __init__(self):
        self.ytmusic = YTMusic()
        self.played_videos: set[str] = set()

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
        except Exception:
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
        try:
            watch_playlist = self.ytmusic.get_watch_playlist(videoId=video_id)
            tracks = watch_playlist.get("tracks", [])

            recommendations = []
            for track in tracks:
                vid = track.get("videoId")
                if vid and vid != video_id and vid not in self.played_videos:
                    recommendations.append(
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
                    if len(recommendations) >= limit:
                        break

            return recommendations
        except Exception:
            return []

    def mark_played(self, video_id: str) -> None:
        """Mark a video as played to avoid repeating in autoplay."""
        self.played_videos.add(video_id)

    def clear_history(self) -> None:
        """Clear the played videos history."""
        self.played_videos.clear()
