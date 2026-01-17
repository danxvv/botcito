"""Mock object factories for testing."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, PropertyMock


def create_mock_voice_channel(
    channel_id: int = 123456789,
    channel_name: str = "General",
    guild_id: int = 987654321,
    guild_name: str = "Test Server",
) -> MagicMock:
    """Create a mock Discord voice channel."""
    channel = MagicMock()
    channel.id = channel_id
    channel.name = channel_name
    channel.guild = MagicMock()
    channel.guild.id = guild_id
    channel.guild.name = guild_name
    return channel


def create_mock_voice_client(
    is_connected: bool = True,
    is_playing: bool = False,
    is_paused: bool = False,
) -> MagicMock:
    """Create a mock Discord voice client."""
    client = MagicMock()
    client.is_connected.return_value = is_connected
    client.is_playing.return_value = is_playing
    client.is_paused.return_value = is_paused
    client.play = MagicMock()
    client.stop = MagicMock()
    client.pause = MagicMock()
    client.resume = MagicMock()
    client.disconnect = AsyncMock()
    return client


def create_mock_member(
    user_id: int = 111222333,
    username: str = "TestUser",
    in_voice: bool = True,
    voice_channel_id: int = 123456789,
) -> MagicMock:
    """Create a mock Discord guild member."""
    member = MagicMock()
    member.id = user_id
    member.name = username
    member.display_name = username

    if in_voice:
        member.voice = MagicMock()
        member.voice.channel = MagicMock()
        member.voice.channel.id = voice_channel_id
        member.voice.channel.name = "General"
    else:
        member.voice = None

    return member


def create_mock_interaction(
    user_id: int = 111222333,
    guild_id: int = 987654321,
    user_in_voice: bool = True,
    bot_in_voice: bool = False,
) -> MagicMock:
    """Create a mock Discord interaction for slash commands."""
    interaction = MagicMock()

    # User setup
    interaction.user = create_mock_member(user_id=user_id, in_voice=user_in_voice)

    # Guild setup
    interaction.guild = MagicMock()
    interaction.guild.id = guild_id
    interaction.guild.name = "Test Server"

    if bot_in_voice:
        interaction.guild.voice_client = create_mock_voice_client()
    else:
        interaction.guild.voice_client = None

    # Response methods
    interaction.response = MagicMock()
    interaction.response.defer = AsyncMock()
    interaction.response.send_message = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    interaction.edit_original_response = AsyncMock()

    return interaction


def create_mock_ytdl(extract_info_result: dict[str, Any] | None = None) -> MagicMock:
    """Create a mock yt-dlp YoutubeDL instance."""
    ytdl = MagicMock()

    if extract_info_result is not None:
        ytdl.extract_info.return_value = extract_info_result
    else:
        ytdl.extract_info.return_value = {
            "id": "dQw4w9WgXcQ",
            "title": "Never Gonna Give You Up",
            "duration": 212,
            "thumbnail": "https://i.ytimg.com/vi/dQw4w9WgXcQ/maxresdefault.jpg",
            "webpage_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "url": "https://manifest.googlevideo.com/test",
        }

    return ytdl


def create_mock_ytmusic(
    search_results: list[dict] | None = None,
    watch_playlist: dict | None = None,
    search_suggestions: list[str] | None = None,
) -> MagicMock:
    """Create a mock ytmusicapi YTMusic instance."""
    ytmusic = MagicMock()

    ytmusic.search.return_value = search_results or []
    ytmusic.get_watch_playlist.return_value = watch_playlist or {"tracks": []}
    ytmusic.get_search_suggestions.return_value = search_suggestions or []

    return ytmusic


def create_mock_ffmpeg_audio() -> MagicMock:
    """Create a mock FFmpegOpusAudio source."""
    audio = MagicMock()
    audio.read.return_value = b"\x00" * 3840  # Silence
    audio.cleanup = MagicMock()
    audio.is_opus.return_value = True
    return audio


def create_mock_agno_agent(response_content: str = "Test response") -> MagicMock:
    """Create a mock Agno Agent instance."""
    agent = MagicMock()

    # Mock the arun method for async streaming
    async def mock_arun(*args, **kwargs):
        class MockResponse:
            content = response_content
            messages = [MagicMock(content=response_content)]

        return MockResponse()

    agent.arun = AsyncMock(side_effect=mock_arun)

    return agent


def create_mock_mcp_tools() -> MagicMock:
    """Create a mock MCPTools instance."""
    tools = MagicMock()
    tools.tools = [
        MagicMock(name="web_search", description="Search the web"),
        MagicMock(name="get_contents", description="Get page contents"),
    ]
    return tools
