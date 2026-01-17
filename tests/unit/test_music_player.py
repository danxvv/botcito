"""Unit tests for music_player.py - Queue and playback management."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from music_player import GuildPlayer, MusicPlayerManager
from youtube import SongInfo


@pytest.fixture
def sample_songs():
    """Create sample songs for testing."""
    return [
        SongInfo(
            url="https://stream1.com",
            title="Song 1",
            duration=180,
            thumbnail="",
            video_id="vid1",
            webpage_url="https://youtube.com/watch?v=vid1",
        ),
        SongInfo(
            url="https://stream2.com",
            title="Song 2",
            duration=200,
            thumbnail="",
            video_id="vid2",
            webpage_url="https://youtube.com/watch?v=vid2",
        ),
        SongInfo(
            url="https://stream3.com",
            title="Song 3",
            duration=220,
            thumbnail="",
            video_id="vid3",
            webpage_url="https://youtube.com/watch?v=vid3",
        ),
    ]


class TestGuildPlayer:
    """Tests for GuildPlayer dataclass."""

    def test_default_values(self):
        """Test GuildPlayer has correct defaults."""
        player = GuildPlayer()
        assert player.voice_client is None
        assert len(player.queue) == 0
        assert player.current_song is None
        assert player.autoplay_enabled is False
        assert len(player.autoplay_queue) == 0
        assert len(player.recent_songs) == 0


class TestMusicPlayerManagerBasics:
    """Tests for basic MusicPlayerManager operations."""

    def test_init_empty_players(self):
        """Test manager initializes with no players."""
        manager = MusicPlayerManager()
        assert len(manager.players) == 0

    def test_get_player_creates_new(self):
        """Test get_player creates new player for unknown guild."""
        manager = MusicPlayerManager()
        player = manager.get_player(12345)

        assert 12345 in manager.players
        assert isinstance(player, GuildPlayer)

    def test_get_player_returns_existing(self):
        """Test get_player returns same player for same guild."""
        manager = MusicPlayerManager()
        player1 = manager.get_player(12345)
        player2 = manager.get_player(12345)

        assert player1 is player2

    def test_different_guilds_different_players(self):
        """Test different guilds get different players."""
        manager = MusicPlayerManager()
        player1 = manager.get_player(111)
        player2 = manager.get_player(222)

        assert player1 is not player2


class TestQueueManagement:
    """Tests for queue management operations."""

    @pytest.mark.asyncio
    async def test_add_to_queue_returns_position(self, sample_songs):
        """Test add_to_queue returns correct position."""
        manager = MusicPlayerManager()
        guild_id = 12345

        pos1 = await manager.add_to_queue(guild_id, sample_songs[0])
        pos2 = await manager.add_to_queue(guild_id, sample_songs[1])
        pos3 = await manager.add_to_queue(guild_id, sample_songs[2])

        assert pos1 == 1
        assert pos2 == 2
        assert pos3 == 3

    @pytest.mark.asyncio
    async def test_add_to_queue_appends_song(self, sample_songs):
        """Test add_to_queue adds song to end of queue."""
        manager = MusicPlayerManager()
        guild_id = 12345

        await manager.add_to_queue(guild_id, sample_songs[0])
        await manager.add_to_queue(guild_id, sample_songs[1])

        queue = manager.get_queue(guild_id)
        assert len(queue) == 2
        assert queue[0].video_id == "vid1"
        assert queue[1].video_id == "vid2"

    def test_get_queue_returns_list(self, sample_songs):
        """Test get_queue returns list copy of queue."""
        manager = MusicPlayerManager()
        guild_id = 12345
        player = manager.get_player(guild_id)

        player.queue.append(sample_songs[0])
        player.queue.append(sample_songs[1])

        queue = manager.get_queue(guild_id)

        assert isinstance(queue, list)
        assert len(queue) == 2
        # Modifying returned list shouldn't affect internal queue
        queue.clear()
        assert len(player.queue) == 2

    def test_get_queue_empty(self):
        """Test get_queue returns empty list for new guild."""
        manager = MusicPlayerManager()
        queue = manager.get_queue(99999)

        assert queue == []


class TestAutoplayManagement:
    """Tests for autoplay toggle and history."""

    def test_toggle_autoplay_enables(self):
        """Test toggle_autoplay enables when disabled."""
        manager = MusicPlayerManager()
        guild_id = 12345

        result = manager.toggle_autoplay(guild_id)

        assert result is True
        assert manager.get_player(guild_id).autoplay_enabled is True

    def test_toggle_autoplay_disables(self):
        """Test toggle_autoplay disables when enabled."""
        manager = MusicPlayerManager()
        guild_id = 12345

        manager.toggle_autoplay(guild_id)  # Enable
        result = manager.toggle_autoplay(guild_id)  # Disable

        assert result is False
        assert manager.get_player(guild_id).autoplay_enabled is False

    def test_clear_history_clears_all(self, sample_songs):
        """Test clear_history clears history and queues."""
        manager = MusicPlayerManager()
        guild_id = 12345
        player = manager.get_player(guild_id)

        # Add some state
        player.recent_songs.append("vid1")
        player.recent_songs.append("vid2")
        player.autoplay_queue.append(sample_songs[0])

        manager.clear_history(guild_id)

        assert len(player.recent_songs) == 0
        assert len(player.autoplay_queue) == 0


class TestPlaybackControls:
    """Tests for playback control operations."""

    def test_skip_when_playing(self):
        """Test skip returns True when playing."""
        manager = MusicPlayerManager()
        guild_id = 12345
        player = manager.get_player(guild_id)

        # Mock voice client
        player.voice_client = MagicMock()
        player.voice_client.is_playing.return_value = True

        result = manager.skip(guild_id)

        assert result is True
        player.voice_client.stop.assert_called_once()

    def test_skip_when_not_playing(self):
        """Test skip returns False when not playing."""
        manager = MusicPlayerManager()
        guild_id = 12345
        player = manager.get_player(guild_id)

        player.voice_client = MagicMock()
        player.voice_client.is_playing.return_value = False

        result = manager.skip(guild_id)

        assert result is False

    def test_skip_no_voice_client(self):
        """Test skip returns False when no voice client."""
        manager = MusicPlayerManager()
        result = manager.skip(12345)

        assert result is False

    def test_pause_when_playing(self):
        """Test pause returns True when playing."""
        manager = MusicPlayerManager()
        guild_id = 12345
        player = manager.get_player(guild_id)

        player.voice_client = MagicMock()
        player.voice_client.is_playing.return_value = True

        result = manager.pause(guild_id)

        assert result is True
        player.voice_client.pause.assert_called_once()

    def test_pause_when_not_playing(self):
        """Test pause returns False when not playing."""
        manager = MusicPlayerManager()
        guild_id = 12345
        player = manager.get_player(guild_id)

        player.voice_client = MagicMock()
        player.voice_client.is_playing.return_value = False

        result = manager.pause(guild_id)

        assert result is False

    def test_resume_when_paused(self):
        """Test resume returns True when paused."""
        manager = MusicPlayerManager()
        guild_id = 12345
        player = manager.get_player(guild_id)

        player.voice_client = MagicMock()
        player.voice_client.is_paused.return_value = True

        result = manager.resume(guild_id)

        assert result is True
        player.voice_client.resume.assert_called_once()

    def test_resume_when_not_paused(self):
        """Test resume returns False when not paused."""
        manager = MusicPlayerManager()
        guild_id = 12345
        player = manager.get_player(guild_id)

        player.voice_client = MagicMock()
        player.voice_client.is_paused.return_value = False

        result = manager.resume(guild_id)

        assert result is False


class TestPlaybackState:
    """Tests for playback state queries."""

    def test_get_current_song(self, sample_songs):
        """Test get_current_song returns current song."""
        manager = MusicPlayerManager()
        guild_id = 12345
        player = manager.get_player(guild_id)

        player.current_song = sample_songs[0]

        result = manager.get_current_song(guild_id)

        assert result == sample_songs[0]

    def test_get_current_song_none(self):
        """Test get_current_song returns None when nothing playing."""
        manager = MusicPlayerManager()
        result = manager.get_current_song(12345)

        assert result is None

    def test_is_playing_when_playing(self):
        """Test is_playing returns True when playing."""
        manager = MusicPlayerManager()
        guild_id = 12345
        player = manager.get_player(guild_id)

        player.voice_client = MagicMock()
        player.voice_client.is_playing.return_value = True
        player.voice_client.is_paused.return_value = False

        assert manager.is_playing(guild_id) is True

    def test_is_playing_when_paused(self):
        """Test is_playing returns True when paused."""
        manager = MusicPlayerManager()
        guild_id = 12345
        player = manager.get_player(guild_id)

        player.voice_client = MagicMock()
        player.voice_client.is_playing.return_value = False
        player.voice_client.is_paused.return_value = True

        assert manager.is_playing(guild_id) is True

    def test_is_playing_when_stopped(self):
        """Test is_playing returns False when stopped."""
        manager = MusicPlayerManager()
        guild_id = 12345
        player = manager.get_player(guild_id)

        player.voice_client = MagicMock()
        player.voice_client.is_playing.return_value = False
        player.voice_client.is_paused.return_value = False

        assert manager.is_playing(guild_id) is False

    def test_is_playing_no_voice_client(self):
        """Test is_playing returns False when no voice client."""
        manager = MusicPlayerManager()
        assert manager.is_playing(12345) is False


class TestBlendedRecommendations:
    """Tests for _get_blended_recommendations."""

    def test_blended_recommendations_empty_recent(self):
        """Test empty list when no recent songs."""
        manager = MusicPlayerManager()
        player = manager.get_player(12345)

        result = manager._get_blended_recommendations(player, limit=5)

        assert result == []

    def test_blended_recommendations_deduplicates(self):
        """Test duplicate recommendations are removed."""
        manager = MusicPlayerManager()
        player = manager.get_player(12345)

        # Add recent songs
        player.recent_songs.append("vid1")
        player.recent_songs.append("vid2")

        # Mock ytmusic to return overlapping recommendations
        player.ytmusic.get_recommendations = MagicMock(
            return_value=[
                {"videoId": "rec1", "title": "Rec 1", "artist": "Artist"},
                {"videoId": "rec2", "title": "Rec 2", "artist": "Artist"},
            ]
        )

        result = manager._get_blended_recommendations(player, limit=10)

        # Check no duplicates
        video_ids = [r["videoId"] for r in result]
        assert len(video_ids) == len(set(video_ids))


class TestPlayNext:
    """Tests for play_next method."""

    @pytest.mark.asyncio
    async def test_play_next_returns_none_no_voice_client(self, sample_songs):
        """Test play_next returns None when no voice client."""
        manager = MusicPlayerManager()
        guild_id = 12345

        await manager.add_to_queue(guild_id, sample_songs[0])

        result = await manager.play_next(guild_id)

        assert result is None

    @pytest.mark.asyncio
    async def test_play_next_returns_none_disconnected(self, sample_songs):
        """Test play_next returns None when voice client disconnected."""
        manager = MusicPlayerManager()
        guild_id = 12345
        player = manager.get_player(guild_id)

        player.voice_client = MagicMock()
        player.voice_client.is_connected.return_value = False

        await manager.add_to_queue(guild_id, sample_songs[0])

        result = await manager.play_next(guild_id)

        assert result is None

    @pytest.mark.asyncio
    async def test_play_next_plays_from_queue(self, sample_songs):
        """Test play_next plays song from queue."""
        manager = MusicPlayerManager()
        guild_id = 12345
        player = manager.get_player(guild_id)

        # Setup mock voice client
        player.voice_client = MagicMock()
        player.voice_client.is_connected.return_value = True
        player.voice_client.loop = asyncio.get_event_loop()

        await manager.add_to_queue(guild_id, sample_songs[0])

        with patch("music_player.discord.FFmpegOpusAudio"):
            result = await manager.play_next(guild_id)

        assert result == sample_songs[0]
        assert player.current_song == sample_songs[0]
        assert len(player.queue) == 0

    @pytest.mark.asyncio
    async def test_play_next_tracks_recent_songs(self, sample_songs):
        """Test play_next adds song to recent songs."""
        manager = MusicPlayerManager()
        guild_id = 12345
        player = manager.get_player(guild_id)

        player.voice_client = MagicMock()
        player.voice_client.is_connected.return_value = True
        player.voice_client.loop = asyncio.get_event_loop()

        await manager.add_to_queue(guild_id, sample_songs[0])

        with patch("music_player.discord.FFmpegOpusAudio"):
            await manager.play_next(guild_id)

        assert "vid1" in player.recent_songs


class TestConnect:
    """Tests for connect method."""

    @pytest.mark.asyncio
    async def test_connect_new_channel(self):
        """Test connecting to a new voice channel."""
        manager = MusicPlayerManager()
        guild_id = 12345

        mock_channel = MagicMock()
        mock_channel.connect = AsyncMock(return_value=MagicMock())

        result = await manager.connect(guild_id, mock_channel)

        mock_channel.connect.assert_called_once()
        assert manager.get_player(guild_id).voice_client is not None

    @pytest.mark.asyncio
    async def test_connect_already_connected_same_channel(self):
        """Test connect returns existing client when already in same channel."""
        manager = MusicPlayerManager()
        guild_id = 12345
        player = manager.get_player(guild_id)

        mock_vc = MagicMock()
        mock_vc.is_connected.return_value = True
        mock_vc.channel.id = 111

        player.voice_client = mock_vc

        mock_channel = MagicMock()
        mock_channel.id = 111

        result = await manager.connect(guild_id, mock_channel)

        assert result == mock_vc
        mock_vc.move_to.assert_not_called()

    @pytest.mark.asyncio
    async def test_connect_move_to_different_channel(self):
        """Test connect moves to different channel when already connected."""
        manager = MusicPlayerManager()
        guild_id = 12345
        player = manager.get_player(guild_id)

        mock_vc = MagicMock()
        mock_vc.is_connected.return_value = True
        mock_vc.channel.id = 111
        mock_vc.move_to = AsyncMock()

        player.voice_client = mock_vc

        mock_channel = MagicMock()
        mock_channel.id = 222

        result = await manager.connect(guild_id, mock_channel)

        mock_vc.move_to.assert_called_once_with(mock_channel)


class TestDisconnect:
    """Tests for disconnect method."""

    @pytest.mark.asyncio
    async def test_disconnect_clears_state(self, sample_songs):
        """Test disconnect clears all player state."""
        manager = MusicPlayerManager()
        guild_id = 12345
        player = manager.get_player(guild_id)

        # Setup state
        player.voice_client = MagicMock()
        player.voice_client.is_playing.return_value = True
        player.voice_client.disconnect = AsyncMock()
        player.queue.append(sample_songs[0])
        player.autoplay_queue.append(sample_songs[1])
        player.current_song = sample_songs[2]
        player.recent_songs.append("vid1")

        await manager.disconnect(guild_id)

        assert player.voice_client is None
        assert len(player.queue) == 0
        assert len(player.autoplay_queue) == 0
        assert player.current_song is None
        assert len(player.recent_songs) == 0

    @pytest.mark.asyncio
    async def test_disconnect_stops_playback(self, sample_songs):
        """Test disconnect stops current playback."""
        manager = MusicPlayerManager()
        guild_id = 12345
        player = manager.get_player(guild_id)

        mock_vc = MagicMock()
        mock_vc.is_playing.return_value = True
        mock_vc.disconnect = AsyncMock()
        player.voice_client = mock_vc

        await manager.disconnect(guild_id)

        # voice_client is set to None after disconnect, so check the mock directly
        mock_vc.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect_no_voice_client(self):
        """Test disconnect handles no voice client gracefully."""
        manager = MusicPlayerManager()

        # Should not raise
        await manager.disconnect(12345)
