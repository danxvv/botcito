"""YouTube Music tools for the music discovery agent."""

import json
import logging

from ytmusicapi import YTMusic

logger = logging.getLogger(__name__)

# Module-level YTMusic instance (thread-safe for read-only searches)
_ytmusic = YTMusic()


def search_songs(query: str, limit: int = 10) -> str:
    """Search YouTube Music for songs matching a query.

    Use this to find songs based on artist names, song titles, genres,
    or descriptive queries. Returns song metadata including videoId,
    title, artist, and duration.

    Args:
        query: Search query (artist name, song title, genre, mood, etc.)
        limit: Maximum number of results (default 10, max 20)

    Returns:
        JSON string with list of songs, each having videoId, title, artist, duration
    """
    limit = min(max(1, limit), 20)

    try:
        results = _ytmusic.search(query, filter="songs", limit=limit)
        songs = [
            {
                "videoId": r["videoId"],
                "title": r["title"],
                "artist": r["artists"][0]["name"] if r.get("artists") and r["artists"] else "Unknown",
                "duration": r.get("duration", ""),
                "album": r.get("album", {}).get("name", "") if r.get("album") else "",
            }
            for r in results
            if r.get("videoId")
        ]
        return json.dumps(songs, ensure_ascii=False)
    except Exception as e:
        logger.exception("Failed to search songs for query '%s': %s", query, e)
        return json.dumps({"error": str(e)})


def get_song_recommendations(video_id: str, limit: int = 10) -> str:
    """Get song recommendations based on a specific song's video ID.

    Use this to find songs similar to a known song. Useful for
    expanding a discovery list based on a good match.

    Args:
        video_id: YouTube video ID (11 characters) of a reference song
        limit: Maximum number of recommendations (default 10)

    Returns:
        JSON string with list of recommended songs
    """
    limit = min(max(1, limit), 20)

    try:
        watch_playlist = _ytmusic.get_watch_playlist(videoId=video_id)
        tracks = watch_playlist.get("tracks", [])
        songs = []
        for track in tracks:
            vid = track.get("videoId")
            if vid and vid != video_id:
                songs.append({
                    "videoId": vid,
                    "title": track.get("title", "Unknown"),
                    "artist": (
                        track["artists"][0]["name"]
                        if track.get("artists") and track["artists"]
                        else "Unknown"
                    ),
                    "duration": track.get("length", ""),
                })
            if len(songs) >= limit:
                break
        return json.dumps(songs, ensure_ascii=False)
    except Exception as e:
        logger.exception("Failed to get recommendations for '%s': %s", video_id, e)
        return json.dumps({"error": str(e)})
