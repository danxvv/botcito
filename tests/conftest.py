"""Shared pytest fixtures for the botcito test suite."""

import asyncio
from collections.abc import AsyncGenerator, Generator
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from youtube import SongInfo


# ============================================================================
# Discord.py Mocks
# ============================================================================


@pytest.fixture
def mock_voice_channel():
    """Mock Discord voice channel."""
    channel = MagicMock()
    channel.id = 123456789
    channel.name = "General"
    channel.guild.id = 987654321
    channel.guild.name = "Test Server"
    return channel


@pytest.fixture
def mock_voice_client():
    """Mock Discord voice client."""
    client = MagicMock()
    client.is_connected.return_value = True
    client.is_playing.return_value = False
    client.is_paused.return_value = False
    client.play = MagicMock()
    client.stop = MagicMock()
    client.pause = MagicMock()
    client.resume = MagicMock()
    client.disconnect = AsyncMock()
    return client


@pytest.fixture
def mock_member():
    """Mock Discord guild member."""
    member = MagicMock()
    member.id = 111222333
    member.name = "TestUser"
    member.voice = MagicMock()
    member.voice.channel = MagicMock()
    member.voice.channel.id = 123456789
    member.voice.channel.name = "General"
    return member


@pytest.fixture
def mock_interaction(mock_member, mock_voice_channel):
    """Mock Discord interaction for slash commands."""
    interaction = MagicMock()
    interaction.user = mock_member
    interaction.guild = MagicMock()
    interaction.guild.id = 987654321
    interaction.guild.voice_client = None
    interaction.response = MagicMock()
    interaction.response.defer = AsyncMock()
    interaction.response.send_message = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    interaction.edit_original_response = AsyncMock()
    return interaction


# ============================================================================
# YouTube/yt-dlp Mocks
# ============================================================================


@pytest.fixture
def sample_song_info():
    """Sample SongInfo for testing."""
    return SongInfo(
        url="https://manifest.googlevideo.com/api/manifest/hls_playlist/test",
        title="Never Gonna Give You Up",
        duration=212,
        thumbnail="https://i.ytimg.com/vi/dQw4w9WgXcQ/maxresdefault.jpg",
        video_id="dQw4w9WgXcQ",
        webpage_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    )


@pytest.fixture
def sample_song_info_2():
    """Second sample SongInfo for queue testing."""
    return SongInfo(
        url="https://manifest.googlevideo.com/api/manifest/hls_playlist/test2",
        title="Bohemian Rhapsody",
        duration=354,
        thumbnail="https://i.ytimg.com/vi/fJ9rUzIMcZQ/maxresdefault.jpg",
        video_id="fJ9rUzIMcZQ",
        webpage_url="https://www.youtube.com/watch?v=fJ9rUzIMcZQ",
    )


@pytest.fixture
def sample_song_info_3():
    """Third sample SongInfo for queue testing."""
    return SongInfo(
        url="https://manifest.googlevideo.com/api/manifest/hls_playlist/test3",
        title="Stairway to Heaven",
        duration=482,
        thumbnail="https://i.ytimg.com/vi/QkF3oxziUI4/maxresdefault.jpg",
        video_id="QkF3oxziUI4",
        webpage_url="https://www.youtube.com/watch?v=QkF3oxziUI4",
    )


@pytest.fixture
def mock_ytdl_extract_info():
    """Mock yt-dlp extraction result."""
    return {
        "id": "dQw4w9WgXcQ",
        "title": "Rick Astley - Never Gonna Give You Up",
        "duration": 212,
        "thumbnail": "https://i.ytimg.com/vi/dQw4w9WgXcQ/maxresdefault.jpg",
        "webpage_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "url": "https://manifest.googlevideo.com/api/manifest/hls_playlist/test",
        "formats": [
            {
                "format_id": "251",
                "acodec": "opus",
                "url": "https://manifest.googlevideo.com/api/manifest/hls_playlist/test",
            }
        ],
    }


@pytest.fixture
def mock_ytdl_playlist_info():
    """Mock yt-dlp playlist extraction result."""
    return {
        "_type": "playlist",
        "id": "PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf",
        "title": "Test Playlist",
        "entries": [
            {
                "id": "dQw4w9WgXcQ",
                "title": "Never Gonna Give You Up",
                "duration": 212,
            },
            {
                "id": "fJ9rUzIMcZQ",
                "title": "Bohemian Rhapsody",
                "duration": 354,
            },
        ],
    }


