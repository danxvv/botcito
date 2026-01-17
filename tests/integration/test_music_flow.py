"""Integration tests for music playback flow."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from music_player import MusicPlayerManager
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


class TestMusicPlaybackFlow:
    """Integration tests for complete music playback flow."""

    @pytest.mark.asyncio
    async def test_add_and_play_single_song(self, sample_songs):
        """Test adding a song and playing it."""
        manager = MusicPlayerManager()
        guild_id = 12345

        # Setup mock voice client
        player = manager.get_player(guild_id)
        mock_vc = MagicMock()
        mock_vc.is_connected.return_value = True
        mock_vc.loop = asyncio.get_event_loop()
        player.voice_client = mock_vc

        # Add song to queue
        position = await manager.add_to_queue(guild_id, sample_songs[0])
        assert position == 1

        # Play the song
        with patch("music_player.discord.FFmpegOpusAudio"):
            song = await manager.play_next(guild_id)

        assert song == sample_songs[0]
        assert manager.get_current_song(guild_id) == sample_songs[0]
        assert len(manager.get_queue(guild_id)) == 0  # Queue should be empty

    @pytest.mark.asyncio
    async def test_queue_multiple_songs(self, sample_songs):
        """Test queueing multiple songs maintains order."""
        manager = MusicPlayerManager()
        guild_id = 12345

        for i, song in enumerate(sample_songs):
            pos = await manager.add_to_queue(guild_id, song)
            assert pos == i + 1

        queue = manager.get_queue(guild_id)
        assert len(queue) == 3
        assert queue[0].video_id == "vid1"
        assert queue[1].video_id == "vid2"
        assert queue[2].video_id == "vid3"

    @pytest.mark.asyncio
    async def test_play_through_queue(self, sample_songs):
        """Test playing through entire queue."""
        manager = MusicPlayerManager()
        guild_id = 12345

        player = manager.get_player(guild_id)
        mock_vc = MagicMock()
        mock_vc.is_connected.return_value = True
        mock_vc.loop = asyncio.get_event_loop()
        player.voice_client = mock_vc

        # Add all songs
        for song in sample_songs:
            await manager.add_to_queue(guild_id, song)

        # Play through each song
        with patch("music_player.discord.FFmpegOpusAudio"):
            song1 = await manager.play_next(guild_id)
            assert song1.video_id == "vid1"
            assert len(manager.get_queue(guild_id)) == 2

            song2 = await manager.play_next(guild_id)
            assert song2.video_id == "vid2"
            assert len(manager.get_queue(guild_id)) == 1

            song3 = await manager.play_next(guild_id)
            assert song3.video_id == "vid3"
            assert len(manager.get_queue(guild_id)) == 0

    @pytest.mark.asyncio
    async def test_skip_advances_queue(self, sample_songs):
        """Test skipping advances to next song."""
        manager = MusicPlayerManager()
        guild_id = 12345

        player = manager.get_player(guild_id)
        mock_vc = MagicMock()
        mock_vc.is_connected.return_value = True
        mock_vc.is_playing.return_value = True
        mock_vc.loop = asyncio.get_event_loop()
        player.voice_client = mock_vc

        # Add songs
        for song in sample_songs:
            await manager.add_to_queue(guild_id, song)

        # Play first song
        with patch("music_player.discord.FFmpegOpusAudio"):
            await manager.play_next(guild_id)

        # Skip should stop playback (callback triggers next song)
        result = manager.skip(guild_id)
        assert result is True
        mock_vc.stop.assert_called()

    @pytest.mark.asyncio
    async def test_pause_resume_flow(self, sample_songs):
        """Test pausing and resuming playback."""
        manager = MusicPlayerManager()
        guild_id = 12345

        player = manager.get_player(guild_id)
        mock_vc = MagicMock()
        mock_vc.is_connected.return_value = True
        mock_vc.is_playing.return_value = True
        mock_vc.is_paused.return_value = False
        mock_vc.loop = asyncio.get_event_loop()
        player.voice_client = mock_vc

        await manager.add_to_queue(guild_id, sample_songs[0])

        with patch("music_player.discord.FFmpegOpusAudio"):
            await manager.play_next(guild_id)

        # Pause
        result = manager.pause(guild_id)
        assert result is True
        mock_vc.pause.assert_called()

        # Setup for resume
        mock_vc.is_playing.return_value = False
        mock_vc.is_paused.return_value = True

        # Resume
        result = manager.resume(guild_id)
        assert result is True
        mock_vc.resume.assert_called()


class TestAutoplayFlow:
    """Integration tests for autoplay functionality."""

    @pytest.mark.asyncio
    async def test_autoplay_toggle(self, sample_songs):
        """Test toggling autoplay on and off."""
        manager = MusicPlayerManager()
        guild_id = 12345

        # Initially off
        assert manager.get_player(guild_id).autoplay_enabled is False

        # Toggle on
        result = manager.toggle_autoplay(guild_id)
        assert result is True
        assert manager.get_player(guild_id).autoplay_enabled is True

        # Toggle off
        result = manager.toggle_autoplay(guild_id)
        assert result is False
        assert manager.get_player(guild_id).autoplay_enabled is False

    @pytest.mark.asyncio
    async def test_recent_songs_tracked(self, sample_songs):
        """Test recent songs are tracked for recommendations."""
        manager = MusicPlayerManager()
        guild_id = 12345

        player = manager.get_player(guild_id)
        mock_vc = MagicMock()
        mock_vc.is_connected.return_value = True
        mock_vc.loop = asyncio.get_event_loop()
        player.voice_client = mock_vc

        # Add and play songs
        for song in sample_songs:
            await manager.add_to_queue(guild_id, song)

        with patch("music_player.discord.FFmpegOpusAudio"):
            await manager.play_next(guild_id)
            await manager.play_next(guild_id)

        # Recent songs should be tracked
        assert "vid1" in player.recent_songs
        assert "vid2" in player.recent_songs

    @pytest.mark.asyncio
    async def test_clear_history(self, sample_songs):
        """Test clearing history clears recent songs."""
        manager = MusicPlayerManager()
        guild_id = 12345

        player = manager.get_player(guild_id)
        player.recent_songs.append("vid1")
        player.recent_songs.append("vid2")
        player.autoplay_queue.append(sample_songs[0])

        manager.clear_history(guild_id)

        assert len(player.recent_songs) == 0
        assert len(player.autoplay_queue) == 0


class TestMultiGuildIsolation:
    """Integration tests for multi-guild state isolation."""

    @pytest.mark.asyncio
    async def test_different_guilds_independent_queues(self, sample_songs):
        """Test different guilds have independent queues."""
        manager = MusicPlayerManager()
        guild_1 = 111
        guild_2 = 222

        # Add different songs to different guilds
        await manager.add_to_queue(guild_1, sample_songs[0])
        await manager.add_to_queue(guild_2, sample_songs[1])
        await manager.add_to_queue(guild_2, sample_songs[2])

        queue_1 = manager.get_queue(guild_1)
        queue_2 = manager.get_queue(guild_2)

        assert len(queue_1) == 1
        assert len(queue_2) == 2
        assert queue_1[0].video_id == "vid1"
        assert queue_2[0].video_id == "vid2"

    @pytest.mark.asyncio
    async def test_different_guilds_independent_autoplay(self):
        """Test different guilds have independent autoplay settings."""
        manager = MusicPlayerManager()
        guild_1 = 111
        guild_2 = 222

        manager.toggle_autoplay(guild_1)

        assert manager.get_player(guild_1).autoplay_enabled is True
        assert manager.get_player(guild_2).autoplay_enabled is False

    @pytest.mark.asyncio
    async def test_disconnect_one_guild_preserves_other(self, sample_songs):
        """Test disconnecting one guild preserves other guild's state."""
        manager = MusicPlayerManager()
        guild_1 = 111
        guild_2 = 222

        # Setup both guilds
        for guild_id in [guild_1, guild_2]:
            player = manager.get_player(guild_id)
            player.voice_client = MagicMock()
            player.voice_client.is_playing.return_value = False
            player.voice_client.disconnect = AsyncMock()

        await manager.add_to_queue(guild_1, sample_songs[0])
        await manager.add_to_queue(guild_2, sample_songs[1])

        # Disconnect guild 1
        await manager.disconnect(guild_1)

        # Guild 1 should be cleared
        assert len(manager.get_queue(guild_1)) == 0

        # Guild 2 should be preserved
        assert len(manager.get_queue(guild_2)) == 1
        assert manager.get_queue(guild_2)[0].video_id == "vid2"
