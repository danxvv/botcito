"""Unit tests for main.py - Bot utilities and helper functions."""

import shutil
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from main import check_dependencies, ensure_voice, format_duration


class TestFormatDuration:
    """Tests for format_duration function."""

    def test_format_zero_returns_live(self):
        """Test 0 seconds returns 'Live'."""
        assert format_duration(0) == "Live"

    def test_format_negative_returns_live(self):
        """Test negative seconds returns 'Live'."""
        assert format_duration(-10) == "Live"

    def test_format_seconds_only(self):
        """Test formatting under 1 minute."""
        assert format_duration(45) == "0:45"

    def test_format_minutes_and_seconds(self):
        """Test formatting minutes and seconds."""
        assert format_duration(125) == "2:05"  # 2 min 5 sec
        assert format_duration(180) == "3:00"  # 3 min 0 sec
        assert format_duration(599) == "9:59"  # 9 min 59 sec

    def test_format_hours(self):
        """Test formatting with hours."""
        assert format_duration(3600) == "1:00:00"  # 1 hour
        assert format_duration(3661) == "1:01:01"  # 1h 1m 1s
        assert format_duration(7325) == "2:02:05"  # 2h 2m 5s

    def test_format_pads_correctly(self):
        """Test seconds and minutes are zero-padded."""
        assert format_duration(61) == "1:01"
        assert format_duration(3605) == "1:00:05"


class TestEnsureVoice:
    """Tests for ensure_voice function."""

    @pytest.mark.asyncio
    async def test_user_in_voice_channel(self):
        """Test returns True when user is in voice channel."""
        mock_interaction = MagicMock()
        mock_interaction.user.voice = MagicMock()
        mock_interaction.user.voice.channel = MagicMock()

        result = await ensure_voice(mock_interaction)

        assert result is True
        mock_interaction.response.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_user_not_in_voice_channel(self):
        """Test returns False and sends message when user not in voice."""
        mock_interaction = MagicMock()
        mock_interaction.user.voice = None
        mock_interaction.response.send_message = AsyncMock()

        result = await ensure_voice(mock_interaction)

        assert result is False
        mock_interaction.response.send_message.assert_called_once()
        call_args = mock_interaction.response.send_message.call_args
        assert "voice channel" in call_args[0][0].lower()
        assert call_args[1]["ephemeral"] is True


class TestCheckDependencies:
    """Tests for check_dependencies function."""

    def test_all_deps_present(self):
        """Test empty list when all dependencies present."""
        with patch.object(shutil, "which") as mock_which:
            mock_which.side_effect = lambda x: f"/usr/bin/{x}"

            missing = check_dependencies()

            assert missing == []

    def test_ffmpeg_missing(self):
        """Test FFmpeg reported when missing."""
        with patch.object(shutil, "which") as mock_which:
            def which_side_effect(cmd):
                if cmd == "ffmpeg":
                    return None
                return f"/usr/bin/{cmd}"

            mock_which.side_effect = which_side_effect

            missing = check_dependencies()

            assert len(missing) == 1
            assert "FFmpeg" in missing[0]

    def test_deno_and_node_missing(self):
        """Test Deno/Node reported when both missing."""
        with patch.object(shutil, "which") as mock_which:
            def which_side_effect(cmd):
                if cmd in ("deno", "node"):
                    return None
                return f"/usr/bin/{cmd}"

            mock_which.side_effect = which_side_effect

            missing = check_dependencies()

            assert len(missing) == 1
            assert "Deno" in missing[0] or "Node" in missing[0]

    def test_deno_present_node_missing(self):
        """Test no error when Deno present but Node missing."""
        with patch.object(shutil, "which") as mock_which:
            def which_side_effect(cmd):
                if cmd == "node":
                    return None
                return f"/usr/bin/{cmd}"

            mock_which.side_effect = which_side_effect

            missing = check_dependencies()

            # Should be fine - deno is present
            deno_node_missing = [m for m in missing if "Deno" in m or "Node" in m]
            assert len(deno_node_missing) == 0

    def test_node_present_deno_missing(self):
        """Test no error when Node present but Deno missing."""
        with patch.object(shutil, "which") as mock_which:
            def which_side_effect(cmd):
                if cmd == "deno":
                    return None
                return f"/usr/bin/{cmd}"

            mock_which.side_effect = which_side_effect

            missing = check_dependencies()

            # Should be fine - node is present
            deno_node_missing = [m for m in missing if "Deno" in m or "Node" in m]
            assert len(deno_node_missing) == 0

    def test_all_deps_missing(self):
        """Test all dependencies reported when missing."""
        with patch.object(shutil, "which", return_value=None):
            missing = check_dependencies()

            assert len(missing) == 2
            assert any("FFmpeg" in m for m in missing)
            assert any("Deno" in m or "Node" in m for m in missing)


class TestGetGameAgent:
    """Tests for get_game_agent lazy loading.

    Note: These tests are skipped if agno has Python version compatibility issues,
    since importing game_agent triggers agno imports.
    """

    # Try to check if agno is compatible
    @staticmethod
    def _is_agno_compatible():
        try:
            from agno.db.sqlite import SqliteDb
            return True
        except (TypeError, AssertionError, ImportError):
            return False

    @pytest.mark.skipif(
        not _is_agno_compatible.__func__(),
        reason="agno library has Python version compatibility issues"
    )
    def test_get_game_agent_creates_singleton(self):
        """Test get_game_agent creates and returns singleton."""
        import main

        # Reset singleton
        main._game_agent = None

        mock_agent = MagicMock()
        # Patch where GameAgent is imported from (game_agent package)
        with patch("game_agent.GameAgent", return_value=mock_agent) as mock_agent_class:
            # First call creates agent
            agent1 = main.get_game_agent()

            assert agent1 is mock_agent
            mock_agent_class.assert_called_once()

            # Second call returns same agent (singleton)
            agent2 = main.get_game_agent()
            assert agent2 is agent1
            # Should still be only one call
            mock_agent_class.assert_called_once()

        # Clean up
        main._game_agent = None

    @pytest.mark.skipif(
        not _is_agno_compatible.__func__(),
        reason="agno library has Python version compatibility issues"
    )
    def test_get_game_agent_raises_on_missing_keys(self):
        """Test get_game_agent raises ValueError on missing API keys."""
        import importlib.util
        from pathlib import Path

        import main

        # Reset singleton
        main._game_agent = None

        # Import MissingEnvironmentVariableError directly to avoid cascade
        env_path = Path(__file__).parent.parent.parent / "game_agent" / "environment.py"
        spec = importlib.util.spec_from_file_location("env_mod", env_path)
        env_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(env_mod)
        MissingEnvironmentVariableError = env_mod.MissingEnvironmentVariableError

        # Patch GameAgent to raise the exception
        with patch("game_agent.GameAgent", side_effect=MissingEnvironmentVariableError("Missing keys")):
            with pytest.raises(MissingEnvironmentVariableError):
                main.get_game_agent()

        # Clean up
        main._game_agent = None
