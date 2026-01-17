"""Sample song data for testing."""

from youtube import SongInfo

# Sample songs for testing
SAMPLE_SONGS = [
    SongInfo(
        url="https://manifest.googlevideo.com/api/manifest/hls_playlist/song1",
        title="Never Gonna Give You Up",
        duration=212,
        thumbnail="https://i.ytimg.com/vi/dQw4w9WgXcQ/maxresdefault.jpg",
        video_id="dQw4w9WgXcQ",
        webpage_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    ),
    SongInfo(
        url="https://manifest.googlevideo.com/api/manifest/hls_playlist/song2",
        title="Bohemian Rhapsody",
        duration=354,
        thumbnail="https://i.ytimg.com/vi/fJ9rUzIMcZQ/maxresdefault.jpg",
        video_id="fJ9rUzIMcZQ",
        webpage_url="https://www.youtube.com/watch?v=fJ9rUzIMcZQ",
    ),
    SongInfo(
        url="https://manifest.googlevideo.com/api/manifest/hls_playlist/song3",
        title="Stairway to Heaven",
        duration=482,
        thumbnail="https://i.ytimg.com/vi/QkF3oxziUI4/maxresdefault.jpg",
        video_id="QkF3oxziUI4",
        webpage_url="https://www.youtube.com/watch?v=QkF3oxziUI4",
    ),
    SongInfo(
        url="https://manifest.googlevideo.com/api/manifest/hls_playlist/song4",
        title="Hotel California",
        duration=391,
        thumbnail="https://i.ytimg.com/vi/09839DpTctU/maxresdefault.jpg",
        video_id="09839DpTctU",
        webpage_url="https://www.youtube.com/watch?v=09839DpTctU",
    ),
    SongInfo(
        url="https://manifest.googlevideo.com/api/manifest/hls_playlist/song5",
        title="Sweet Child O' Mine",
        duration=303,
        thumbnail="https://i.ytimg.com/vi/1w7OgIMMRc4/maxresdefault.jpg",
        video_id="1w7OgIMMRc4",
        webpage_url="https://www.youtube.com/watch?v=1w7OgIMMRc4",
    ),
]


def get_sample_song(index: int = 0) -> SongInfo:
    """Get a sample song by index."""
    return SAMPLE_SONGS[index % len(SAMPLE_SONGS)]


def get_sample_songs(count: int = 3) -> list[SongInfo]:
    """Get multiple sample songs."""
    return [get_sample_song(i) for i in range(count)]