@pytest.fixture
def mock_ytdl_search_result():
    """Mock yt-dlp search result."""
    return {
        "id": "dQw4w9WgXcQ",
        "title": "Rick Astley - Never Gonna Give You Up",
        "duration": 212,
        "thumbnail": "https://i.ytimg.com/vi/dQw4w9WgXcQ/maxresdefault.jpg",
        "webpage_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "url": "https://manifest.googlevideo.com/api/manifest/hls_playlist/test",
    }


# ============================================================================
# YouTube Music API Mocks
# ============================================================================


@pytest.fixture
def mock_ytmusic_search_results():
    """Mock ytmusicapi search results."""
    return [
        {
            "videoId": "dQw4w9WgXcQ",
            "title": "Never Gonna Give You Up",
            "artists": [{"name": "Rick Astley"}],
            "duration": "3:32",
            "thumbnails": [{"url": "https://i.ytimg.com/vi/dQw4w9WgXcQ/default.jpg"}],
        },
        {
            "videoId": "fJ9rUzIMcZQ",
            "title": "Bohemian Rhapsody",
            "artists": [{"name": "Queen"}],
            "duration": "5:54",
            "thumbnails": [{"url": "https://i.ytimg.com/vi/fJ9rUzIMcZQ/default.jpg"}],
        },
    ]


@pytest.fixture
def mock_ytmusic_recommendations():
    """Mock ytmusicapi watch playlist (recommendations)."""
    return {
        "tracks": [
            {
                "videoId": "abc123",
                "title": "Take On Me",
                "artists": [{"name": "a-ha"}],
                "length": "3:45",
                "thumbnail": [{"url": "https://i.ytimg.com/vi/abc123/default.jpg"}],
            },
            {
                "videoId": "def456",
                "title": "Sweet Dreams",
                "artists": [{"name": "Eurythmics"}],
                "length": "3:36",
                "thumbnail": [{"url": "https://i.ytimg.com/vi/def456/default.jpg"}],
            },
            {
                "videoId": "ghi789",
                "title": "Africa",
                "artists": [{"name": "Toto"}],
                "length": "4:35",
                "thumbnail": [{"url": "https://i.ytimg.com/vi/ghi789/default.jpg"}],
            },
        ]
    }


# ============================================================================
# Game Agent Mocks
# ============================================================================


@pytest.fixture
def mock_api_keys():
    """Mock API keys for game agent."""
    return {
        "EXA_API_KEY": "test-exa-api-key-12345",
        "OPENROUTER_API_KEY": "test-openrouter-api-key-12345",
    }


@pytest.fixture
def mock_mcp_tools():
    """Mock MCP tools for game agent."""
    tools = MagicMock()
    tools.tools = [
        MagicMock(name="web_search"),
        MagicMock(name="get_contents"),
    ]
    return tools


@pytest.fixture
def mock_agent_response():
    """Mock Agno agent streaming response."""

    @dataclass
    class MockRunResponseMessage:
        content: str

    @dataclass
    class MockRunResponse:
        content: str
        messages: list

    return MockRunResponse(
        content="Based on my research, here's how to beat the boss...",
        messages=[
            MockRunResponseMessage(content="Based on my research, "),
            MockRunResponseMessage(content="here's how to beat the boss..."),
        ],
    )


# ============================================================================
# Database Fixtures
# ============================================================================


@pytest.fixture
def temp_settings_db(tmp_path):
    """Create a temporary settings database."""
    db_path = tmp_path / "data" / "settings.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path


@pytest.fixture
def temp_memory_db(tmp_path):
    """Create a temporary agent memory database."""
    db_path = tmp_path / "data" / "game_agent_memory.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path


# ============================================================================
# Async Test Support
# ============================================================================


@pytest.fixture
def event_loop():
    """Create an event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ============================================================================
# Music Player Fixtures
# ============================================================================


@pytest.fixture
def fresh_player_manager():
    """Create a fresh MusicPlayerManager for testing."""
    from music_player import MusicPlayerManager

    manager = MusicPlayerManager()
    return manager


@pytest.fixture
def player_with_songs(fresh_player_manager, sample_song_info, sample_song_info_2):
    """Player manager with some songs in queue."""
    guild_id = 987654321
    fresh_player_manager.add_to_queue(guild_id, sample_song_info)
    fresh_player_manager.add_to_queue(guild_id, sample_song_info_2)
    return fresh_player_manager, guild_id
