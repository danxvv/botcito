"""Unit tests for game_agent/agent.py - Main GameAgent class.

Note: These tests are skipped if agno has Python version compatibility issues.
The agno library has known issues with Python 3.14's pydantic integration.
"""

import importlib.util
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Try to import agno to check compatibility
try:
    from agno.db.sqlite import SqliteDb

    AGNO_COMPATIBLE = True
except (TypeError, AssertionError, ImportError) as e:
    AGNO_COMPATIBLE = False


pytestmark = pytest.mark.skipif(
    not AGNO_COMPATIBLE,
    reason="agno library has Python version compatibility issues"
)


# Import environment module directly to avoid game_agent/__init__.py cascade
_env_path = Path(__file__).parent.parent.parent.parent / "game_agent" / "environment.py"
_env_spec = importlib.util.spec_from_file_location("game_agent_env", _env_path)
_env_module = importlib.util.module_from_spec(_env_spec)
_env_spec.loader.exec_module(_env_module)
MissingEnvironmentVariableError = _env_module.MissingEnvironmentVariableError


class TestGameAgentInit:
    """Tests for GameAgent initialization."""

    def test_init_validates_environment(self):
        """Test __init__ validates environment variables."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(MissingEnvironmentVariableError):
                from game_agent.agent import GameAgent
                GameAgent()

    def test_init_creates_db(self):
        """Test __init__ creates SQLite database."""
        env = {
            "EXA_API_KEY": "test-exa",
            "OPENROUTER_API_KEY": "test-openrouter",
        }

        with patch.dict(os.environ, env, clear=True):
            with patch("game_agent.agent.SqliteDb") as mock_db_class:
                with patch("game_agent.agent.validate_environment") as mock_validate:
                    mock_validate.return_value = MagicMock(
                        exa_api_key="test-exa",
                        openrouter_api_key="test-openrouter",
                    )

                    from game_agent.agent import GameAgent
                    agent = GameAgent()

                    mock_db_class.assert_called_once()

    def test_init_stores_api_keys(self):
        """Test __init__ stores validated API keys."""
        env = {
            "EXA_API_KEY": "test-exa-key",
            "OPENROUTER_API_KEY": "test-openrouter-key",
        }

        with patch.dict(os.environ, env, clear=True):
            with patch("game_agent.agent.SqliteDb"):
                from game_agent.agent import GameAgent
                agent = GameAgent()

                assert agent.api_keys.exa_api_key == "test-exa-key"
                assert agent.api_keys.openrouter_api_key == "test-openrouter-key"


class TestGameAgentAsk:
    """Tests for GameAgent.ask method."""

    @pytest.fixture
    def mock_agent(self):
        """Create a mocked GameAgent."""
        env = {
            "EXA_API_KEY": "test-exa",
            "OPENROUTER_API_KEY": "test-openrouter",
        }

        with patch.dict(os.environ, env, clear=True):
            with patch("game_agent.agent.SqliteDb"):
                from game_agent.agent import GameAgent
                return GameAgent()

    @pytest.mark.asyncio
    async def test_ask_raises_on_empty_question(self, mock_agent):
        """Test ask raises ValueError for empty question."""
        with pytest.raises(ValueError, match="empty"):
            async for _ in mock_agent.ask(111, 222, ""):
                pass

    @pytest.mark.asyncio
    async def test_ask_raises_on_whitespace_question(self, mock_agent):
        """Test ask raises ValueError for whitespace-only question."""
        with pytest.raises(ValueError, match="empty"):
            async for _ in mock_agent.ask(111, 222, "   "):
                pass

    @pytest.mark.asyncio
    async def test_ask_streams_response_chunks(self, mock_agent):
        """Test ask yields response chunks."""
        mock_event1 = MagicMock()
        mock_event1.content = "Hello "
        mock_event2 = MagicMock()
        mock_event2.content = "world!"
        mock_event3 = MagicMock()
        mock_event3.content = None  # Empty event should be skipped

        async def mock_arun(*args, **kwargs):
            for event in [mock_event1, mock_event2, mock_event3]:
                yield event

        mock_agno_agent = MagicMock()
        mock_agno_agent.arun = mock_arun

        with patch("game_agent.agent.MCPConnection") as mock_mcp_conn:
            mock_mcp_conn.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_mcp_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch("game_agent.agent.create_game_agent", return_value=mock_agno_agent):
                chunks = []
                async for chunk in mock_agent.ask(111, 222, "How do I beat the boss?"):
                    chunks.append(chunk)

                assert chunks == ["Hello ", "world!"]


class TestGameAgentAskSimple:
    """Tests for GameAgent.ask_simple method."""

    @pytest.fixture
    def mock_agent(self):
        """Create a mocked GameAgent."""
        env = {
            "EXA_API_KEY": "test-exa",
            "OPENROUTER_API_KEY": "test-openrouter",
        }

        with patch.dict(os.environ, env, clear=True):
            with patch("game_agent.agent.SqliteDb"):
                from game_agent.agent import GameAgent
                return GameAgent()

    @pytest.mark.asyncio
    async def test_ask_simple_returns_full_response(self, mock_agent):
        """Test ask_simple returns complete response string."""
        async def mock_ask(guild_id, user_id, question):
            yield "Part 1: "
            yield "Part 2: "
            yield "Part 3"

        with patch.object(mock_agent, "ask", mock_ask):
            result = await mock_agent.ask_simple(111, 222, "test")

            assert result == "Part 1: Part 2: Part 3"

    @pytest.mark.asyncio
    async def test_ask_simple_returns_empty_string(self, mock_agent):
        """Test ask_simple returns empty string when no chunks."""
        async def mock_ask(guild_id, user_id, question):
            return
            yield  # Make it a generator

        with patch.object(mock_agent, "ask", mock_ask):
            result = await mock_agent.ask_simple(111, 222, "test")

            assert result == ""
