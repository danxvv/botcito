"""Mock API responses for testing."""

# ============================================================================
# yt-dlp Responses
# ============================================================================

YTDL_VIDEO_RESPONSE = {
    "id": "dQw4w9WgXcQ",
    "title": "Rick Astley - Never Gonna Give You Up (Official Music Video)",
    "duration": 212,
    "thumbnail": "https://i.ytimg.com/vi/dQw4w9WgXcQ/maxresdefault.jpg",
    "webpage_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "url": "https://manifest.googlevideo.com/api/manifest/hls_playlist/test",
    "extractor": "youtube",
    "uploader": "Rick Astley",
    "view_count": 1500000000,
    "like_count": 15000000,
    "formats": [
        {
            "format_id": "251",
            "ext": "webm",
            "acodec": "opus",
            "abr": 160,
            "url": "https://manifest.googlevideo.com/api/manifest/hls_playlist/test",
        }
    ],
}

YTDL_SEARCH_RESPONSE = {
    "id": "dQw4w9WgXcQ",
    "title": "Rick Astley - Never Gonna Give You Up",
    "duration": 212,
    "thumbnail": "https://i.ytimg.com/vi/dQw4w9WgXcQ/maxresdefault.jpg",
    "webpage_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "url": "https://manifest.googlevideo.com/api/manifest/hls_playlist/test",
}

YTDL_PLAYLIST_RESPONSE = {
    "_type": "playlist",
    "id": "PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf",
    "title": "80s Greatest Hits",
    "uploader": "Music Collection",
    "entries": [
        {
            "id": "dQw4w9WgXcQ",
            "title": "Never Gonna Give You Up",
            "duration": 212,
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        },
        {
            "id": "fJ9rUzIMcZQ",
            "title": "Bohemian Rhapsody",
            "duration": 354,
            "url": "https://www.youtube.com/watch?v=fJ9rUzIMcZQ",
        },
        {
            "id": "oHg5SJYRHA0",
            "title": "Take On Me",
            "duration": 226,
            "url": "https://www.youtube.com/watch?v=oHg5SJYRHA0",
        },
    ],
}

YTDL_ERROR_RESPONSES = {
    "private_video": {
        "error": "Video unavailable",
        "reason": "This video is private",
    },
    "deleted_video": {
        "error": "Video unavailable",
        "reason": "This video has been removed by the uploader",
    },
    "age_restricted": {
        "error": "Sign in to confirm your age",
        "reason": "This video is age-restricted",
    },
}

# ============================================================================
# YouTube Music API Responses
# ============================================================================

YTMUSIC_SEARCH_RESPONSE = [
    {
        "videoId": "dQw4w9WgXcQ",
        "title": "Never Gonna Give You Up",
        "artists": [{"name": "Rick Astley", "id": "UCuAXFkgsw1L7xaCfnd5JJOw"}],
        "album": {"name": "Whenever You Need Somebody", "id": "MPREb_"},
        "duration": "3:32",
        "duration_seconds": 212,
        "thumbnails": [
            {"url": "https://i.ytimg.com/vi/dQw4w9WgXcQ/default.jpg", "width": 120, "height": 90}
        ],
        "resultType": "song",
    },
    {
        "videoId": "fJ9rUzIMcZQ",
        "title": "Bohemian Rhapsody",
        "artists": [{"name": "Queen", "id": "UCiMhD4jzUqG-IgPzUmmytRQ"}],
        "album": {"name": "A Night at the Opera", "id": "MPREb_2"},
        "duration": "5:54",
        "duration_seconds": 354,
        "thumbnails": [
            {"url": "https://i.ytimg.com/vi/fJ9rUzIMcZQ/default.jpg", "width": 120, "height": 90}
        ],
        "resultType": "song",
    },
]

YTMUSIC_AUTOCOMPLETE_RESPONSE = [
    "never gonna give you up",
    "never gonna give you up lyrics",
    "never gonna give you up rick astley",
    "never let me down",
    "never say never",
]

YTMUSIC_WATCH_PLAYLIST_RESPONSE = {
    "tracks": [
        {
            "videoId": "abc123",
            "title": "Together Forever",
            "artists": [{"name": "Rick Astley"}],
            "album": {"name": "Whenever You Need Somebody"},
            "length": "3:25",
            "thumbnail": [{"url": "https://i.ytimg.com/vi/abc123/default.jpg"}],
        },
        {
            "videoId": "def456",
            "title": "Take On Me",
            "artists": [{"name": "a-ha"}],
            "album": {"name": "Hunting High and Low"},
            "length": "3:45",
            "thumbnail": [{"url": "https://i.ytimg.com/vi/def456/default.jpg"}],
        },
        {
            "videoId": "ghi789",
            "title": "Sweet Dreams",
            "artists": [{"name": "Eurythmics"}],
            "album": {"name": "Sweet Dreams (Are Made of This)"},
            "length": "3:36",
            "thumbnail": [{"url": "https://i.ytimg.com/vi/ghi789/default.jpg"}],
        },
        {
            "videoId": "jkl012",
            "title": "Africa",
            "artists": [{"name": "Toto"}],
            "album": {"name": "Toto IV"},
            "length": "4:35",
            "thumbnail": [{"url": "https://i.ytimg.com/vi/jkl012/default.jpg"}],
        },
    ]
}

# ============================================================================
# Game Agent / Exa API Responses
# ============================================================================

EXA_SEARCH_RESPONSE = {
    "results": [
        {
            "title": "How to Beat the Elden Ring Final Boss - Complete Guide",
            "url": "https://www.ign.com/wikis/elden-ring/final-boss-guide",
            "score": 0.95,
            "text": "The final boss in Elden Ring requires patience and careful timing...",
            "published_date": "2024-01-15",
        },
        {
            "title": "Elden Ring Boss Strategy Guide",
            "url": "https://www.polygon.com/elden-ring-boss-guide",
            "score": 0.89,
            "text": "Learn the attack patterns and find the perfect openings...",
            "published_date": "2024-02-20",
        },
    ],
    "autoprompt_string": "Elden Ring boss strategy guide tips",
}

OPENROUTER_CHAT_RESPONSE = {
    "id": "chatcmpl-123abc",
    "object": "chat.completion",
    "created": 1700000000,
    "model": "google/gemini-2.0-flash-001",
    "choices": [
        {
            "index": 0,
            "message": {
                "role": "assistant",
                "content": "Based on my research, here are the key strategies for this boss...",
            },
            "finish_reason": "stop",
        }
    ],
    "usage": {
        "prompt_tokens": 150,
        "completion_tokens": 200,
        "total_tokens": 350,
    },
}

AGENT_STREAMING_CHUNKS = [
    "Based on my research, ",
    "here are the key strategies:\n\n",
    "1. **Dodge timing** - Wait for the slam attack\n",
    "2. **Weak point** - Attack the glowing orb\n",
    "3. **Phase 2** - Stay close to avoid ranged attacks",
]
