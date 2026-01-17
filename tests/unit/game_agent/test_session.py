"""Unit tests for game_agent/session.py - Session context management."""

import importlib.util
from pathlib import Path

import pytest

# Import directly from the file to avoid game_agent/__init__.py cascade
# which triggers agno imports that may have Python version compatibility issues
_module_path = Path(__file__).parent.parent.parent.parent / "game_agent" / "session.py"
_spec = importlib.util.spec_from_file_location("game_agent_session", _module_path)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)

SessionContext = _module.SessionContext
create_session_context = _module.create_session_context


class TestSessionContext:
    """Tests for SessionContext dataclass."""

    def test_session_context_creation(self):
        """Test SessionContext creation with valid values."""
        ctx = SessionContext(
            user_id_str="123456",
            session_id="guild_user",
        )
        assert ctx.user_id_str == "123456"
        assert ctx.session_id == "guild_user"

    def test_session_context_immutable(self):
        """Test SessionContext is immutable (frozen dataclass)."""
        ctx = SessionContext(user_id_str="123", session_id="456")

        with pytest.raises(AttributeError):
            ctx.user_id_str = "789"

    def test_session_context_equality(self):
        """Test SessionContext equality comparison."""
        ctx1 = SessionContext(user_id_str="123", session_id="456")
        ctx2 = SessionContext(user_id_str="123", session_id="456")
        ctx3 = SessionContext(user_id_str="123", session_id="789")

        assert ctx1 == ctx2
        assert ctx1 != ctx3


class TestCreateSessionContext:
    """Tests for create_session_context function."""

    def test_creates_context_with_correct_user_id(self):
        """Test user_id_str is string of user_id."""
        ctx = create_session_context(guild_id=111, user_id=222)

        assert ctx.user_id_str == "222"

    def test_creates_context_with_correct_session_id(self):
        """Test session_id combines guild and user."""
        ctx = create_session_context(guild_id=111, user_id=222)

        assert ctx.session_id == "111_222"

    def test_different_guilds_different_sessions(self):
        """Test same user in different guilds gets different sessions."""
        ctx1 = create_session_context(guild_id=111, user_id=999)
        ctx2 = create_session_context(guild_id=222, user_id=999)

        # Same user ID string
        assert ctx1.user_id_str == ctx2.user_id_str

        # Different session IDs
        assert ctx1.session_id != ctx2.session_id

    def test_different_users_same_guild(self):
        """Test different users in same guild get different sessions."""
        ctx1 = create_session_context(guild_id=111, user_id=100)
        ctx2 = create_session_context(guild_id=111, user_id=200)

        # Different user IDs
        assert ctx1.user_id_str != ctx2.user_id_str

        # Different session IDs
        assert ctx1.session_id != ctx2.session_id

    def test_handles_large_ids(self):
        """Test handles large Discord snowflake IDs."""
        # Discord snowflakes can be very large
        guild_id = 1234567890123456789
        user_id = 9876543210987654321

        ctx = create_session_context(guild_id=guild_id, user_id=user_id)

        assert ctx.user_id_str == "9876543210987654321"
        assert ctx.session_id == "1234567890123456789_9876543210987654321"

    def test_handles_zero_ids(self):
        """Test handles zero IDs (edge case)."""
        ctx = create_session_context(guild_id=0, user_id=0)

        assert ctx.user_id_str == "0"
        assert ctx.session_id == "0_0"
